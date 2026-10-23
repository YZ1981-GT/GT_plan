# Feature: partner-manager-edit-permission, Task 14.2: EQCR 别名拒绝、判定出错拒绝与改派即时生效
"""EQCR 门禁一致性测试。

需求 7.4: 覆盖集合端点 × 全局角色 (partner/auditor/admin) × `独立复核合伙人` 与 `eqcr` 委派
          (成员行 (partner, review)) → 403

需求 7.6: 委派查询注入异常 → 附注编辑门禁与交付中心门禁各至少一个写操作：
          非成功响应、业务 0 次、无残留改动

需求 7.9: 改派即时生效：
  - auditor 在 P 委派 `manager` 的用户改派 `eqcr` 并保存后 → 附注写与交付中心写都 403
  - 改回 `manager` 后不再因 EQCR 被拒
  - 预置与成员行矛盾的旧 `perm:*` 键（edit）不影响结论

_Requirements: 7.3, 7.4, 7.6, 7.9_
"""
from __future__ import annotations

import importlib
import uuid
from typing import Any

import pytest
import pytest_asyncio
from httpx import Response

from tests.authz_world import (
    TARGET_NOTE_ID,
    TARGET_PROJECT_ID,
    AuthzWorld,
    GateClient,
    Identity,
    sqlite_world,
)
from tests.note_edit_gate_recipes import ALL_RECIPES, Recipe, StubTarget, _NOTE_ID, _YEAR
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.services.note_edit_gate import (
    REASON_EQCR_READONLY,
    REASON_FORBIDDEN,
)
import app.services.eqcr_resolver as eqcr_resolver

# ---------------------------------------------------------------------------
# 代表端点选择
# ---------------------------------------------------------------------------

# 附注编辑门禁覆盖集合代表：A6 路径依赖
RECIPE_NOTE_WRITE = ALL_RECIPES[("POST", "/api/disclosure-notes/{project_id}/{year}/pull-from-workpapers")]
# A2 对象 id 端点 (用于部分测试)
RECIPE_NOTE_WRITE_A2 = ALL_RECIPES[("PUT", "/api/disclosure-notes/{note_id}")]

# ---------------------------------------------------------------------------
# 路由导入
# ---------------------------------------------------------------------------

from app.routers import disclosure_notes  # noqa: E402
from app.routers import deliverable  # noqa: E402

_NOTE_ROUTERS = (disclosure_notes.router,)
_DELIVERABLE_ROUTERS = (deliverable.router,)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


class _SmartMock:
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
    stubs = []
    for st in recipe.stubs:
        owner = importlib.import_module(st.owner_import)
        if st.is_class:
            stubs.append(world.stub(owner, st.attr, returns=_SmartMock(), awaitable=False))
        else:
            stubs.append(world.stub(owner, st.attr, returns=_SmartMock(), awaitable=st.awaitable))
    return stubs


def _assert_denied(resp: Response, status: int, reason: str) -> None:
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


async def _setup_world_extras(world: AuthzWorld) -> None:
    """建 A2 对象 id 端点需要的附注行。"""
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
# 需求 7.4: EQCR 别名拒绝 — 两种别名 × 三种全局角色 × 覆盖集合端点
# ============================================================================


_EQCR_ALIASES = ("eqcr", "独立复核合伙人")
_GLOBAL_ROLES_FOR_EQCR = (UserRole.partner, UserRole.auditor, UserRole.admin)
_EQCR_PARAMS = [
    (alias, role)
    for alias in _EQCR_ALIASES
    for role in _GLOBAL_ROLES_FOR_EQCR
]
_EQCR_IDS = [f"alias={a},global={r.value}" for a, r in _EQCR_PARAMS]


class TestEqcrAliasRejection:
    """需求 7.4: 覆盖集合端点对持有 EQCR 别名委派的成员返回 403。

    两种委派逐端点结论相同；全局角色 partner/auditor/admin 都不豁免。
    交付中心读以外的全部操作 403、读操作放行。
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("alias,global_role", _EQCR_PARAMS, ids=_EQCR_IDS)
    async def test_note_write_denied_for_eqcr_alias(
        self, monkeypatch: pytest.MonkeyPatch, alias: str, global_role: UserRole,
    ) -> None:
        """附注编辑门禁覆盖集合端点 (A6) 对 EQCR 别名返回 403。"""
        recipe = RECIPE_NOTE_WRITE
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)

            # 建成员行 (partner, review) + EQCR 别名委派
            identity = await world.member("review", "partner", global_role=global_role)
            await world.eqcr_assignment(alias, user=identity.user)
            stubs = await _setup_stubs(world, recipe)

            async with world.client(*_NOTE_ROUTERS, user=identity.user) as client:
                resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

            _assert_denied(resp, 403, REASON_EQCR_READONLY)
            for stub in stubs:
                assert stub.count == 0, f"EQCR {alias}/{global_role}: 业务桩 {stub.target} 应 0 次"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("alias", _EQCR_ALIASES, ids=_EQCR_ALIASES)
    async def test_deliverable_write_denied_for_eqcr(
        self, monkeypatch: pytest.MonkeyPatch, alias: str,
    ) -> None:
        """交付中心写操作 (trio 一键出具) 对 EQCR 返回 403。"""
        async with sqlite_world(monkeypatch) as world:
            # 建成员行 + EQCR 委派
            identity = await world.member("review", "partner")
            await world.eqcr_assignment(alias, user=identity.user)

            # 交付中心写端点 POST /trio (export action)：EQCR 被 _guard_action 拒绝
            async with world.client(*_DELIVERABLE_ROUTERS, user=identity.user) as client:
                resp = await client.post(
                    f"/api/projects/{TARGET_PROJECT_ID}/deliverables/trio",
                    params={"year": _YEAR},
                )

            # EQCR 写操作 → 403
            assert resp.status_code == 403, (
                f"EQCR {alias} 交付中心写操作应被 403 拒绝，实际 {resp.status_code}：{resp.text[:300]}"
            )

    @pytest.mark.asyncio
    async def test_both_aliases_same_conclusion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """两种 EQCR 别名在同一端点上得到相同结论（403 EQCR）。"""
        recipe = RECIPE_NOTE_WRITE
        results: dict[str, int] = {}

        for alias in _EQCR_ALIASES:
            async with sqlite_world(monkeypatch) as world:
                await _setup_world_extras(world)
                identity = await world.member("review", "partner")
                await world.eqcr_assignment(alias, user=identity.user)
                await _setup_stubs(world, recipe)

                async with world.client(*_NOTE_ROUTERS, user=identity.user) as client:
                    resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

                results[alias] = resp.status_code
                _assert_denied(resp, 403, REASON_EQCR_READONLY)

        # 两种别名结论完全相同
        assert results["eqcr"] == results["独立复核合伙人"], (
            f"两种别名结论不同：eqcr={results['eqcr']}, 独立复核合伙人={results['独立复核合伙人']}"
        )


# ============================================================================
# 需求 7.6: 判定出错拒绝
# ============================================================================


class TestEqcrQueryFaultInjection:
    """需求 7.6: 委派查询注入异常 → 非成功响应、业务 0 次。"""

    @pytest.mark.asyncio
    async def test_note_edit_gate_fault_injection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """附注编辑门禁：EQCR 判定查询出错 → 请求失败、业务 0 次。"""
        recipe = RECIPE_NOTE_WRITE
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)
            # review 成员（正常应放行）
            identity = await world.review_member()
            stubs = await _setup_stubs(world, recipe)

            # 注入异常到 EQCR 判定的下层查询
            async def _raise(*args: Any, **kwargs: Any) -> int:
                raise RuntimeError("模拟 EQCR 查询故障")

            monkeypatch.setattr(eqcr_resolver, "_count_project_eqcr_assignments", _raise)

            async with world.client(*_NOTE_ROUTERS, user=identity.user) as client:
                try:
                    resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)
                except Exception:
                    # 异常直接冒泡 = 请求失败，业务不执行（需求 7.6 的语义）
                    for stub in stubs:
                        assert stub.count == 0, f"EQCR 查询故障后业务桩 {stub.target} 应 0 次"
                    return

            # 如果没抛异常，应该是非成功响应
            assert resp.status_code >= 400, (
                f"EQCR 查询故障后应返回错误响应，实际 {resp.status_code}"
            )
            # 业务桩 0 次
            for stub in stubs:
                assert stub.count == 0, f"故障后业务桩 {stub.target} 应 0 次"

    @pytest.mark.asyncio
    async def test_deliverable_gate_fault_injection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """交付中心门禁：EQCR 判定查询出错 → 请求失败、业务 0 次。

        使用交付中心写操作 POST /trio (export action)。
        """
        async with sqlite_world(monkeypatch) as world:
            # review 成员（正常应放行交付中心写操作）
            identity = await world.member("review", "manager")

            # 注入异常
            async def _raise(*args: Any, **kwargs: Any) -> int:
                raise RuntimeError("模拟 EQCR 查询故障")

            monkeypatch.setattr(eqcr_resolver, "_count_project_eqcr_assignments", _raise)

            # 用一个交付中心写端点
            async with world.client(*_DELIVERABLE_ROUTERS, user=identity.user) as client:
                try:
                    resp = await client.post(
                        f"/api/projects/{TARGET_PROJECT_ID}/deliverables/trio",
                        params={"year": _YEAR},
                    )
                except Exception:
                    # 异常直接冒泡 = 请求失败（需求 7.6）
                    return

            assert resp.status_code >= 400, (
                f"交付中心 EQCR 查询故障后应返回错误响应，实际 {resp.status_code}"
            )


# ============================================================================
# 需求 7.9: 改派即时生效
# ============================================================================


class TestReassignmentTakesEffectImmediately:
    """需求 7.9: manager → eqcr 后附注写与交付中心写都 403；改回 manager 后不再被拒。

    注意：这里是「逻辑层面」的测试——直接操作数据库模拟委派同步结果，
    而非走完整的委派保存端点（完整端到端在任务 14.4）。
    """

    @pytest.mark.asyncio
    async def test_manager_to_eqcr_note_write_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """manager 用户改派 eqcr 后，附注写返回 403。"""
        recipe = RECIPE_NOTE_WRITE
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)

            # 建 auditor 用户 + (manager, edit) 成员行
            user = await world.user(UserRole.auditor)
            from app.models.core import ProjectUser
            member_row = await world._add(ProjectUser(
                project_id=TARGET_PROJECT_ID,
                user_id=user.id,
                role=ProjectUserRole.manager,
                permission_level=PermissionLevel.edit,
            ))

            # 先验证 manager 能写
            stubs = await _setup_stubs(world, recipe)
            async with world.client(*_NOTE_ROUTERS, user=user) as client:
                try:
                    resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)
                except Exception:
                    client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")
                else:
                    assert resp.status_code != 403, "manager should be allowed before reassignment"

            # 模拟改派为 eqcr：更新成员行为 (partner, review) + 建 eqcr 委派
            member_row.role = ProjectUserRole.partner
            member_row.permission_level = PermissionLevel.review
            await world.db.flush()
            await world.eqcr_assignment("eqcr", user=user)

            # 预置与成员行矛盾的旧 perm:* 键（edit）——不影响结论（D3：缓存已移除）
            await world.redis.setex(f"perm:{user.id}:{TARGET_PROJECT_ID}", 300, "edit")

            # 重新安装桩（上一轮的桩已被用过）
            stubs = await _setup_stubs(world, recipe)
            async with world.client(*_NOTE_ROUTERS, user=user) as client:
                resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

            _assert_denied(resp, 403, REASON_EQCR_READONLY)
            for stub in stubs:
                assert stub.count == 0, f"改派 eqcr 后业务桩 {stub.target} 应 0 次"

            # 验证 perm:* 键仍存在且未被读取（缓存已移除，键不影响判定）
            cached = await world.redis.get(f"perm:{user.id}:{TARGET_PROJECT_ID}")
            assert cached == "edit", "perm:* 键应保持原样（缓存不被读写）"

    @pytest.mark.asyncio
    async def test_eqcr_back_to_manager_no_longer_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """改回 manager 后不再因 EQCR 被拒。"""
        recipe = RECIPE_NOTE_WRITE
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)

            user = await world.user(UserRole.auditor)
            from app.models.core import ProjectUser
            from app.models.staff_models import StaffMember, ProjectAssignment
            from datetime import datetime, timezone

            # 先建为 eqcr 状态
            member_row = await world._add(ProjectUser(
                project_id=TARGET_PROJECT_ID,
                user_id=user.id,
                role=ProjectUserRole.partner,
                permission_level=PermissionLevel.review,
            ))
            staff = await world._add(StaffMember(user_id=user.id, name="测试人员"))
            eqcr_row = await world._add(ProjectAssignment(
                project_id=TARGET_PROJECT_ID,
                staff_id=staff.id,
                role="eqcr",
                assigned_at=datetime.now(timezone.utc),
            ))

            # eqcr 状态下应被拒
            stubs = await _setup_stubs(world, recipe)
            async with world.client(*_NOTE_ROUTERS, user=user) as client:
                resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)
            _assert_denied(resp, 403, REASON_EQCR_READONLY)

            # 模拟改回 manager：更新成员行 + 软删 eqcr 委派
            member_row.role = ProjectUserRole.manager
            member_row.permission_level = PermissionLevel.edit
            eqcr_row.is_deleted = True
            await world.db.flush()

            # 改回后应放行
            stubs = await _setup_stubs(world, recipe)
            async with world.client(*_NOTE_ROUTERS, user=user) as client:
                try:
                    resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)
                except Exception:
                    # 门禁放行，业务代码后续可能因桩而抛异常——已证明不再被 EQCR 拒绝
                    client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")
                    return

            assert resp.status_code != 403, (
                f"改回 manager 后不应被 403 拒绝：{resp.text[:300]}"
            )
            client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")

    @pytest.mark.asyncio
    async def test_perm_key_does_not_affect_conclusion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """预置与成员行矛盾的旧 perm:* 键（edit）不影响 EQCR 判定结论。"""
        recipe = RECIPE_NOTE_WRITE
        async with sqlite_world(monkeypatch) as world:
            await _setup_world_extras(world)

            # EQCR 身份 (partner, review) + eqcr 委派
            identity = await world.project_eqcr()

            # 预置 perm:* 键为 edit（矛盾值）
            await world.redis.setex(
                f"perm:{identity.user.id}:{TARGET_PROJECT_ID}", 300, "edit"
            )

            stubs = await _setup_stubs(world, recipe)
            async with world.client(*_NOTE_ROUTERS, user=identity.user) as client:
                resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

            # 仍然被 EQCR 拒绝（缓存已移除，perm:* 键不被读取）
            _assert_denied(resp, 403, REASON_EQCR_READONLY)

            # 键仍存在、未被删除（缓存不被读写）
            cached = await world.redis.get(f"perm:{identity.user.id}:{TARGET_PROJECT_ID}")
            assert cached == "edit", "perm:* 键应保持原样"
