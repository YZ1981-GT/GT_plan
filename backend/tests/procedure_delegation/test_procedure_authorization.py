# Feature: procedure-delegation-notification — Task 7 项目授权 / staff-user 归一化 / SOD
"""`require_project_delegator` 与 staff/user 归一化 SOD 守卫测试。

Task 7 / 需求 5.1-5.3, 8.5-8.6, 11.1-11.6 / Design C5、D5 / Properties P16、P32：

- 单元 + 角色×项目 assignment 权限矩阵：仅 admin 全局放行；partner/signing_partner/manager
  必须持当前项目 **唯一** active ProjectAssignment；缺失/无 user_id/inactive/重复映射/
  跨项目/角色不足一律 fail-closed 403。
- 参与者 / 历史只读 guard：从 task 反查 project 绑定，跨项目 404；归一化 user 比较而非 staff id。
- PBT P16（staff/user 归一化 SOD）：Requirements 5.1, 5.2, 5.3
- PBT P32（项目授权 fail-closed）：Requirements 11.1, 11.2, 11.3, 11.4

真实 PostgreSQL（audit_platform）承载 staff/assignment/user 数据；每个用例在事务内插入并
回滚，绝不污染 dev 库。不可达 PG 时 skip。PBT 使用项目 fast profile。
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.models.base import UserRole
from app.models.core import Project, User
from app.models.procedure_models import (
    ProcedureRowDefinition,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
)
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.procedure_authorization import (
    ParticipantAccess,
    assert_sod_distinct,
    assert_task_in_project,
    ensure_project_delegator,
    normalize_staff_to_user,
    require_staff_active_user,
    resolve_task_participant_access,
)

_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")


# ---------------------------------------------------------------------------
# 测试数据 helper（均需要一个已 begin 的 AsyncSession）
# ---------------------------------------------------------------------------


async def _mk_user(s: AsyncSession, role: str = "manager") -> User:
    u = User(
        username=f"u_{uuid4().hex[:16]}",
        email=f"{uuid4().hex[:16]}@t.example",
        hashed_password="x",
        role=UserRole(role),
        is_active=True,
    )
    s.add(u)
    await s.flush()
    return u


async def _mk_project(s: AsyncSession) -> Project:
    p = Project(name=f"proj_{uuid4().hex[:8]}", client_name="测试客户")
    s.add(p)
    await s.flush()
    return p


async def _mk_staff(
    s: AsyncSession, user_id=None, is_deleted: bool = False
) -> StaffMember:
    st_ = StaffMember(name=f"staff_{uuid4().hex[:8]}", user_id=user_id)
    st_.is_deleted = is_deleted
    s.add(st_)
    await s.flush()
    return st_


async def _mk_assignment(
    s: AsyncSession, project_id, staff_id, role: str = "manager", is_deleted: bool = False
) -> ProjectAssignment:
    a = ProjectAssignment(project_id=project_id, staff_id=staff_id, role=role)
    a.is_deleted = is_deleted
    s.add(a)
    await s.flush()
    return a


async def _mk_definition(s: AsyncSession) -> ProcedureRowDefinition:
    d = ProcedureRowDefinition(
        definition_key=f"TESTWP::TESTWP::{uuid4().hex[:16]}",
        template_code="TESTWP",
        template_revision_hash="0" * 64,
        sheet_key="TESTWP",
        procedure_text="测试程序",
    )
    s.add(d)
    await s.flush()
    return d


async def _mk_task(
    s: AsyncSession, project, wp_index_id, definition_key,
    assignee_staff_id=None, reviewer_staff_id=None,
) -> ProcedureRowTask:
    t = ProcedureRowTask(
        project_id=project.id,
        wp_index_id=wp_index_id,
        definition_key=definition_key,
        sheet_key="TESTWP",
        definition_revision_hash="0" * 64,
        audit_cycle_snapshot="T",
        assignee_staff_id=assignee_staff_id,
        reviewer_staff_id=reviewer_staff_id,
    )
    s.add(t)
    await s.flush()
    return t


async def _existing_wp_index_id(s: AsyncSession, project_id):
    """ProcedureRowTask.wp_index_id 有 FK 到 wp_index，需要一个真实 wp_index。

    dev 库通常有 wp_index 行；取任意一条复用（事务回滚，不修改其归属）。
    """
    row = (await s.execute(sa.text("SELECT id FROM wp_index LIMIT 1"))).first()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# 事务隔离 session fixture（PG，用例结束回滚）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (procedure authorization)")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
    try:
        conn = await engine.connect()
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    trans = await conn.begin()
    s = AsyncSession(bind=conn)
    try:
        yield s
    finally:
        await s.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# 角色 × 项目 assignment 权限矩阵（P32 / 需求 11.1-11.4）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProjectDelegatorMatrix:
    async def test_admin_global_pass_without_assignment(self, session):
        """admin 无 assignment 也全局放行（需求 11.1）。"""
        admin = await _mk_user(session, "admin")
        proj = await _mk_project(session)
        ctx = await ensure_project_delegator(session, admin, proj.id)
        assert ctx.is_admin is True
        assert ctx.project_id == proj.id

    @pytest.mark.parametrize("assign_role", ["partner", "signing_partner", "manager"])
    async def test_delegator_roles_with_active_assignment_pass(self, session, assign_role):
        """partner/signing_partner/manager 持当前项目唯一 active assignment → 通过。"""
        user = await _mk_user(session, "manager")
        proj = await _mk_project(session)
        staff = await _mk_staff(session, user_id=user.id)
        await _mk_assignment(session, proj.id, staff.id, role=assign_role)
        ctx = await ensure_project_delegator(session, user, proj.id)
        assert ctx.is_admin is False
        assert ctx.assignment_role == assign_role
        assert ctx.staff_id == staff.id

    async def test_partner_system_role_without_assignment_denied(self, session):
        """仅有系统 role（无当前项目 active assignment）不放行（需求 11.2）。"""
        user = await _mk_user(session, "partner")
        proj = await _mk_project(session)
        await _mk_staff(session, user_id=user.id)  # 有 staff 但无 assignment
        with pytest.raises(HTTPException) as ei:
            await ensure_project_delegator(session, user, proj.id)
        assert ei.value.status_code == 403

    async def test_auditor_role_assignment_insufficient(self, session):
        """assignment role=auditor 角色不足 → 403（需求 11.3）。"""
        user = await _mk_user(session, "auditor")
        proj = await _mk_project(session)
        staff = await _mk_staff(session, user_id=user.id)
        await _mk_assignment(session, proj.id, staff.id, role="auditor")
        with pytest.raises(HTTPException) as ei:
            await ensure_project_delegator(session, user, proj.id)
        assert ei.value.status_code == 403

    async def test_qc_role_assignment_insufficient(self, session):
        user = await _mk_user(session, "qc")
        proj = await _mk_project(session)
        staff = await _mk_staff(session, user_id=user.id)
        await _mk_assignment(session, proj.id, staff.id, role="qc")
        with pytest.raises(HTTPException) as ei:
            await ensure_project_delegator(session, user, proj.id)
        assert ei.value.status_code == 403

    async def test_no_staff_mapping_denied(self, session):
        """user 无 active StaffMember → 403（需求 11.2/11.3）。"""
        user = await _mk_user(session, "manager")
        proj = await _mk_project(session)
        with pytest.raises(HTTPException) as ei:
            await ensure_project_delegator(session, user, proj.id)
        assert ei.value.status_code == 403

    async def test_duplicate_staff_mapping_denied(self, session):
        """同一 user 映射到多个 active staff（重复映射）→ 403（需求 11.3）。"""
        user = await _mk_user(session, "manager")
        proj = await _mk_project(session)
        s1 = await _mk_staff(session, user_id=user.id)
        s2 = await _mk_staff(session, user_id=user.id)
        await _mk_assignment(session, proj.id, s1.id, role="manager")
        await _mk_assignment(session, proj.id, s2.id, role="manager")
        with pytest.raises(HTTPException) as ei:
            await ensure_project_delegator(session, user, proj.id)
        assert ei.value.status_code == 403

    async def test_inactive_assignment_denied(self, session):
        """assignment 已软删除（inactive）→ 403（需求 11.3）。"""
        user = await _mk_user(session, "manager")
        proj = await _mk_project(session)
        staff = await _mk_staff(session, user_id=user.id)
        await _mk_assignment(session, proj.id, staff.id, role="manager", is_deleted=True)
        with pytest.raises(HTTPException) as ei:
            await ensure_project_delegator(session, user, proj.id)
        assert ei.value.status_code == 403

    async def test_inactive_staff_denied(self, session):
        """staff 已软删除 → user 无 active staff → 403。"""
        user = await _mk_user(session, "manager")
        proj = await _mk_project(session)
        staff = await _mk_staff(session, user_id=user.id, is_deleted=True)
        await _mk_assignment(session, proj.id, staff.id, role="manager")
        with pytest.raises(HTTPException) as ei:
            await ensure_project_delegator(session, user, proj.id)
        assert ei.value.status_code == 403

    async def test_cross_project_assignment_denied(self, session):
        """assignment 属于项目 B，为项目 A 授权 → 403（需求 11.3 跨项目）。"""
        user = await _mk_user(session, "manager")
        proj_a = await _mk_project(session)
        proj_b = await _mk_project(session)
        staff = await _mk_staff(session, user_id=user.id)
        await _mk_assignment(session, proj_b.id, staff.id, role="manager")
        with pytest.raises(HTTPException) as ei:
            await ensure_project_delegator(session, user, proj_a.id)
        assert ei.value.status_code == 403


# ---------------------------------------------------------------------------
# 参与者 / 历史只读 / 跨项目绑定 guard（需求 8.5-8.6, 11.5-11.6）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestParticipantAndBinding:
    async def test_cross_project_task_binding_returns_404(self, session):
        user = await _mk_user(session, "manager")
        proj_a = await _mk_project(session)
        proj_b = await _mk_project(session)
        wp_index_id = await _existing_wp_index_id(session, proj_a.id)
        if wp_index_id is None:
            pytest.skip("dev 库无 wp_index 可复用")
        d = await _mk_definition(session)
        task = await _mk_task(session, proj_a, wp_index_id, d.definition_key)
        # 用项目 B 校验属于项目 A 的 task → 404，不泄露
        with pytest.raises(HTTPException) as ei:
            await assert_task_in_project(session, task.id, proj_b.id)
        assert ei.value.status_code == 404

    async def test_assignee_access_by_normalized_user(self, session):
        """assignee 按归一化 user 命中（而非 staff id）。"""
        user = await _mk_user(session, "auditor")
        proj = await _mk_project(session)
        wp_index_id = await _existing_wp_index_id(session, proj.id)
        if wp_index_id is None:
            pytest.skip("dev 库无 wp_index 可复用")
        staff = await _mk_staff(session, user_id=user.id)
        d = await _mk_definition(session)
        task = await _mk_task(session, proj, wp_index_id, d.definition_key, assignee_staff_id=staff.id)
        res = await resolve_task_participant_access(session, task.id, user)
        assert res.access == ParticipantAccess.assignee

    async def test_history_participant_readonly(self, session):
        """转派后历史参与者获只读访问，但非当前 assignee/reviewer/delegator。"""
        old_user = await _mk_user(session, "auditor")
        cur_user = await _mk_user(session, "auditor")
        proj = await _mk_project(session)
        wp_index_id = await _existing_wp_index_id(session, proj.id)
        if wp_index_id is None:
            pytest.skip("dev 库无 wp_index 可复用")
        old_staff = await _mk_staff(session, user_id=old_user.id)
        cur_staff = await _mk_staff(session, user_id=cur_user.id)
        d = await _mk_definition(session)
        # 当前 assignee = cur_staff；历史里 old_staff 曾是 assignee
        task = await _mk_task(session, proj, wp_index_id, d.definition_key, assignee_staff_id=cur_staff.id)
        session.add(
            ProcedureRowTaskHistory(
                task_id=task.id,
                project_id=proj.id,
                event_type="reassign",
                old_assignee_staff_id=old_staff.id,
                new_assignee_staff_id=cur_staff.id,
            )
        )
        await session.flush()
        # old_user 现在只应有历史只读
        res_old = await resolve_task_participant_access(session, task.id, old_user)
        assert res_old.access == ParticipantAccess.history_readonly
        # cur_user 是当前 assignee
        res_cur = await resolve_task_participant_access(session, task.id, cur_user)
        assert res_cur.access == ParticipantAccess.assignee

    async def test_stranger_has_no_access(self, session):
        stranger = await _mk_user(session, "auditor")
        proj = await _mk_project(session)
        wp_index_id = await _existing_wp_index_id(session, proj.id)
        if wp_index_id is None:
            pytest.skip("dev 库无 wp_index 可复用")
        d = await _mk_definition(session)
        task = await _mk_task(session, proj, wp_index_id, d.definition_key)
        res = await resolve_task_participant_access(session, task.id, stranger)
        assert res.access == ParticipantAccess.none


# ---------------------------------------------------------------------------
# SOD 单元（P16 / 需求 5.2-5.3）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSodUnit:
    async def test_two_staff_same_user_cannot_be_assignee_and_reviewer(self, session):
        """两个不同 staff 归一到同一 user → 不能分别任 assignee/reviewer（409）。"""
        user = await _mk_user(session, "auditor")
        s1 = await _mk_staff(session, user_id=user.id)
        s2 = await _mk_staff(session, user_id=user.id)
        with pytest.raises(HTTPException) as ei:
            await assert_sod_distinct(session, s1.id, s2.id)
        assert ei.value.status_code == 409

    async def test_two_staff_different_users_ok(self, session):
        u1 = await _mk_user(session, "auditor")
        u2 = await _mk_user(session, "auditor")
        s1 = await _mk_staff(session, user_id=u1.id)
        s2 = await _mk_staff(session, user_id=u2.id)
        # 不抛错
        await assert_sod_distinct(session, s1.id, s2.id)

    async def test_staff_without_user_cannot_participate(self, session):
        """无 active user_id 的 staff 不能被委派/设为 reviewer（422）。"""
        s_no_user = await _mk_staff(session, user_id=None)
        with pytest.raises(HTTPException) as ei:
            await require_staff_active_user(session, s_no_user.id)
        assert ei.value.status_code == 422
        # 归一化返回 None
        assert await normalize_staff_to_user(session, s_no_user.id) is None

    async def test_same_staff_both_roles_is_sod_conflict(self, session):
        user = await _mk_user(session, "auditor")
        s1 = await _mk_staff(session, user_id=user.id)
        with pytest.raises(HTTPException) as ei:
            await assert_sod_distinct(session, s1.id, s1.id)
        assert ei.value.status_code == 409


# ---------------------------------------------------------------------------
# PBT 基础设施：每 example 独立事务 + 回滚（新引擎/新 loop，避免跨 loop 复用）
# ---------------------------------------------------------------------------


def _run(coro_fn):
    async def _wrap():
        engine = create_async_engine(app_settings.DATABASE_URL)
        conn = await engine.connect()
        trans = await conn.begin()
        s = AsyncSession(bind=conn)
        try:
            return await coro_fn(s)
        finally:
            await s.close()
            await trans.rollback()
            await conn.close()
            await engine.dispose()

    return asyncio.run(_wrap())


# ---------------------------------------------------------------------------
# PBT P16：staff/user 归一化 SOD
# Validates: Requirements 5.1, 5.2, 5.3
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _IS_PG, reason="need PostgreSQL")
class TestP16SodNormalization:
    @given(
        # 两个 staff 是否共享同一 user；各自是否有 user_id
        share_user=st.booleans(),
        assignee_has_user=st.booleans(),
        reviewer_has_user=st.booleans(),
    )
    @settings(max_examples=5)
    def test_sod_iff_normalized_users_distinct(
        self, share_user, assignee_has_user, reviewer_has_user
    ):
        async def scenario(s: AsyncSession):
            u1 = await _mk_user(s, "auditor")
            u2 = u1 if share_user else await _mk_user(s, "auditor")
            a_staff = await _mk_staff(s, user_id=(u1.id if assignee_has_user else None))
            r_staff = await _mk_staff(s, user_id=(u2.id if reviewer_has_user else None))

            raised = None
            try:
                await assert_sod_distinct(s, a_staff.id, r_staff.id)
            except HTTPException as exc:
                raised = exc.status_code

            if not assignee_has_user or not reviewer_has_user:
                # 无 active user_id 的 staff 不能参与 → 422
                assert raised == 422
            elif share_user:
                # 归一到同一 user → 自我复核 409
                assert raised == 409
            else:
                # 归一到不同 user → 通过
                assert raised is None

        _run(scenario)


# ---------------------------------------------------------------------------
# PBT P32：项目授权 fail-closed
# Validates: Requirements 11.1, 11.2, 11.3, 11.4
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _IS_PG, reason="need PostgreSQL")
class TestP32ProjectAuthFailClosed:
    @given(
        system_role=st.sampled_from(["admin", "partner", "manager", "auditor", "qc"]),
        has_staff=st.booleans(),
        assignment_role=st.sampled_from(
            ["partner", "signing_partner", "manager", "auditor", "qc", None]
        ),
        assignment_active=st.booleans(),
        same_project=st.booleans(),
    )
    @settings(max_examples=5)
    def test_only_admin_or_unique_active_delegator_assignment_passes(
        self, system_role, has_staff, assignment_role, assignment_active, same_project
    ):
        async def scenario(s: AsyncSession):
            user = await _mk_user(s, system_role)
            proj = await _mk_project(s)
            other = await _mk_project(s)

            if has_staff:
                staff = await _mk_staff(s, user_id=user.id)
                if assignment_role is not None:
                    await _mk_assignment(
                        s,
                        (proj.id if same_project else other.id),
                        staff.id,
                        role=assignment_role,
                        is_deleted=not assignment_active,
                    )

            passed = True
            try:
                await ensure_project_delegator(s, user, proj.id)
            except HTTPException as exc:
                assert exc.status_code == 403  # fail-closed，绝不 500
                passed = False

            # 期望：admin 恒通过；否则须 has_staff + 当前项目 active assignment
            # + role ∈ {partner,signing_partner,manager}
            expected = system_role == "admin" or (
                has_staff
                and assignment_role in ("partner", "signing_partner", "manager")
                and assignment_active
                and same_project
            )
            assert passed == expected

        _run(scenario)
