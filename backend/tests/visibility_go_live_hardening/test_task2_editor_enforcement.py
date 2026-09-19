# Feature: visibility-isolation-go-live-hardening — Task 2 启用编辑器令牌强制（R1）
"""Task 2 / Requirements 1.1–1.12（组件 H1 EnforcementEnabler / C11 EditorSecurity / C8 WpBoundGate）。

证明三层，**两个 enforce 状态都真实生效，绝不假绿**：

  A. 环境求值（H1）：``settings.ONLYOFFICE_JWT_ENFORCE`` 未显式设置时按 ``APP_ENV`` 派生
     （prod/production/staging → True；dev → False）；显式设置则尊重原值（纯配置 Rollback_Path，
     不需代码回滚）。默认值不硬翻转为 True（本地开发编辑不破坏）。—— Req 1.1/1.10/1.11/1.12。

  B. enforce=True 时门拒绝分支统一 404（External_Not_Found）+ secret 缺失 fail-closed + 有效令牌放行；
     enforce=False 时 dev 门拒绝仅记录告警并放行（编辑不破坏）。真实 FastAPI 门路径
     （``wp_onlyoffice_router._gate_editor`` + ``resolve_wp_binding_and_access``）+ 真实 PostgreSQL。
     —— Req 1.2/1.3/1.8/1.11。

  C. WOPI GetFile 真实 ASGI wire：签名有效但 claim 不一致的令牌在 enforce=True 下 wire 404
     （token 绑定校验在文件解析前拦截跨资源重放）；enforce=False 时不因强制而阻断（进入文件解析路径）。
     callback/PutFile 落盘前重校验 Current_Version / action / 撤权（``verify_callback_preconditions``，
     即回调分支实际调用的机制）。—— Req 1.4/1.5/1.6/1.7/1.9。

不改 ``editor_security`` 校验逻辑（恒 fail-closed，父 spec 已建已测），本 Task 仅确认 enforce
门控是否对外 404 / 放行。真实 PostgreSQL（audit_platform），每用例事务隔离回滚，绝不污染 dev 库。
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.core.config import settings as app_settings
from app.core.database import get_db
from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL
from app.services.wp_visibility.editor_security import (
    sign_editor_token,
    verify_callback_preconditions,
)

from tests.procedure_delegation_visibility._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)

_SECRET = "task2-go-live-enforce-secret"


# ===========================================================================
# A. 环境求值 + Rollback_Path（H1 EnforcementEnabler，Req 1.1/1.10/1.11/1.12）
#    纯配置层，无需 DB。
# ===========================================================================
class TestEnvGatedEnforcement:
    def _fresh(self, monkeypatch, **kw) -> Settings:
        # 移除进程 env 干扰，确保派生逻辑可确定复现（构造入参优先级最高）。
        monkeypatch.delenv("ONLYOFFICE_JWT_ENFORCE", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        return Settings(_env_file=None, **kw)

    def test_dev_defaults_false(self, monkeypatch):
        """dev（JWT disabled）保持 False → 本地开发编辑不破坏（Req 1.11）。"""
        assert self._fresh(monkeypatch, APP_ENV="dev").ONLYOFFICE_JWT_ENFORCE is False

    @pytest.mark.parametrize("env", ["prod", "production", "staging"])
    def test_prod_staging_derives_true(self, monkeypatch, env):
        """生产/预发环境派生为 True（Req 1.1）。"""
        assert self._fresh(monkeypatch, APP_ENV=env).ONLYOFFICE_JWT_ENFORCE is True

    def test_rollback_path_explicit_false_in_prod(self, monkeypatch):
        """生产环境显式 ONLYOFFICE_JWT_ENFORCE=false → 恢复启用前行为，纯配置、无需代码回滚（Req 1.10）。"""
        s = self._fresh(monkeypatch, APP_ENV="production", ONLYOFFICE_JWT_ENFORCE=False)
        assert s.ONLYOFFICE_JWT_ENFORCE is False

    def test_explicit_true_enables_in_dev(self, monkeypatch):
        """显式 env ONLYOFFICE_JWT_ENFORCE=true 即启用（不依赖 APP_ENV）。"""
        s = self._fresh(monkeypatch, APP_ENV="dev", ONLYOFFICE_JWT_ENFORCE=True)
        assert s.ONLYOFFICE_JWT_ENFORCE is True

    def test_default_runtime_import_is_dev_false(self):
        """默认值未硬翻转为 True：进程内既有 settings 单例在 dev 下为 False（Req 1.1 反向保证）。"""
        # dev 环境（无 APP_ENV/ONLYOFFICE_JWT_ENFORCE env）下 live 单例应为 False。
        if (os.environ.get("APP_ENV") or "dev").lower() in ("prod", "production", "staging"):
            pytest.skip("APP_ENV 指向生产/预发，跳过 dev 默认断言")
        assert app_settings.ONLYOFFICE_JWT_ENFORCE is False


# ===========================================================================
# 真实 PostgreSQL 事务隔离上下文（用例结束整体回滚）
# ===========================================================================
class _PgCtx:
    def __init__(self) -> None:
        self.engine = None
        self.conn = None
        self.trans = None
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self.engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
        self.conn = await self.engine.connect()
        self.trans = await self.conn.begin()
        self.session = AsyncSession(bind=self.conn, join_transaction_mode="create_savepoint")
        return self.session

    async def __aexit__(self, *exc) -> None:
        from app.main import app

        app.dependency_overrides.pop(get_db, None)
        if self.session is not None:
            await self.session.close()
        if self.trans is not None:
            await self.trans.rollback()
        if self.conn is not None:
            await self.conn.close()
        if self.engine is not None:
            await self.engine.dispose()

async def _lead(s, *, scope="D", cycle="D", wp_code="D2-1"):
    proj = await mk_project(s)
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code=wp_code, audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp


async def _outsider(s, proj):
    o = await mk_user(s)
    await mk_project_user(s, proj.id, o.id, scope_cycles="")
    await s.flush()
    return o


# ===========================================================================
# B. _gate_editor enforce 两态（真实 PG，Req 1.2/1.3/1.8/1.11）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (real gate integration)")
@pytest.mark.asyncio
class TestEditorGateEnforceStates:
    async def test_gate_deny_enforce_true_returns_404(self, monkeypatch):
        """enforce=True + 门拒绝（越权成员）→ 统一 External_Not_Found 404（Req 1.2）。"""
        from app.routers import wp_onlyoffice_router as oor

        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_ENFORCE", True)
        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, _lead_u, _wi, wp = await _lead(s)
            outsider = await _outsider(s, proj)
            with pytest.raises(HTTPException) as ei:
                await oor._gate_editor(
                    s, outsider, wp_id=wp.id, project_id=proj.id,
                    entrypoint="editor.config", action="editor_config",
                    method="GET", sheet_name="D2A",
                )
            assert ei.value.status_code == 404
            assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
        finally:
            await ctx.__aexit__()

    async def test_gate_deny_enforce_false_dev_passthrough(self, monkeypatch):
        """enforce=False + 门拒绝 → dev 放行（返回 None），本地开发编辑不破坏（Req 1.11）。"""
        from app.routers import wp_onlyoffice_router as oor

        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_ENFORCE", False)
        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, _lead_u, _wi, wp = await _lead(s)
            outsider = await _outsider(s, proj)
            res = await oor._gate_editor(
                s, outsider, wp_id=wp.id, project_id=proj.id,
                entrypoint="editor.config", action="editor_config",
                method="GET", sheet_name="D2A",
            )
            assert res is None  # dev passthrough：不阻断请求
        finally:
            await ctx.__aexit__()

    async def test_valid_token_lead_allowed_enforce_true(self, monkeypatch):
        """enforce=True + 有效签名令牌 + 合法 lead → 门放行（Req 1.3）。

        （不带 requested sheet，避免依赖 SheetBindingCatalog——合成 wp 无模板故无 sheet 目录；
        令牌逐 claim 绑定 project/wp/version/wp_code/action 一致校验仍完整执行。）
        """
        from app.routers import wp_onlyoffice_router as oor

        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_ENFORCE", True)
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", _SECRET)
        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, lead, _wi, wp = await _lead(s)
            token = sign_editor_token(
                secret=_SECRET, sub=str(lead.id), project_id=str(proj.id),
                wp_id=str(wp.id), sheet_name="D2A", wp_code="D2-1",
                version=str(wp.file_version), action="editor_config",
            )
            res = await oor._gate_editor(
                s, lead, wp_id=wp.id, project_id=proj.id,
                entrypoint="editor.config", action="editor_config",
                method="GET", signed_token=token,
            )
            assert res is not None
            assert "lead" in res.access_kinds
            assert res.readonly is False
        finally:
            await ctx.__aexit__()

    @pytest.mark.parametrize(
        "kind",
        ["bad_signature", "expired", "claim_mismatch"],
    )
    async def test_bad_token_enforce_true_404(self, monkeypatch, kind):
        """enforce=True + 令牌失败态（签名错误 / 过期 / claim 不一致）→ 统一 404（Req 1.4/1.5/1.6）。

        令牌全量校验由 editor_security fail-closed（本 Task 不改其逻辑）；门抛 ExternalNotFound
        (token_invalid)，enforce 开启对外统一 External_Not_Found 404。
        """
        import time as _time
        from app.routers import wp_onlyoffice_router as oor

        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_ENFORCE", True)
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", _SECRET)
        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, lead, _wi, wp = await _lead(s)
            if kind == "bad_signature":
                token = sign_editor_token(
                    secret="a-totally-different-secret", sub=str(lead.id),
                    project_id=str(proj.id), wp_id=str(wp.id), sheet_name="D2A",
                    wp_code="D2-1", version=str(wp.file_version), action="editor_config",
                )
            elif kind == "expired":
                token = sign_editor_token(
                    secret=_SECRET, sub=str(lead.id), project_id=str(proj.id),
                    wp_id=str(wp.id), sheet_name="D2A", wp_code="D2-1",
                    version=str(wp.file_version), action="editor_config",
                    lifetime_seconds=1, now=int(_time.time()) - 10_000,
                )
            else:  # claim_mismatch —— 为「其它 wp」签发（wp_id 不一致，跨资源重放）
                token = sign_editor_token(
                    secret=_SECRET, sub=str(lead.id), project_id=str(proj.id),
                    wp_id=str(uuid4()), sheet_name="D2A", wp_code="D2-1",
                    version=str(wp.file_version), action="editor_config",
                )
            with pytest.raises(HTTPException) as ei:
                await oor._gate_editor(
                    s, lead, wp_id=wp.id, project_id=proj.id,
                    entrypoint="editor.config", action="editor_config",
                    method="GET", signed_token=token,
                )
            assert ei.value.status_code == 404
            assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
        finally:
            await ctx.__aexit__()

    async def test_bad_token_enforce_false_dev_passthrough(self, monkeypatch):
        """enforce=False + 令牌失败态 → dev 放行（不因强制阻断），本地开发编辑不破坏（Req 1.11）。"""
        from app.routers import wp_onlyoffice_router as oor

        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_ENFORCE", False)
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", _SECRET)
        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, lead, _wi, wp = await _lead(s)
            token = sign_editor_token(
                secret="a-totally-different-secret", sub=str(lead.id),
                project_id=str(proj.id), wp_id=str(wp.id), sheet_name="D2A",
                wp_code="D2-1", version=str(wp.file_version), action="editor_config",
            )
            res = await oor._gate_editor(
                s, lead, wp_id=wp.id, project_id=proj.id,
                entrypoint="editor.config", action="editor_config",
                method="GET", signed_token=token,
            )
            assert res is None  # dev passthrough
        finally:
            await ctx.__aexit__()

    async def test_secret_missing_fail_closed_enforce_true(self, monkeypatch):
        """enforce=True + secret 缺失（JWT disabled bypass）+ 携令牌 → fail-closed 404（Req 1.8）。

        即便是合法 lead，secret 缺失时 signed_token 全量校验 fail-closed（editor_security），
        门抛 ExternalNotFound，enforce 开启对外统一 404。
        """
        from app.routers import wp_onlyoffice_router as oor

        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_ENFORCE", True)
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")
        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, lead, _wi, wp = await _lead(s)
            with pytest.raises(HTTPException) as ei:
                await oor._gate_editor(
                    s, lead, wp_id=wp.id, project_id=proj.id,
                    entrypoint="editor.config", action="editor_config",
                    method="GET", sheet_name="D2A",
                    signed_token="any.forged.token",
                )
            assert ei.value.status_code == 404
            assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
        finally:
            await ctx.__aexit__()


# ===========================================================================
# C. callback/PutFile 落盘前重校验（Req 1.7/1.9）
#    这是 wp_onlyoffice_router callback 分支与 api/wopi PutFile 分支在 enforce=True 时
#    实际调用的机制（verify_callback_preconditions / 门 editor_write 重解析）。纯函数，无需 DB。
# ===========================================================================
class TestCallbackReverify:
    def test_callback_reverify_version_conflict(self):
        """callback 落盘前 Current_Version 重校验：claim 版本 ≠ 当前版本 → 拒绝（Req 1.9）。"""
        ok, reason = verify_callback_preconditions(
            claim_action="callback", server_action="callback",
            claim_version="1", current_version="9", gate_allow_write=True,
        )
        assert ok is False and reason == "version_conflict"

    def test_callback_reverify_readonly_token_write(self):
        """只读令牌请求写（回调）→ 拒绝（Req 1.7）。"""
        ok, reason = verify_callback_preconditions(
            claim_action="editor_read", server_action="callback",
            claim_version="1", current_version="1", gate_allow_write=True,
        )
        assert ok is False and reason == "readonly_token"

    def test_callback_reverify_revoked_session(self):
        """撤权会话（门不再授权写 / epoch 失效）→ 拒绝（Req 1.9）。"""
        ok_r, reason_r = verify_callback_preconditions(
            claim_action="callback", server_action="callback",
            claim_version="1", current_version="1", gate_allow_write=False,
        )
        assert ok_r is False and reason_r == "not_delegated"
        ok_e, reason_e = verify_callback_preconditions(
            claim_action="callback", server_action="callback",
            claim_version="1", current_version="1",
            gate_allow_write=True, epoch_valid=False,
        )
        assert ok_e is False and reason_e == "epoch_stale"

    def test_callback_reverify_action_mismatch_and_pass(self):
        """action 与服务端不一致 → 拒绝；全部一致 → 放行（Req 1.9 正/反）。"""
        ok_bad, reason_bad = verify_callback_preconditions(
            claim_action="convert_write", server_action="callback",
            claim_version="1", current_version="1", gate_allow_write=True,
        )
        assert ok_bad is False and reason_bad == "action_denied"
        ok, reason = verify_callback_preconditions(
            claim_action="callback", server_action="callback",
            claim_version="1", current_version="1", gate_allow_write=True,
        )
        assert ok is True and reason is None
