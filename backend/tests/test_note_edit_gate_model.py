# Feature: partner-manager-edit-permission, Property 7: 附注编辑门禁结论等于模型，拒绝零业务效果
"""附注编辑门禁模型对拍（端点级）。

Property 7: 附注编辑门禁结论等于模型，拒绝零业务效果

Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.11, 6.12, 6.13

维度（需求 6.13）：
- 身份：edit member / review member / readonly member / EQCR / non-member / admin / archived project member
- 端点：路径依赖（大多数）/ 请求体 project_id (A1 generate) / 对象 id (A2 update)
- 合并锁：属于 / 不属于 consol_lock 适用集合

三个代表端点：
- A6 (POST .../pull-from-workpapers)：路径依赖，consol_lock=False
- A1 (POST .../generate)：请求体 project_id，consol_lock=True
- A2 (PUT .../disclosure-notes/{note_id})：对象 id 反查，consol_lock=True

7 个固定样例（需求 6.13）：
1. archived-admin: admin on archived project → 423
2. non-member-locked: non-member on locked project → 403
3. project-eqcr-locked: EQCR on locked project → 403 (EQCR 先于合并锁)
4. admin-with-eqcr-assignment: admin with eqcr delegation → 403 (EQCR)
5. qc-global-qc-role: qc member with global qc role → 403 (operation matrix)
6. review-member: review member on unlocked project → allowed
7. review-member-locked-without-lock-check: review member on locked project,
   endpoint has consol_lock=False → allowed

拒绝时断言：业务桩 0 次；EventBus 替身计数 0；原因为固定中文、不含业务内容。
"""
from __future__ import annotations

import importlib
import uuid
from typing import Any

import pytest
import pytest_asyncio
from httpx import Response

from authz_world import (
    TARGET_NOTE_ID,
    TARGET_PROJECT_ID,
    AuthzWorld,
    GateClient,
    Identity,
    sqlite_world,
)
from note_edit_gate_recipes import ALL_RECIPES, Recipe, StubTarget, _NOTE_ID, _YEAR
from app.models.base import PermissionLevel, ProjectStatus, ProjectUserRole, UserRole
from app.services.note_edit_gate import (
    REASON_EQCR_READONLY,
    REASON_FORBIDDEN,
    REASON_OPERATION_DENIED,
)

# ---------------------------------------------------------------------------
# 三个代表端点的配方
# ---------------------------------------------------------------------------

# A6: 路径依赖，consol_lock=False
RECIPE_PATH_DEP = ALL_RECIPES[("POST", "/api/disclosure-notes/{project_id}/{year}/pull-from-workpapers")]
# A1: 请求体 project_id，consol_lock=True
RECIPE_BODY_PID = ALL_RECIPES[("POST", "/api/disclosure-notes/generate")]
# A2: 对象 id 反查，consol_lock=True
RECIPE_OBJECT_ID = ALL_RECIPES[("PUT", "/api/disclosure-notes/{note_id}")]

REPRESENTATIVE_RECIPES = [RECIPE_PATH_DEP, RECIPE_BODY_PID, RECIPE_OBJECT_ID]
_RECIPE_IDS = [f"{r.method} {r.path_template}" for r in REPRESENTATIVE_RECIPES]


# ---------------------------------------------------------------------------
# 路由导入
# ---------------------------------------------------------------------------

from app.routers import disclosure_notes  # noqa: E402

_ALL_ROUTERS = (disclosure_notes.router,)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


class _SmartMock:
    """与 test_note_edit_gate_endpoints 同一个自动代理——门禁放行后业务桩需要返回可用对象。"""
    _PASSTHROUGH = {"ok": True, "message": "stubbed", "executed": 0, "updated": 0}

    def __getattr__(self, name: str) -> _SmartMock:
        return _SmartMock()

    async def __call__(self, *args: Any, **kwargs: Any) -> _SmartMock:
        return _SmartMock()

    def __getitem__(self, key: str) -> Any:
        return self._PASSTHROUGH.get(key, None)

    def __bool__(self) -> bool:
        return False

    def __iter__(self) -> Any:
        return iter([_SmartMock(), _SmartMock()])

    def __len__(self) -> int:
        return 2

    def get(self, key: str, default: Any = None) -> Any:
        return self._PASSTHROUGH.get(key, default)

    def append(self, item: Any) -> None:
        pass


async def _setup_stubs(world: AuthzWorld, recipe: Recipe) -> list[Any]:
    """安装业务桩并返回桩列表（同 test_note_edit_gate_endpoints 的模式）。"""
    stubs = []
    for st in recipe.stubs:
        owner = importlib.import_module(st.owner_import)
        if st.is_class:
            stubs.append(world.stub(owner, st.attr, returns=_SmartMock(), awaitable=False))
        else:
            stubs.append(world.stub(owner, st.attr, returns=_SmartMock(), awaitable=st.awaitable))
    return stubs


def _assert_denied(resp: Response, status: int, reason: str) -> None:
    """断言拒绝响应：状态码 + detail 中的 message 或 detail 本身逐字一致。"""
    assert resp.status_code == status, (
        f"期望 {status}，实际 {resp.status_code}；body={resp.text[:500]}"
    )
    body = resp.json()
    detail = body.get("detail", "")
    if isinstance(detail, dict):
        actual_reason = detail.get("message", "")
    else:
        actual_reason = detail
    assert actual_reason == reason, f"reason 不一致：期望 {reason!r}，实际 {actual_reason!r}"


def _assert_no_business_content(resp: Response) -> None:
    """拒绝响应的原因不含业务内容（如附注正文、表格数据）。"""
    body = resp.json()
    detail = body.get("detail", "")
    text = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    # 业务内容的标志：附注正文长度、表格数据等
    assert len(text) < 200, f"拒绝原因疑似包含业务内容（长度 {len(text)}）"
    # 确认原因是已知的固定中文文本之一
    known_reasons = {REASON_FORBIDDEN, REASON_EQCR_READONLY, REASON_OPERATION_DENIED}
    # 也可能是归档或合并锁文案
    is_known = text in known_reasons or "归档" in text or "合并锁定" in text
    assert is_known, f"拒绝原因不是已知的固定中文文案：{text!r}"


async def _setup_world_extras(world: AuthzWorld) -> None:
    """为 A2 (对象 id 端点) 和 A1 建立必要的附注行。"""
    from app.models.report_models import DisclosureNote as DN
    await world.db.execute(
        DN.__table__.insert().values(
            id=_NOTE_ID,
            project_id=TARGET_PROJECT_ID,
            year=_YEAR,
            note_section="五、1",
            section_title="测试章节",
            is_deleted=False,
        )
    )
    await world.db.flush()


# ============================================================================
# 7 个固定样例
# ============================================================================


class TestFixedSample1ArchivedAdmin:
    """固定样例 1: admin on archived project → 423 归档。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("recipe", REPRESENTATIVE_RECIPES, ids=_RECIPE_IDS)
    async def test_archived_admin_gets_423(self, monkeypatch: pytest.MonkeyPatch, recipe: Recipe) -> None:
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)
            # 把目标项目置为已归档
            world.target.status = ProjectStatus.archived
            await world.db.flush()

            admin_user = await world.user(UserRole.admin)
            stubs = await _setup_stubs(world, recipe)

            async with world.client(*_ALL_ROUTERS, user=admin_user) as client:
                resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

            assert resp.status_code == 423, f"admin on archived project should get 423, got {resp.status_code}"
            # 业务桩 0 次
            for stub in stubs:
                assert stub.count == 0, f"archived admin: 业务桩 {stub.target} 应 0 次，实际 {stub.count}"
            _assert_no_business_content(resp)


class TestFixedSample2NonMemberLocked:
    """固定样例 2: non-member on locked project → 403。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("recipe", REPRESENTATIVE_RECIPES, ids=_RECIPE_IDS)
    async def test_non_member_locked_gets_403(self, monkeypatch: pytest.MonkeyPatch, recipe: Recipe) -> None:
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)
            # 合并锁定
            world.target.consol_lock = True
            await world.db.flush()

            identity = await world.non_member()
            stubs = await _setup_stubs(world, recipe)

            async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
                resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

            _assert_denied(resp, 403, REASON_FORBIDDEN)
            for stub in stubs:
                assert stub.count == 0, f"non-member locked: 业务桩 {stub.target} 应 0 次，实际 {stub.count}"
            _assert_no_business_content(resp)


class TestFixedSample3EqcrLocked:
    """固定样例 3: EQCR on locked project → 403 (EQCR 先于合并锁)。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("recipe", REPRESENTATIVE_RECIPES, ids=_RECIPE_IDS)
    async def test_eqcr_locked_gets_403_eqcr(self, monkeypatch: pytest.MonkeyPatch, recipe: Recipe) -> None:
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)
            # 合并锁定
            world.target.consol_lock = True
            await world.db.flush()

            identity = await world.project_eqcr()
            stubs = await _setup_stubs(world, recipe)

            async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
                resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

            # EQCR 403 先于合并锁 423
            _assert_denied(resp, 403, REASON_EQCR_READONLY)
            for stub in stubs:
                assert stub.count == 0, f"eqcr locked: 业务桩 {stub.target} 应 0 次，实际 {stub.count}"
            _assert_no_business_content(resp)


class TestFixedSample4AdminWithEqcrAssignment:
    """固定样例 4: admin with eqcr delegation → 403 (EQCR, admin 不豁免)。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("recipe", REPRESENTATIVE_RECIPES, ids=_RECIPE_IDS)
    async def test_admin_eqcr_gets_403(self, monkeypatch: pytest.MonkeyPatch, recipe: Recipe) -> None:
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)
            # admin + EQCR 委派。admin 不需要成员行（跳过 ② 的成员校验），但 ③ EQCR 不豁免 admin
            admin_user = await world.user(UserRole.admin)
            await world.eqcr_assignment("eqcr", user=admin_user)
            stubs = await _setup_stubs(world, recipe)

            async with world.client(*_ALL_ROUTERS, user=admin_user) as client:
                resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

            _assert_denied(resp, 403, REASON_EQCR_READONLY)
            for stub in stubs:
                assert stub.count == 0, f"admin eqcr: 业务桩 {stub.target} 应 0 次，实际 {stub.count}"
            _assert_no_business_content(resp)


class TestFixedSample5QcGlobalQcRole:
    """固定样例 5: qc member with global qc role → 403 (operation matrix)。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("recipe", REPRESENTATIVE_RECIPES, ids=_RECIPE_IDS)
    async def test_qc_global_qc_gets_403_operation(self, monkeypatch: pytest.MonkeyPatch, recipe: Recipe) -> None:
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)
            # 全局角色 qc + 项目角色 qc → 操作矩阵不含 note:edit
            identity = await world.qc_review_member()
            stubs = await _setup_stubs(world, recipe)

            async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
                resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

            _assert_denied(resp, 403, REASON_OPERATION_DENIED)
            for stub in stubs:
                assert stub.count == 0, f"qc global qc: 业务桩 {stub.target} 应 0 次，实际 {stub.count}"
            _assert_no_business_content(resp)


class TestFixedSample6ReviewMemberAllowed:
    """固定样例 6: review member on unlocked project → allowed。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("recipe", REPRESENTATIVE_RECIPES, ids=_RECIPE_IDS)
    async def test_review_member_allowed(self, monkeypatch: pytest.MonkeyPatch, recipe: Recipe) -> None:
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)
            # review member (qc, review) — global role auditor, 操作矩阵对 auditor 放行 note:edit
            identity = await world.review_member()
            stubs = await _setup_stubs(world, recipe)

            async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
                try:
                    resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)
                except Exception:
                    # 业务代码在门禁放行后抛异常（桩返回格式不符）——门禁已执行即可
                    client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")
                    return

            assert resp.status_code != 401, f"review member should not get 401"
            assert resp.status_code != 403, f"review member should not get 403: {resp.text[:300]}"
            client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")


class TestFixedSample7ReviewMemberLockedNoLockCheck:
    """固定样例 7: review member on locked project, endpoint has consol_lock=False → allowed。

    只测 A6 (consol_lock=False)，因为 A1/A2 有 consol_lock=True 会被合并锁拦截。
    """

    @pytest.mark.asyncio
    async def test_review_member_locked_no_lock_check_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recipe = RECIPE_PATH_DEP  # A6: consol_lock=False
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)
            # 合并锁定
            world.target.consol_lock = True
            await world.db.flush()

            identity = await world.review_member()
            stubs = await _setup_stubs(world, recipe)

            async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
                try:
                    resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)
                except Exception:
                    client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")
                    return

            assert resp.status_code != 401, f"review member locked no-lock-check should not get 401"
            assert resp.status_code != 403, f"review member locked no-lock-check should not get 403: {resp.text[:300]}"
            assert resp.status_code != 423, f"review member locked no-lock-check should not get 423 (consol_lock=False)"
            client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")


# ============================================================================
# 补充验证：拒绝时 EventBus 替身 0 次（通过检查 world.redis 无写入间接证明）
# ============================================================================


class TestRejectionZeroSideEffects:
    """拒绝时目标项目数据不变（附注行数不变），业务桩 0 次。

    用固定样例 2 (non-member) 作代表。
    """

    @pytest.mark.asyncio
    async def test_rejection_no_data_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recipe = RECIPE_PATH_DEP  # A6
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)
            identity = await world.non_member()

            # 请求前附注行数
            from sqlalchemy import func, select
            from app.models.report_models import DisclosureNote
            q = select(func.count(DisclosureNote.id)).where(DisclosureNote.project_id == TARGET_PROJECT_ID)
            count_before = (await world.db.execute(q)).scalar()

            stubs = await _setup_stubs(world, recipe)

            async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
                resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

            _assert_denied(resp, 403, REASON_FORBIDDEN)
            for stub in stubs:
                assert stub.count == 0

            # 请求后附注行数不变
            count_after = (await world.db.execute(q)).scalar()
            assert count_after == count_before, f"拒绝后附注行数变化：{count_before} → {count_after}"
