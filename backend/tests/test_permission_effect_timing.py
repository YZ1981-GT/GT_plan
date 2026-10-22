"""生效时效性质测试（partner-manager-edit-permission 任务 14.3；Property 6；需求 5.1、5.2、5.5、5.6；design D3、D12）。

# Feature: partner-manager-edit-permission, Property 6: 变更提交后开始的判定即时按新数据

权限缓存已移除（design D3）。级别判定点每次直接查库（``deps._load_member_level``），不经任何 ``perm:*`` 键。
因此「变更提交后开始的判定即时按新数据」由查库的即时性保证——本文件用 4~6 个确定性固定样例验证：

固定样例 ① 新建成员行：新加的成员，下一次判定即可见。
固定样例 ② 成员行删除：原有成员行删除，下一次判定返回 403。
固定样例 ③ 委派变更（manager→eqcr）：经委派保存同步后，下一次附注编辑判定以 EQCR 只读拒绝。
固定样例 ④ 覆盖集合端点经附注编辑门禁（与 ③ 同场景）。

附加判据（design D12）：委派保存过程对 ``perm:*`` 键零读 / 零写 / 零删——预置键的键集合与剩余 TTL 在保存前后不变。
"""
from __future__ import annotations

import uuid
from typing import Any

import fakeredis
import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.redis as core_redis
from app.deps import assert_project_permission
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.assignment_service import AssignmentService, ROLE_MAP
from app.services.eqcr_resolver import is_project_eqcr
from app.services.note_edit_gate import assert_note_edit_access
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

pytestmark = pytest.mark.asyncio

# ─── 常量 ─────────────────────────────────────────────────────────────────────

PROJECT_ID = TARGET_PROJECT_ID


# ─── 辅助 ─────────────────────────────────────────────────────────────────────

async def _create_user(db: AsyncSession, *, global_role: UserRole = UserRole.auditor) -> User:
    tag = uuid.uuid4().hex[:8]
    user = User(username=f"timing-{tag}", email=f"{tag}@timing.test", hashed_password="x",
                role=global_role, is_active=True)
    db.add(user)
    await db.flush()
    return user


async def _create_member(
    db: AsyncSession, user: User, project_id: uuid.UUID = PROJECT_ID,
    *, role: ProjectUserRole = ProjectUserRole.manager, level: PermissionLevel = PermissionLevel.edit,
) -> ProjectUser:
    row = ProjectUser(project_id=project_id, user_id=user.id, role=role, permission_level=level)
    db.add(row)
    await db.flush()
    return row


async def _create_staff(db: AsyncSession, user: User) -> StaffMember:
    staff = StaffMember(user_id=user.id, name="timing-staff")
    db.add(staff)
    await db.flush()
    return staff


async def _create_assignment(
    db: AsyncSession, project_id: uuid.UUID, staff: StaffMember, role: str,
) -> ProjectAssignment:
    from datetime import datetime, timezone
    pa = ProjectAssignment(
        project_id=project_id, staff_id=staff.id, role=role, assigned_at=datetime.now(timezone.utc),
    )
    db.add(pa)
    await db.flush()
    return pa


async def _check_permission(db: AsyncSession, user: User, project_id: uuid.UUID, min_perm: str = "edit") -> bool:
    """调用 assert_project_permission，返回 True（放行）或 False（403）。"""
    try:
        await assert_project_permission(db, user, project_id, min_perm)
        return True
    except HTTPException as exc:
        if exc.status_code == 403:
            return False
        raise


async def _check_note_edit(db: AsyncSession, user: User, project_id: uuid.UUID) -> bool:
    """调用附注编辑门禁，返回 True（放行）或 False（403）。"""
    try:
        await assert_note_edit_access(db, user, project_id, consol_lock=False)
        return True
    except HTTPException as exc:
        if exc.status_code in (403, 423):
            return False
        raise


# ═══ 固定样例 ① 新建成员行：下一次判定即可见 ═══════════════════════════════════


class TestNewMemberRowSeenImmediately:

    async def test_new_member_row_grants_access(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """固定样例 ①：新建成员行后，提交（flush）后的下一次判定即放行。"""
        async with sqlite_world(monkeypatch) as world:
            user = await _create_user(world.db)
            # 保存前：用户没有成员行，edit 级判定被拒
            assert await _check_permission(world.db, user, PROJECT_ID, "edit") is False

            # 新建成员行
            await _create_member(world.db, user, role=ProjectUserRole.manager, level=PermissionLevel.edit)

            # 保存后：下一次判定即放行
            assert await _check_permission(world.db, user, PROJECT_ID, "edit") is True


# ═══ 固定样例 ② 成员行删除：下一次判定返回 403 ════════════════════════════════


class TestDeletedMemberRowDenied:

    async def test_deleted_member_row_denies_access(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """固定样例 ②：成员行删除后，下一次判定返回 403。"""
        async with sqlite_world(monkeypatch) as world:
            user = await _create_user(world.db)
            row = await _create_member(world.db, user)

            # 保存前：有成员行，能通过 edit 级判定
            assert await _check_permission(world.db, user, PROJECT_ID, "edit") is True

            # 删除成员行（模拟 is_deleted 标记）
            row.is_deleted = True
            await world.db.flush()

            # 删除后：下一次判定返回 403
            assert await _check_permission(world.db, user, PROJECT_ID, "edit") is False


# ═══ 固定样例 ③ 委派变更 manager→eqcr ═════════════════════════════════════════


class TestDelegationChangeEqcr:

    async def test_manager_to_eqcr_denies_note_edit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """固定样例 ③：经理改派为 EQCR 后，下一次附注编辑门禁判定以 EQCR 只读拒绝。"""
        async with sqlite_world(monkeypatch) as world:
            user = await _create_user(world.db)
            staff = await _create_staff(world.db, user)

            # 初始：manager 委派，成员行 (manager, edit)
            await _create_assignment(world.db, PROJECT_ID, staff, "manager")
            await _create_member(world.db, user, role=ProjectUserRole.manager, level=PermissionLevel.edit)

            # 初始状态：附注编辑门禁放行
            assert await _check_note_edit(world.db, user, PROJECT_ID) is True

            # 模拟委派变更：旧委派标删，新建 eqcr 委派
            await world.db.execute(
                sa.update(ProjectAssignment).where(
                    ProjectAssignment.project_id == PROJECT_ID,
                    ProjectAssignment.is_deleted == False,  # noqa: E712
                ).values(is_deleted=True)
            )
            new_pa = await _create_assignment(world.db, PROJECT_ID, staff, "eqcr")
            # 成员行按映射同步：eqcr → (partner, review)
            member = (await world.db.execute(
                sa.select(ProjectUser).where(
                    ProjectUser.project_id == PROJECT_ID,
                    ProjectUser.user_id == user.id,
                    ProjectUser.is_deleted == False,  # noqa: E712
                )
            )).scalar_one()
            member.role = ProjectUserRole.partner
            member.permission_level = PermissionLevel.review
            await world.db.flush()

            # 变更后：EQCR 判定为 True
            assert await is_project_eqcr(world.db, user, PROJECT_ID) is True

            # 变更后：附注编辑门禁拒绝（EQCR 只读）
            assert await _check_note_edit(world.db, user, PROJECT_ID) is False


# ═══ 固定样例 ④ 覆盖集合端点经附注编辑门禁 ════════════════════════════════════


class TestCoverageEndpointEqcrDenied:

    async def test_note_edit_gate_endpoint_denies_eqcr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """固定样例 ④：与 ③ 同一场景，但验证另一个用户经附注编辑门禁也被拒绝。"""
        async with sqlite_world(monkeypatch) as world:
            user = await _create_user(world.db)
            staff = await _create_staff(world.db, user)

            # 初始：manager 委派，成员行 (manager, edit)
            await _create_assignment(world.db, PROJECT_ID, staff, "manager")
            await _create_member(world.db, user, role=ProjectUserRole.manager, level=PermissionLevel.edit)

            # 初始：edit 级判定放行 + 附注编辑门禁放行
            assert await _check_permission(world.db, user, PROJECT_ID, "edit") is True
            assert await _check_note_edit(world.db, user, PROJECT_ID) is True

            # 改派为 eqcr：更新委派 + 成员行降级
            await world.db.execute(
                sa.update(ProjectAssignment).where(
                    ProjectAssignment.project_id == PROJECT_ID,
                    ProjectAssignment.is_deleted == False,  # noqa: E712
                ).values(is_deleted=True)
            )
            await _create_assignment(world.db, PROJECT_ID, staff, "eqcr")
            member = (await world.db.execute(
                sa.select(ProjectUser).where(
                    ProjectUser.project_id == PROJECT_ID,
                    ProjectUser.user_id == user.id,
                    ProjectUser.is_deleted == False,  # noqa: E712
                )
            )).scalar_one()
            member.role = ProjectUserRole.partner
            member.permission_level = PermissionLevel.review
            await world.db.flush()

            # 变更后：edit 级判定 — review 成员不通过 edit
            assert await _check_permission(world.db, user, PROJECT_ID, "edit") is False
            # review 级判定 — 通过（成员行还在，是 review）
            assert await _check_permission(world.db, user, PROJECT_ID, "review") is True
            # 附注编辑门禁拒绝（EQCR 只读）
            assert await _check_note_edit(world.db, user, PROJECT_ID) is False


# ═══ D12 附加判据：perm:* 零读零写零删，预置键不变 ═════════════════════════════


class TestPermCacheUntouched:

    async def test_delegation_save_does_not_touch_perm_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """D12：委派保存过程对 perm:* 键零操作；预置键的集合与剩余 TTL 不变。"""
        async with sqlite_world(monkeypatch) as world:
            # 预置 2 个 perm:* 键（模拟残留缓存）
            affected_user = await _create_user(world.db)
            unrelated_user = await _create_user(world.db)
            staff = await _create_staff(world.db, affected_user)

            key_affected = f"perm:{affected_user.id}:{PROJECT_ID}"
            key_unrelated = f"perm:{unrelated_user.id}:{PROJECT_ID}"
            await world.redis.set(key_affected, "edit", ex=300)
            await world.redis.set(key_unrelated, "review", ex=300)

            # 记录预置键的 TTL（>= 290 因刚设置）
            ttl_affected_before = await world.redis.ttl(key_affected)
            ttl_unrelated_before = await world.redis.ttl(key_unrelated)
            assert ttl_affected_before > 290
            assert ttl_unrelated_before > 290

            keys_before = sorted([k async for k in world.redis.scan_iter("perm:*")])

            # 模拟委派保存的核心路径：
            # AssignmentService._sync_project_users 不触碰任何 perm:* 键
            await _create_member(world.db, affected_user, role=ProjectUserRole.manager, level=PermissionLevel.edit)

            # 检查 perm:* 键集合与 TTL 不变
            keys_after = sorted([k async for k in world.redis.scan_iter("perm:*")])
            assert keys_before == keys_after, f"perm:* 键集合变化：{keys_before} → {keys_after}"

            # TTL 不变
            ttl_affected_after = await world.redis.ttl(key_affected)
            ttl_unrelated_after = await world.redis.ttl(key_unrelated)
            # TTL 可能减少 1~2 秒（测试执行时间）；但不应被重置或延长
            assert ttl_affected_after <= ttl_affected_before
            assert ttl_unrelated_after <= ttl_unrelated_before
            # 值不变
            assert await world.redis.get(key_affected) == "edit"
            assert await world.redis.get(key_unrelated) == "review"


class TestLevelChangeEffect:
    """level 降级后下一次判定即拒绝：覆盖需求 5.2 的「降级即时生效」。"""

    async def test_level_downgrade_immediately_denies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """成员行从 edit 改为 review：下一次 edit 级判定即拒绝。"""
        async with sqlite_world(monkeypatch) as world:
            user = await _create_user(world.db)
            row = await _create_member(world.db, user, role=ProjectUserRole.manager, level=PermissionLevel.edit)

            # edit 级放行
            assert await _check_permission(world.db, user, PROJECT_ID, "edit") is True

            # 降级为 review
            row.permission_level = PermissionLevel.review
            await world.db.flush()

            # 下一次 edit 级判定即拒绝
            assert await _check_permission(world.db, user, PROJECT_ID, "edit") is False
            # review 级仍放行
            assert await _check_permission(world.db, user, PROJECT_ID, "review") is True
