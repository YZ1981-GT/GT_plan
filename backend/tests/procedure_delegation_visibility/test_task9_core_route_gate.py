# Feature: procedure-delegation-visibility-isolation — Task 9 EntryIntegration（C10）
"""核心底稿路由接入 Wp_Bound_Gate 的真实 app + PostgreSQL 集成测试。

Task 9 / Requirements 5.8–5.18, 7.5, 8.5, 8.10–8.12, 8.15, 9, 12.7–12.9。

覆盖已接入 gate 的核心路由（每路由+method 的 allow / deny / cross-project 维度）：
  - GET  /api/workpapers/{wp_id}/render-config           （render_config / read_render）
  - GET  /api/workpapers/{wp_id}/checklist-responses     （checklist / read_checklist）
  - PUT  /api/workpapers/{wp_id}/checklist-responses     （checklist / save_checklist）
  - PUT  /api/projects/{pid}/working-papers/{wp_id}/parsed-data （save / save_parsed_data）
  - POST /api/workpapers/{wp_id}/ai/generate-text        （ai / ai_generate）

真实 FastAPI app（app.main:app）+ 真实 PostgreSQL（audit_platform）。每个用例独立引擎/连接，
外层事务 + ``join_transaction_mode="create_savepoint"``（route 内 commit 只释放 savepoint，
用例结束整体回滚，绝不污染 dev 库）。gate 的安全 outbox 走独立 session，其对未提交 project 的
FK 插入会失败并被吞（Operational_Alert），故 deny 用例也不留痕。

version / sheet 维度说明：这些内容路由在 wp 级接入 gate（Current_Version 隐式、无历史版本/单 sheet
路由参数），历史版本与未映射 sheet 的 404 隔离由 gate 服务层统一处理并在 test_wp_bound_gate.py
（Property 10）验证；此处以路由级 allow/deny/cross-project 为主。
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL


def _detail(resp) -> str | None:
    """提取拒绝文案：ResponseWrapperMiddleware 把 404 包成 {code,message} 信封，
    detail 落在 message；未包装时仍在 detail。"""
    body = resp.json()
    if not isinstance(body, dict):
        return None
    return body.get("detail") or body.get("message")

from ._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (real app gate integration)"),
]


class _Ctx:
    """每用例独立 PG 连接 + savepoint 隔离 + app 依赖覆盖。"""

    def __init__(self) -> None:
        self.engine = None
        self.conn = None
        self.trans = None
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self.engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
        self.conn = await self.engine.connect()
        self.trans = await self.conn.begin()
        self.session = AsyncSession(
            bind=self.conn, join_transaction_mode="create_savepoint"
        )
        return self.session

    async def __aexit__(self, *exc) -> None:
        from app.main import app

        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        if self.session is not None:
            await self.session.close()
        if self.trans is not None:
            await self.trans.rollback()
        if self.conn is not None:
            await self.conn.close()
        if self.engine is not None:
            await self.engine.dispose()

    def bind_app(self, user):
        """把 app 的 get_db / get_current_user 绑定到本用例 session + 指定用户。"""
        from app.main import app

        session = self.session

        async def _override_db():
            yield session

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_lead(s, *, scope="D", cycle="D"):
    """底稿主编场景：user 是 wp 的 assigned_to，scope 覆盖循环。"""
    proj = await mk_project(s)
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp


async def _seed_outsider(s, proj):
    """同项目但无委派、scope 为空的受限用户（gate → not_delegated 404）。"""
    outsider = await mk_user(s)
    await mk_project_user(s, proj.id, outsider.id, scope_cycles="")
    await s.flush()
    return outsider


async def _mk_admin(s):
    admin = await mk_user(s, role="admin")
    await s.flush()
    return admin


# ---------------------------------------------------------------------------
# render-config
# ---------------------------------------------------------------------------
async def test_render_config_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/workpapers/{wp.id}/render-config")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_render_config_allow_lead_passes_gate():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/workpapers/{wp.id}/render-config")
        # 合法主编：gate 放行。下游模板加载可能因合成底稿失败，但绝不是 gate 的统一 404。
        if r.status_code == 404:
            assert _detail(r) != EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_render_config_cross_project_denied():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        # lead 在另一个项目里没有任何可见性；用其访问本 wp 但声明另一项目——此处用 outsider 更直接
        other = await mk_project(s)
        await s.flush()
        # lead 对 other 项目无 project_user → 对 other 内资源不可见；构造 other 项目底稿
        wi2 = await mk_wp_index(s, other.id, wp_code="D2-1", audit_cycle="D")
        wp2 = await mk_working_paper(s, other.id, wi2.id)
        await s.flush()
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/workpapers/{wp2.id}/render-config")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# checklist-responses GET
# ---------------------------------------------------------------------------
async def test_checklist_get_allow_lead():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/workpapers/{wp.id}/checklist-responses")
        assert r.status_code == 200
        # 信封中 data 为 list（新底稿无响应 → 空列表）
        body = r.json()
        data = body.get("data", body)
        assert isinstance(data, list)
    finally:
        await ctx.__aexit__()


async def test_checklist_get_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/workpapers/{wp.id}/checklist-responses")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_checklist_get_nonexistent_404():
    from uuid import uuid4

    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/workpapers/{uuid4()}/checklist-responses")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# checklist-responses PUT （admin 绕过编辑权门禁，聚焦 gate 行为）
# ---------------------------------------------------------------------------
async def test_checklist_put_allow_admin():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj = await mk_project(s)
        admin = await _mk_admin(s)
        wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
        wp = await mk_working_paper(s, proj.id, wi.id)
        await s.flush()
        payload = {"items": [{"item_id": "D2-note", "conclusion": None, "remark": "x"}]}
        async with ctx.bind_app(admin) as c:
            r = await c.put(
                f"/api/workpapers/{wp.id}/checklist-responses", json=payload
            )
        # admin 通过编辑权门禁 + gate → 保存成功（不得为 gate 的 404）
        assert r.status_code != 404
    finally:
        await ctx.__aexit__()


async def test_checklist_put_deny_admin_nonexistent_wp():
    from uuid import uuid4

    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        await mk_project(s)
        admin = await _mk_admin(s)
        await s.flush()
        payload = {"items": [{"item_id": "D2-note", "conclusion": None, "remark": "x"}]}
        async with ctx.bind_app(admin) as c:
            r = await c.put(
                f"/api/workpapers/{uuid4()}/checklist-responses", json=payload
            )
        # gate 反查不到资源 → 统一 404
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# parsed-data PUT （admin）
# ---------------------------------------------------------------------------
async def test_parsed_data_deny_admin_nonexistent_wp():
    from uuid import uuid4

    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj = await mk_project(s)
        admin = await _mk_admin(s)
        await s.flush()
        async with ctx.bind_app(admin) as c:
            r = await c.put(
                f"/api/projects/{proj.id}/working-papers/{uuid4()}/parsed-data",
                json={"foo": "bar"},
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_parsed_data_allow_admin():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj = await mk_project(s)
        admin = await _mk_admin(s)
        wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
        wp = await mk_working_paper(s, proj.id, wi.id)
        await s.flush()
        async with ctx.bind_app(admin) as c:
            r = await c.put(
                f"/api/projects/{proj.id}/working-papers/{wp.id}/parsed-data",
                json={"foo": "bar"},
            )
        assert r.status_code != 404
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# AI generate-text POST
# ---------------------------------------------------------------------------
async def test_ai_generate_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.post(
                f"/api/workpapers/{wp.id}/ai/generate-text",
                json={"prompt": "x", "context": {}, "existingContent": "", "section": ""},
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_ai_generate_allow_lead_passes_gate():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.post(
                f"/api/workpapers/{wp.id}/ai/generate-text",
                json={"prompt": "x", "context": {}, "existingContent": "", "section": ""},
            )
        # gate 放行；AI 服务可能未启用 → 503，但绝不是 gate 的统一 404
        if r.status_code == 404:
            assert _detail(r) != EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_ai_generate_nonexistent_404():
    from uuid import uuid4

    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.post(
                f"/api/workpapers/{uuid4()}/ai/generate-text",
                json={"prompt": "x", "context": {}, "existingContent": "", "section": ""},
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# workpaper detail GET  /api/projects/{pid}/working-papers/{wp_id}
# entrypoint workpaper.detail / read_detail（Task 9 续接）
# ---------------------------------------------------------------------------
async def test_detail_allow_lead():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/projects/{proj.id}/working-papers/{wp.id}")
        # 合法主编：gate 放行（下游详情装配可能因合成底稿数据异常，但绝不是 gate 的统一 404）。
        assert not (r.status_code == 404 and _detail(r) == EXTERNAL_NOT_FOUND_DETAIL)
    finally:
        await ctx.__aexit__()


async def test_detail_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/projects/{proj.id}/working-papers/{wp.id}")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_detail_cross_project_denied():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        other = await mk_project(s)
        wi2 = await mk_wp_index(s, other.id, wp_code="D2-1", audit_cycle="D")
        wp2 = await mk_working_paper(s, other.id, wi2.id)
        await s.flush()
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/projects/{other.id}/working-papers/{wp2.id}")
        # 详情 route 保留既有 require_project_access("readonly")：跨项目非成员先行 403；
        # gate 层叠其上（同项目未委派 → 404）。两者均阻断，绝不放行 200。
        assert r.status_code in (403, 404)
        assert r.status_code != 200
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# version list GET  /api/projects/{pid}/workpapers/{wp_id}/versions
# 注意：该路径由 wp_export_import_router.get_version_history 实际服务（与 version_trail
# 同路径重复注册），两处 handler 均已接入 gate。get_version_history 保留 require_project_access，
# 故跨项目返回 403（既有项目级门禁，未改语义），同项目未委派返回 gate 的 404。
# entrypoint workpaper.version_list / read_versions
# ---------------------------------------------------------------------------
async def test_version_list_allow_lead():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/projects/{proj.id}/workpapers/{wp.id}/versions")
        # 合法主编：gate 放行 → 200（归档历史列表，新底稿为空）。
        assert r.status_code == 200
    finally:
        await ctx.__aexit__()


async def test_version_list_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/projects/{proj.id}/workpapers/{wp.id}/versions")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_version_list_cross_project_denied():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        other = await mk_project(s)
        wi2 = await mk_wp_index(s, other.id, wp_code="D2-1", audit_cycle="D")
        wp2 = await mk_working_paper(s, other.id, wi2.id)
        await s.flush()
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/projects/{other.id}/workpapers/{wp2.id}/versions")
        # 跨项目非成员：既有 require_project_access 先行 403；gate 亦会 404。均阻断，绝不 200。
        assert r.status_code in (403, 404)
        assert r.status_code != 200
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# version detail GET  /api/projects/{pid}/workpapers/{wp_id}/versions/{vid}
# ---------------------------------------------------------------------------
async def test_version_detail_deny_not_delegated():
    from uuid import uuid4

    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(
                f"/api/projects/{proj.id}/workpapers/{wp.id}/versions/{uuid4()}"
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_version_detail_allow_lead_passes_gate():
    from uuid import uuid4

    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(
                f"/api/projects/{proj.id}/workpapers/{wp.id}/versions/{uuid4()}"
            )
        # gate 放行；快照不存在 → 下游 404，但绝不是 gate 的统一 External_Not_Found。
        if r.status_code == 404:
            assert _detail(r) != EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# version rollback POST  /api/projects/{pid}/workpapers/{wp_id}/versions/{vid}/rollback
# entrypoint version.restore / version_restore（写；仅 lead/admin/supervisor_scope）
# ---------------------------------------------------------------------------
async def test_version_rollback_deny_not_delegated():
    from uuid import uuid4

    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.post(
                f"/api/projects/{proj.id}/workpapers/{wp.id}/versions/{uuid4()}/rollback"
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_version_rollback_cross_project_denied():
    from uuid import uuid4

    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        other = await mk_project(s)
        wi2 = await mk_wp_index(s, other.id, wp_code="D2-1", audit_cycle="D")
        wp2 = await mk_working_paper(s, other.id, wi2.id)
        await s.flush()
        async with ctx.bind_app(lead) as c:
            r = await c.post(
                f"/api/projects/{other.id}/workpapers/{wp2.id}/versions/{uuid4()}/rollback"
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_version_rollback_allow_admin_passes_gate():
    from uuid import uuid4

    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj = await mk_project(s)
        admin = await _mk_admin(s)
        wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
        wp = await mk_working_paper(s, proj.id, wi.id)
        await s.flush()
        async with ctx.bind_app(admin) as c:
            r = await c.post(
                f"/api/projects/{proj.id}/workpapers/{wp.id}/versions/{uuid4()}/rollback"
            )
        # admin 过 gate + 角色门禁；快照不存在 → 下游 404/400，但绝不是 gate 的统一 404。
        if r.status_code == 404:
            assert _detail(r) != EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()
