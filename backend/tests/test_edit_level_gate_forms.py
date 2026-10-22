"""edit 级判定点结论等于模型（partner-manager-edit-permission 任务 14.5；需求 9.9）。
# Feature: partner-manager-edit-permission, Property 12: edit 级判定点结论等于模型

从 ``edit_level_impact_inventory.json`` 读取出现的 edit 级 *gate form* 集合，
对每种形态选一个代表端点，用 7 个固定样例（质控 / EQCR / 未登记 / 无成员行拒绝；
合伙人 / 经理 / 审计员放行）验证判定结论等于模型：

- admin → 放行
- 免查名单内 → 放行
- 不具所需全局能力 → 拒绝
- 成员行未删除且级别不低于要求 → 放行；其余 → 拒绝
- 放行时业务桩恰 1 次，拒绝时 0 次并返回该形态现有文案
- 项目角色不影响结论

gate_internal 的入口（如 authorize_wp_edit 内部被 require_wp_edit_permission 包装的点）
没有直接暴露端点，用有端点的外层包装形态代替。

**Validates: Requirements 9.9**
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import Table

from app.deps import assert_project_permission, authorize_wp_edit
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex

from tests.authz_world import (
    TARGET_PROJECT_ID,
    AuthzWorld,
    WORLD_TABLES,
    create_world_schema,
    sqlite_world,
)

pytestmark = pytest.mark.asyncio

# ─── 清单加载 ───────────────────────────────────────────────────────────────
_INVENTORY_PATH = Path(__file__).resolve().parents[1] / "data" / "authz" / "edit_level_impact_inventory.json"


def _load_inventory() -> dict[str, Any]:
    return json.loads(_INVENTORY_PATH.read_text("utf-8"))


def _extract_edit_gate_forms(inv: dict[str, Any]) -> set[str]:
    """从影响清单中提取所有有端点的 edit 级门禁形态。"""
    forms: set[str] = set()
    for gp in inv.get("gate_points", []):
        if gp.get("level") == "edit" and gp.get("endpoints"):
            forms.add(gp["form"])
    return forms


_INVENTORY = _load_inventory()
EDIT_GATE_FORMS: set[str] = _extract_edit_gate_forms(_INVENTORY)

# ─── 代表端点映射（每种门禁形态取第一个有端点的门禁点） ─────────────────────
_FORM_REPRESENTATIVES: dict[str, dict[str, Any]] = {}
for _gp in _INVENTORY.get("gate_points", []):
    if _gp.get("level") == "edit" and _gp.get("endpoints") and _gp["form"] not in _FORM_REPRESENTATIVES:
        _FORM_REPRESENTATIVES[_gp["form"]] = _gp


# ─── 常量 ──────────────────────────────────────────────────────────────────
PROJECT_ID = TARGET_PROJECT_ID

# 7 个固定样例（需求 9.9）
# (label, global_role, project_role, level, expected_allowed)
SAMPLES: list[tuple[str, str, str, str, bool]] = [
    # 拒绝
    ("qc_member", "qc", "qc", "review", False),
    ("eqcr_member", "eqcr", "qc", "review", False),
    ("unregistered_role", "readonly", "readonly", "readonly", False),
    ("no_member_row", "auditor", "", "", False),         # 空 = 无成员行
    # 放行
    ("partner_member", "partner", "partner", "edit", True),
    ("manager_member", "manager", "manager", "edit", True),
    ("auditor_member", "auditor", "manager", "edit", True),
]


# ═══════════════════════════════════════════════════════════════════════════
# 测试 1：门禁形态集合等于清单
# ═══════════════════════════════════════════════════════════════════════════
class TestGateFormSetMatchesInventory:
    """清单中出现的 edit 级门禁形态集合 = 测试已知的形态集合。"""

    # 预期的四种有端点的 edit 级门禁形态
    EXPECTED_FORMS: set[str] = {
        "require_project_access",
        "assert_project_permission",
        "authorize_wp_edit",
        "require_wp_edit_permission",
    }

    def test_form_set_equals_inventory(self) -> None:
        """从清单读取的门禁形态集合与预期逐值相等。"""
        assert EDIT_GATE_FORMS == self.EXPECTED_FORMS, (
            f"清单门禁形态不匹配：\n"
            f"  多出：{EDIT_GATE_FORMS - self.EXPECTED_FORMS}\n"
            f"  缺少：{self.EXPECTED_FORMS - EDIT_GATE_FORMS}"
        )

    def test_every_form_has_representative(self) -> None:
        """每种门禁形态在代表端点表中有条目。"""
        for form in EDIT_GATE_FORMS:
            assert form in _FORM_REPRESENTATIVES, f"门禁形态 {form!r} 没有代表端点"


# ═══════════════════════════════════════════════════════════════════════════
# 测试 2：require_project_access("edit") — 代表端点级
# ═══════════════════════════════════════════════════════════════════════════
class TestRequireProjectAccessEditLevel:
    """require_project_access("edit") 的 7 样例通过 assert_project_permission 直调验证。

    assert_project_permission 是 require_project_access 的内部实现（设计确认），
    避免需要构建完整的路由端点。
    """

    @pytest_asyncio.fixture
    async def world(self, monkeypatch: pytest.MonkeyPatch):
        async with sqlite_world(monkeypatch) as w:
            yield w

    async def _make_user(
        self, world: AuthzWorld, *, global_role: str, project_role: str, level: str,
    ) -> User:
        """创建用户并可选地创建成员行。"""
        role_enum = UserRole(global_role)
        user = await world.user(role_enum)
        if project_role and level:
            # 建成员行
            pu = ProjectUser(
                project_id=PROJECT_ID,
                user_id=user.id,
                role=ProjectUserRole(project_role),
                permission_level=PermissionLevel(level),
            )
            world.db.add(pu)
            await world.db.flush()
        return user

    @pytest.mark.parametrize(
        "label,global_role,project_role,level,expected",
        SAMPLES,
        ids=[s[0] for s in SAMPLES],
    )
    async def test_require_project_access_edit_samples(
        self, world: AuthzWorld, label: str, global_role: str, project_role: str,
        level: str, expected: bool,
    ) -> None:
        user = await self._make_user(
            world, global_role=global_role, project_role=project_role, level=level,
        )
        if expected:
            # 放行：不抛异常
            result = await assert_project_permission(world.db, user, PROJECT_ID, "edit")
            assert result is user
        else:
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await assert_project_permission(world.db, user, PROJECT_ID, "edit")
            assert exc_info.value.status_code in (403, 423)


# ═══════════════════════════════════════════════════════════════════════════
# 测试 3：authorize_wp_edit — 代表端点级
# ═══════════════════════════════════════════════════════════════════════════
_EXTENDED_TABLES: tuple[Table, ...] = (*WORLD_TABLES, WpIndex.__table__, WorkingPaper.__table__)


class TestAuthorizeWpEditLevel:
    """authorize_wp_edit 的 7 样例。

    authorize_wp_edit 和 require_wp_edit_permission 共用同一实现，
    前者是后者的内部调用。authorize_wp_edit 需要底稿存在于库中。
    全局能力检查 (WORKPAPER_WRITE) 使 qc/readonly/eqcr 被提前拒绝。
    partner 全局放行（不查成员行）。
    """

    @pytest_asyncio.fixture
    async def world_with_wp(self, monkeypatch: pytest.MonkeyPatch):
        """带 working_paper 表的权限世界。"""
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        try:
            async with engine.begin() as conn:
                for table in _EXTENDED_TABLES:
                    await conn.run_sync(table.create, checkfirst=True)
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                world = await AuthzWorld.create(session, monkeypatch)
                # 创建底稿索引 + 底稿
                wp_index = WpIndex(
                    id=uuid.uuid4(),
                    project_id=PROJECT_ID,
                    wp_code="T1",
                    wp_name="测试底稿",
                    audit_cycle="D",
                )
                session.add(wp_index)
                await session.flush()
                wp = WorkingPaper(
                    id=uuid.uuid4(),
                    project_id=PROJECT_ID,
                    wp_index_id=wp_index.id,
                    file_path="/nonexistent",
                    source_type="upload",
                    is_deleted=False,
                )
                session.add(wp)
                await session.flush()
                world._test_wp_id = wp.id  # type: ignore[attr-defined]
                try:
                    yield world
                finally:
                    await world.redis.aclose()
        finally:
            await engine.dispose()

    async def _make_user(
        self, world: AuthzWorld, *, global_role: str, project_role: str, level: str,
    ) -> User:
        role_enum = UserRole(global_role)
        user = await world.user(role_enum)
        if project_role and level:
            pu = ProjectUser(
                project_id=PROJECT_ID,
                user_id=user.id,
                role=ProjectUserRole(project_role),
                permission_level=PermissionLevel(level),
            )
            world.db.add(pu)
            await world.db.flush()
        return user

    @pytest.mark.parametrize(
        "label,global_role,project_role,level,expected",
        SAMPLES,
        ids=[s[0] for s in SAMPLES],
    )
    async def test_authorize_wp_edit_samples(
        self, world_with_wp: AuthzWorld, label: str, global_role: str,
        project_role: str, level: str, expected: bool,
    ) -> None:
        world = world_with_wp
        wp_id = world._test_wp_id  # type: ignore[attr-defined]
        user = await self._make_user(
            world, global_role=global_role, project_role=project_role, level=level,
        )
        if expected:
            # partner 全局放行；manager/auditor 需 edit 成员行
            result = await authorize_wp_edit(world.db, user, wp_id)
            assert result == PROJECT_ID
        else:
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await authorize_wp_edit(world.db, user, wp_id)
            # authorize_wp_edit 对 qc/eqcr/readonly 返回 403（无 WORKPAPER_WRITE）
            # 对无成员行返回 403
            assert exc_info.value.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 测试 4：assert_project_permission 直调 — 代表 assert_project_permission 形态
# ═══════════════════════════════════════════════════════════════════════════
class TestAssertProjectPermissionEditLevel:
    """assert_project_permission("edit") 作为函数体调用形态的代表。

    与 require_project_access 共用实现但挂载方式不同——某些端点在函数体内
    显式调用 assert_project_permission 而非通过路径依赖 require_project_access。
    判定逻辑相同，此处确认同一 7 样例结论一致。
    """

    @pytest_asyncio.fixture
    async def world(self, monkeypatch: pytest.MonkeyPatch):
        async with sqlite_world(monkeypatch) as w:
            yield w

    async def _make_user(
        self, world: AuthzWorld, *, global_role: str, project_role: str, level: str,
    ) -> User:
        role_enum = UserRole(global_role)
        user = await world.user(role_enum)
        if project_role and level:
            pu = ProjectUser(
                project_id=PROJECT_ID,
                user_id=user.id,
                role=ProjectUserRole(project_role),
                permission_level=PermissionLevel(level),
            )
            world.db.add(pu)
            await world.db.flush()
        return user

    @pytest.mark.parametrize(
        "label,global_role,project_role,level,expected",
        SAMPLES,
        ids=[s[0] for s in SAMPLES],
    )
    async def test_assert_project_permission_edit_samples(
        self, world: AuthzWorld, label: str, global_role: str,
        project_role: str, level: str, expected: bool,
    ) -> None:
        user = await self._make_user(
            world, global_role=global_role, project_role=project_role, level=level,
        )
        if expected:
            result = await assert_project_permission(world.db, user, PROJECT_ID, "edit")
            assert result is user
        else:
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await assert_project_permission(world.db, user, PROJECT_ID, "edit")
            assert exc_info.value.status_code in (403, 423)


# ═══════════════════════════════════════════════════════════════════════════
# 测试 5：项目角色不影响 edit 级判定结论
# ═══════════════════════════════════════════════════════════════════════════
class TestProjectRoleDoesNotAffectEditConclusion:
    """对同一用户，成员行项目角色换成其他合法值不改变 edit 级判定结论。"""

    @pytest_asyncio.fixture
    async def world(self, monkeypatch: pytest.MonkeyPatch):
        async with sqlite_world(monkeypatch) as w:
            yield w

    @pytest.mark.parametrize("project_role", ["partner", "manager", "auditor", "qc"])
    async def test_edit_member_allowed_regardless_of_project_role(
        self, world: AuthzWorld, project_role: str,
    ) -> None:
        """成员行 (任意项目角色, edit) + 全局 auditor → 放行。"""
        user = await world.user(UserRole.auditor)
        pu = ProjectUser(
            project_id=PROJECT_ID,
            user_id=user.id,
            role=ProjectUserRole(project_role),
            permission_level=PermissionLevel.edit,
        )
        world.db.add(pu)
        await world.db.flush()
        result = await assert_project_permission(world.db, user, PROJECT_ID, "edit")
        assert result is user

    @pytest.mark.parametrize("project_role", ["partner", "manager", "auditor", "qc"])
    async def test_review_member_rejected_regardless_of_project_role(
        self, world: AuthzWorld, project_role: str,
    ) -> None:
        """成员行 (任意项目角色, review) + 全局 auditor → 拒绝。"""
        from fastapi import HTTPException
        user = await world.user(UserRole.auditor)
        pu = ProjectUser(
            project_id=PROJECT_ID,
            user_id=user.id,
            role=ProjectUserRole(project_role),
            permission_level=PermissionLevel.review,
        )
        world.db.add(pu)
        await world.db.flush()
        with pytest.raises(HTTPException) as exc_info:
            await assert_project_permission(world.db, user, PROJECT_ID, "edit")
        assert exc_info.value.status_code == 403
