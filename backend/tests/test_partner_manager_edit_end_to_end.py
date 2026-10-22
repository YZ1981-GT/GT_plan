"""合伙人 / 经理升 edit 的全平台端到端测试（partner-manager-edit-permission 任务 14.4；需求 9.2、9.3、9.6）。

# Feature: partner-manager-edit-permission, Property: 合伙人/经理升 edit 全平台 E2E

**完整管线**：``AssignmentService.save_assignments`` 的核心路径（``_sync_project_users``）→ 权限判定，
全部走生产代码（权限世界），不预建成员行。

为避免 ``save_assignments`` 的可见性 epoch（``wp_visibility_policy_epoch``）等副作用表不在 SQLite
权限世界中，本文件直接调用 ``_sync_project_users``（E2E 管线的核心：建委派 → 同步成员行 → 判定）。
这与生产管线的差异只在于跳过 SOD 校验和通知——这些与权限判定无关。

代表端点：
- ``assert_project_permission(..., "edit")`` — 调整分录等 edit 级操作的判定入口
- ``authorize_wp_edit`` — 底稿编辑权判定

**需求 9.2**：合伙人 / 经理 5 个别名各经委派同步产生 edit 成员行 → 判定放行；
  全局 auditor+manager、全局 qc+合伙人委派 → 各测一次。
**需求 9.3**：qc / 质控 / eqcr / 独立复核合伙人 / 观察员 各一次拒绝；
  改派从 (manager, edit) → eqcr / 质控 / 未登记 → 拒绝。
**需求 9.6**：全局 partner 无成员行 → authorize_wp_edit 放行；
  全局 qc + (manager, edit) 成员行 → 「无底稿编辑权限」。
"""
from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.deps import assert_project_permission, authorize_wp_edit
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.assignment_service import (
    AssignmentService,
    ROLE_MAP,
    UNMAPPED_ROLE,
    map_assignment_role,
    resolve_member_mapping,
)
from app.services.note_edit_gate import assert_note_edit_access
from tests.authz_world import TARGET_PROJECT_ID, AuthzWorld, WORLD_TABLES, create_world_schema, sqlite_world

pytestmark = pytest.mark.asyncio

# ─── 常量 ─────────────────────────────────────────────────────────────────────

PROJECT_ID = TARGET_PROJECT_ID

# 合伙人 / 经理别名（需求 2.1）
PARTNER_MANAGER_ALIASES = ("signing_partner", "partner", "合伙人", "manager", "项目经理")

# 被拒绝的角色（需求 9.3）
REJECTED_ROLES = ("qc", "质控", "eqcr", "独立复核合伙人", "观察员")

# 权限世界 + working_paper / wp_index 表（authorize_wp_edit 需要反查底稿所属项目）
_EXTENDED_TABLES: tuple[Table, ...] = (*WORLD_TABLES, WpIndex.__table__, WorkingPaper.__table__)


@contextlib.asynccontextmanager
async def _extended_sqlite_world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AuthzWorld]:
    """SQLite 内存库版权限世界，额外包含 working_paper 表（供 authorize_wp_edit 测试用）。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with engine.begin() as conn:
            for table in _EXTENDED_TABLES:
                await conn.run_sync(table.create, checkfirst=True)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            world = await AuthzWorld.create(session, monkeypatch)
            try:
                yield world
            finally:
                await world.redis.aclose()
    finally:
        await engine.dispose()


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

async def _user(db: AsyncSession, *, global_role: UserRole = UserRole.auditor) -> User:
    tag = uuid.uuid4().hex[:8]
    user = User(username=f"e2e-{tag}", email=f"{tag}@e2e.test", hashed_password="x",
                role=global_role, is_active=True)
    db.add(user)
    await db.flush()
    return user


async def _staff(db: AsyncSession, user: User) -> StaffMember:
    sm = StaffMember(user_id=user.id, name=f"e2e-staff-{uuid.uuid4().hex[:6]}")
    db.add(sm)
    await db.flush()
    return sm


async def _workpaper(db: AsyncSession, project_id: uuid.UUID) -> WorkingPaper:
    """为 authorize_wp_edit 测试建一条底稿记录（含必需的 wp_index 行）。"""
    wpi = WpIndex(id=uuid.uuid4(), project_id=project_id, wp_code="E2E-TEST", wp_name="E2E 测试底稿")
    db.add(wpi)
    await db.flush()
    wp = WorkingPaper(
        id=uuid.uuid4(), project_id=project_id, wp_index_id=wpi.id,
        file_path="/nonexistent", source_type="upload",
    )
    db.add(wp)
    await db.flush()
    return wp


async def _delegate_and_sync(
    db: AsyncSession, project_id: uuid.UUID,
    batch: list[tuple[StaffMember, str]],
) -> None:
    """建委派 + 调 _sync_project_users（生产代码管线核心），不经 save_assignments 的可见性 epoch。"""
    now = datetime.now(timezone.utc)
    # 先软删本项目现有委派
    await db.execute(
        sa.update(ProjectAssignment).where(
            ProjectAssignment.project_id == project_id,
            ProjectAssignment.is_deleted == False,  # noqa: E712
        ).values(is_deleted=True, deleted_at=now)
    )
    # 建新委派
    created: list[ProjectAssignment] = []
    for sm, role in batch:
        pa = ProjectAssignment(
            project_id=project_id, staff_id=sm.id, role=role, assigned_at=now,
        )
        db.add(pa)
        created.append(pa)
    await db.flush()
    # 经 _sync_project_users 同步成员行（生产代码）
    svc = AssignmentService(db)
    await svc._sync_project_users(project_id, created)
    await db.flush()


async def _get_member(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> ProjectUser | None:
    return (await db.execute(
        sa.select(ProjectUser).where(
            ProjectUser.project_id == project_id,
            ProjectUser.user_id == user_id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    )).scalar_one_or_none()


async def _check_edit(db: AsyncSession, user: User, project_id: uuid.UUID) -> bool:
    """assert_project_permission(..., "edit") → True=放行 / False=403。"""
    try:
        await assert_project_permission(db, user, project_id, "edit")
        return True
    except HTTPException as exc:
        if exc.status_code == 403:
            return False
        raise


async def _check_review(db: AsyncSession, user: User, project_id: uuid.UUID) -> bool:
    try:
        await assert_project_permission(db, user, project_id, "review")
        return True
    except HTTPException as exc:
        if exc.status_code == 403:
            return False
        raise


async def _check_wp_edit(db: AsyncSession, user: User, wp_id: uuid.UUID) -> tuple[bool, str]:
    """authorize_wp_edit → (True, "") / (False, detail)。"""
    try:
        await authorize_wp_edit(db, user, wp_id)
        return True, ""
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            return False, exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        raise


async def _check_note_edit(db: AsyncSession, user: User, project_id: uuid.UUID) -> bool:
    try:
        await assert_note_edit_access(db, user, project_id, consol_lock=False)
        return True
    except HTTPException as exc:
        if exc.status_code in (403, 423):
            return False
        raise


# ═══ 需求 9.2：合伙人 / 经理别名经委派保存 → 成员行 edit → 判定放行 ═══════════


class TestPartnerManagerAliasesGetEdit:
    """5 个别名各走一次 _sync_project_users 全管线，验证成员行为 edit、判定放行。"""

    @pytest.mark.parametrize("alias", PARTNER_MANAGER_ALIASES, ids=PARTNER_MANAGER_ALIASES)
    async def test_delegation_alias_creates_edit_member(
        self, monkeypatch: pytest.MonkeyPatch, alias: str,
    ) -> None:
        async with sqlite_world(monkeypatch) as world:
            user = await _user(world.db)
            sm = await _staff(world.db, user)

            # 经委派同步（生产管线）
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, alias)])

            # 验证成员行
            member = await _get_member(world.db, user.id, PROJECT_ID)
            assert member is not None, f"别名 {alias!r} 未产生成员行"
            expected_role, expected_level = map_assignment_role(alias)
            assert member.role == expected_role, f"项目角色：期望 {expected_role}，实际 {member.role}"
            assert member.permission_level == expected_level, f"级别：期望 {expected_level}，实际 {member.permission_level}"
            assert member.permission_level == PermissionLevel.edit

            # assert_project_permission("edit") 放行
            assert await _check_edit(world.db, user, PROJECT_ID) is True


class TestPartnerManagerViaEndpoint:
    """需求 9.2 的 authorize_wp_edit 端点覆盖：合伙人别名经委派后能编辑底稿。"""

    async def test_partner_delegation_allows_wp_edit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async with _extended_sqlite_world(monkeypatch) as world:
            user = await _user(world.db, global_role=UserRole.auditor)
            sm = await _staff(world.db, user)
            wp = await _workpaper(world.db, PROJECT_ID)

            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, "partner")])
            allowed, _ = await _check_wp_edit(world.db, user, wp.id)
            assert allowed is True

    async def test_manager_delegation_allows_wp_edit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async with _extended_sqlite_world(monkeypatch) as world:
            user = await _user(world.db, global_role=UserRole.auditor)
            sm = await _staff(world.db, user)
            wp = await _workpaper(world.db, PROJECT_ID)

            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, "项目经理")])
            allowed, _ = await _check_wp_edit(world.db, user, wp.id)
            assert allowed is True


# ═══ 需求 9.2 补充：全局 auditor+manager 委派 / 全局 qc+合伙人委派 ═══════════


class TestGlobalRoleCombinations:

    async def test_global_auditor_with_manager_delegation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """全局 auditor、委派为 manager：成员行 edit，edit 级放行。"""
        async with sqlite_world(monkeypatch) as world:
            user = await _user(world.db, global_role=UserRole.auditor)
            sm = await _staff(world.db, user)
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, "manager")])
            assert await _check_edit(world.db, user, PROJECT_ID) is True

    async def test_global_manager_with_partner_delegation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """全局 auditor，委派为 partner：成员行 (partner, edit)，edit 级放行。"""
        async with sqlite_world(monkeypatch) as world:
            user = await _user(world.db, global_role=UserRole.auditor)
            sm = await _staff(world.db, user)
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, "partner")])
            member = await _get_member(world.db, user.id, PROJECT_ID)
            assert member is not None
            assert member.role == ProjectUserRole.partner
            assert member.permission_level == PermissionLevel.edit
            assert await _check_edit(world.db, user, PROJECT_ID) is True

    async def test_global_qc_with_partner_delegation_member_is_edit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """全局 qc、委派为合伙人：成员行 (partner, edit)，
        require_project_access("edit") 放行，但 authorize_wp_edit 因全局角色 qc 无 WORKPAPER_WRITE 而拒绝。"""
        async with _extended_sqlite_world(monkeypatch) as world:
            user = await _user(world.db, global_role=UserRole.qc)
            sm = await _staff(world.db, user)
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, "合伙人")])
            member = await _get_member(world.db, user.id, PROJECT_ID)
            assert member is not None
            assert member.permission_level == PermissionLevel.edit
            # require_project_access("edit") 只看成员行级别 → 放行
            assert await _check_edit(world.db, user, PROJECT_ID) is True
            # authorize_wp_edit 先检查全局角色 WORKPAPER_WRITE 能力 → qc 无此能力 → 拒绝
            wp = await _workpaper(world.db, PROJECT_ID)
            allowed, detail = await _check_wp_edit(world.db, user, wp.id)
            assert allowed is False
            assert "无底稿编辑权限" in detail


# ═══ 需求 9.3：被拒绝的角色 ══════════════════════════════════════════════════


class TestRejectedRoles:
    """qc / 质控 / eqcr / 独立复核合伙人 / 观察员 各一次拒绝。"""

    @pytest.mark.parametrize("role", REJECTED_ROLES, ids=REJECTED_ROLES)
    async def test_non_edit_role_denied_edit_level(
        self, monkeypatch: pytest.MonkeyPatch, role: str,
    ) -> None:
        async with sqlite_world(monkeypatch) as world:
            user = await _user(world.db)
            sm = await _staff(world.db, user)
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, role)])

            member = await _get_member(world.db, user.id, PROJECT_ID)
            expected_role, expected_level = map_assignment_role(role)
            if member is None:
                # 未登记角色（如 观察员）→ (readonly, readonly) 的新成员行
                assert expected_level == PermissionLevel.readonly
            else:
                assert member.permission_level == expected_level

            # edit 级判定被拒
            assert await _check_edit(world.db, user, PROJECT_ID) is False


class TestReassignmentFromEditDenied:
    """需求 9.3：改派从 (manager, edit) → eqcr / 质控 / 未登记角色 → 被拒绝。"""

    @pytest.mark.parametrize("new_role,label", [
        ("eqcr", "改派为 EQCR"),
        ("质控", "改派为质控"),
        ("观察员", "改派为未登记角色"),
    ])
    async def test_reassignment_from_edit_denied(
        self, monkeypatch: pytest.MonkeyPatch, new_role: str, label: str,
    ) -> None:
        async with sqlite_world(monkeypatch) as world:
            user = await _user(world.db)
            sm = await _staff(world.db, user)

            # 初始委派为 manager → 成员行 (manager, edit)
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, "manager")])
            member = await _get_member(world.db, user.id, PROJECT_ID)
            assert member is not None
            assert member.permission_level == PermissionLevel.edit
            assert await _check_edit(world.db, user, PROJECT_ID) is True

            # 改派
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, new_role)])
            member = await _get_member(world.db, user.id, PROJECT_ID)
            assert member is not None
            expected_role, expected_level = map_assignment_role(new_role)
            assert member.permission_level == expected_level

            # edit 级判定被拒
            assert await _check_edit(world.db, user, PROJECT_ID) is False


# ═══ 需求 9.6：全局 partner 无成员行 / 全局 qc + (manager, edit) ═══════════


class TestGlobalRoleEdgeCases:

    async def test_global_partner_no_member_wp_edit_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """需求 9.6：全局 partner、没有成员行 → authorize_wp_edit 放行（partner 全局放行）。"""
        async with _extended_sqlite_world(monkeypatch) as world:
            user = await _user(world.db, global_role=UserRole.partner)
            # 不建成员行，不做委派
            wp = await _workpaper(world.db, PROJECT_ID)

            allowed, _ = await _check_wp_edit(world.db, user, wp.id)
            assert allowed is True

    async def test_global_qc_with_edit_member_wp_edit_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """需求 9.6：全局 qc、成员行 (manager, edit) → authorize_wp_edit 返回「无底稿编辑权限」。

        authorize_wp_edit 先检查 WORKPAPER_WRITE 能力，qc 无此能力 → 403 在成员行检查之前。
        """
        async with _extended_sqlite_world(monkeypatch) as world:
            user = await _user(world.db, global_role=UserRole.qc)
            sm = await _staff(world.db, user)
            # 委派为 manager → 成员行 (manager, edit)
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, "manager")])
            member = await _get_member(world.db, user.id, PROJECT_ID)
            assert member is not None
            assert member.permission_level == PermissionLevel.edit

            wp = await _workpaper(world.db, PROJECT_ID)
            allowed, detail = await _check_wp_edit(world.db, user, wp.id)
            assert allowed is False
            assert "无底稿编辑权限" in detail


# ═══ 需求 9.3 补充：EQCR 改派后附注编辑门禁也拒绝 ═══════════════════════════


class TestEqcrDeniesNoteEdit:

    async def test_eqcr_delegation_denies_note_edit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """经委派为 eqcr 后，附注编辑门禁以 EQCR 只读拒绝。"""
        async with sqlite_world(monkeypatch) as world:
            user = await _user(world.db)
            sm = await _staff(world.db, user)
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, "eqcr")])

            # 成员行是 (partner, review)
            member = await _get_member(world.db, user.id, PROJECT_ID)
            assert member is not None
            assert member.role == ProjectUserRole.partner
            assert member.permission_level == PermissionLevel.review

            # 附注编辑门禁拒绝
            assert await _check_note_edit(world.db, user, PROJECT_ID) is False

    async def test_reassignment_manager_to_eqcr_denies_note_edit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """从 manager 改派为 eqcr → 附注编辑门禁拒绝（成员行降级 + EQCR 排除）。"""
        async with sqlite_world(monkeypatch) as world:
            user = await _user(world.db)
            sm = await _staff(world.db, user)

            # 初始 manager → 附注编辑放行
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, "manager")])
            assert await _check_note_edit(world.db, user, PROJECT_ID) is True

            # 改派 eqcr
            await _delegate_and_sync(world.db, PROJECT_ID, [(sm, "eqcr")])
            member = await _get_member(world.db, user.id, PROJECT_ID)
            assert member is not None
            assert member.permission_level == PermissionLevel.review

            # 附注编辑门禁拒绝
            assert await _check_note_edit(world.db, user, PROJECT_ID) is False
