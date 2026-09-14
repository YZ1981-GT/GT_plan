# Feature: procedure-delegation-visibility-isolation — Task 3 严格 staff↔user 映射
"""StaffUserMappingService 写事务映射不变量测试。

Task 3 / Requirements 2.4–2.6, 3.1–3.6 / Design "DelegationMappingService" /
Property 2 (Staff and user identity require a unique active mapping)。

任务描述称"Property 5 subset（unique active mapping / cross-project reject /
field-equality reject）"；按 design 权威属性编号，这些 staff↔user 映射不变量归属
**Property 2**（Requirements 2.4–2.6, 3.1–3.6）。此处标注 Property 2。

覆盖：
- Req 3.1/3.2/3.3：目标项目内唯一 active StaffMember、active、非空 user_id 才接受。
- Req 3.4：反向唯一（该 user_id 在目标项目唯一映射到该 active StaffMember）。
- Req 3.6：仅项目外可解析 → 跨项目拒绝。
- Req 3.5：任一条件不成立即拒绝（调用方回滚）。
- Req 2.5/2.6：同人判定只用映射；绝不用 user_id==staff_id 字段值直接相等。

SQL 语义在真实 PostgreSQL 验证（非 sqlite）。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_visibility.staff_user_mapping import (
    MappingRejectReason,
    StaffUserMappingService,
)

from ._factories import (
    IS_PG,
    mk_assignment,
    mk_project,
    mk_staff,
    mk_user,
    run_isolated,
)


# ---------------------------------------------------------------------------
# PG 示例：各映射不变量
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestMappingInvariantExamples:
    async def test_unique_active_mapping_accepted(self, session):
        """Req 3.1–3.4：目标项目唯一 active 双向映射 → 接受，返回映射 user_id。"""
        user = await mk_user(session)
        proj = await mk_project(session)
        staff = await mk_staff(session, user_id=user.id)
        await mk_assignment(session, proj.id, staff.id, role="manager")
        res = await StaffUserMappingService(session).resolve_active_project_mapping(
            proj.id, staff.id
        )
        assert res.ok is True
        assert res.user_id == user.id
        assert res.reason is None

    async def test_empty_staff_rejected(self, session):
        res = await StaffUserMappingService(session).resolve_active_project_mapping(
            (await mk_project(session)).id, None
        )
        assert res.ok is False
        assert res.reason is MappingRejectReason.empty_staff

    async def test_inactive_staff_rejected(self, session):
        """Req 3.2：inactive（软删）StaffMember 拒绝。"""
        user = await mk_user(session)
        proj = await mk_project(session)
        staff = await mk_staff(session, user_id=user.id, is_deleted=True)
        await mk_assignment(session, proj.id, staff.id, role="manager")
        res = await StaffUserMappingService(session).resolve_active_project_mapping(
            proj.id, staff.id
        )
        assert res.ok is False
        assert res.reason is MappingRejectReason.not_found

    async def test_staff_without_user_rejected(self, session):
        """Req 3.3：user_id 为空的 StaffMember 拒绝。"""
        proj = await mk_project(session)
        staff = await mk_staff(session, user_id=None)
        await mk_assignment(session, proj.id, staff.id, role="manager")
        res = await StaffUserMappingService(session).resolve_active_project_mapping(
            proj.id, staff.id
        )
        assert res.ok is False
        assert res.reason is MappingRejectReason.not_found

    async def test_cross_project_rejected(self, session):
        """Req 3.6：staff active 且有 user，但只在别的项目有 assignment → 跨项目拒绝。"""
        user = await mk_user(session)
        proj = await mk_project(session)
        other = await mk_project(session)
        staff = await mk_staff(session, user_id=user.id)
        await mk_assignment(session, other.id, staff.id, role="manager")
        res = await StaffUserMappingService(session).resolve_active_project_mapping(
            proj.id, staff.id
        )
        assert res.ok is False
        assert res.reason is MappingRejectReason.cross_project

    async def test_ambiguous_reverse_rejected(self, session):
        """Req 3.4：同一 user 在目标项目映射到两个 active staff → 反向非唯一，拒绝。"""
        user = await mk_user(session)
        proj = await mk_project(session)
        s1 = await mk_staff(session, user_id=user.id)
        s2 = await mk_staff(session, user_id=user.id)
        await mk_assignment(session, proj.id, s1.id, role="manager")
        await mk_assignment(session, proj.id, s2.id, role="auditor")
        res = await StaffUserMappingService(session).resolve_active_project_mapping(
            proj.id, s1.id
        )
        assert res.ok is False
        assert res.reason is MappingRejectReason.ambiguous

    async def test_field_equality_never_implies_same_person(self, session):
        """Req 2.6：绝不以 user_id==staff_id 字段值直接相等判同人。

        传入 staff_id = 某 user 自身 id（一个合法 UUID 但不是 staff 行）：
        - 朴素的 `user_id == staff_id` 会误判"同人"（同一 UUID）；
        - 基于映射的判定必须为 False（该 id 不是 active StaffMember）。
        """
        user = await mk_user(session)
        proj = await mk_project(session)
        svc = StaffUserMappingService(session)
        # 用 user.id 冒充 staff_id
        res = await svc.resolve_active_project_mapping(proj.id, user.id)
        assert res.ok is False
        assert res.reason is MappingRejectReason.not_found
        # 同人判定：朴素等值会 True，映射判定必须 False
        assert await svc.is_same_natural_person(proj.id, user.id, user.id) is False

    async def test_is_same_natural_person_uses_mapping(self, session):
        """Req 2.4/2.5：同人判定只经映射；映射到不同 user 时为 False。"""
        user = await mk_user(session)
        other_user = await mk_user(session)
        proj = await mk_project(session)
        staff = await mk_staff(session, user_id=user.id)
        await mk_assignment(session, proj.id, staff.id, role="manager")
        svc = StaffUserMappingService(session)
        # 映射到 user → True
        assert await svc.is_same_natural_person(proj.id, user.id, staff.id) is True
        # 映射到 user，但传入 other_user → False（映射说不是同人）
        assert await svc.is_same_natural_person(proj.id, other_user.id, staff.id) is False


# ---------------------------------------------------------------------------
# PBT Property 2：映射唯一 active + 反向唯一 + 跨项目拒绝
# Validates: Requirements 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestProperty2StaffUserMapping:
    @given(
        staff_present=st.booleans(),
        staff_active=st.booleans(),
        staff_has_user=st.booleans(),
        in_project=st.booleans(),
        duplicate_reverse=st.booleans(),
        nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_mapping_accepts_only_unique_active_bidirectional(
        self, staff_present, staff_active, staff_has_user, in_project, duplicate_reverse, nonce
    ):
        async def scenario(s):
            user = await mk_user(s, "auditor")
            proj = await mk_project(s)
            other = await mk_project(s)

            if not staff_present:
                staff_id = uuid4()  # 不存在的 staff
            else:
                uid = user.id if staff_has_user else None
                staff = await mk_staff(s, user_id=uid, is_deleted=not staff_active)
                staff_id = staff.id
                if in_project:
                    await mk_assignment(s, proj.id, staff.id, role="manager")
                else:
                    # 仅在别的项目有 assignment → 跨项目
                    await mk_assignment(s, other.id, staff.id, role="manager")
                if duplicate_reverse and staff_has_user and in_project and staff_active:
                    s2 = await mk_staff(s, user_id=user.id)
                    await mk_assignment(s, proj.id, s2.id, role="auditor")

            res = await StaffUserMappingService(s).resolve_active_project_mapping(
                proj.id, staff_id
            )

            dup_effective = (
                duplicate_reverse and staff_has_user and in_project and staff_active
            )
            expected_ok = (
                staff_present
                and staff_active
                and staff_has_user
                and in_project
                and not dup_effective
            )
            assert res.ok == expected_ok
            if res.ok:
                assert res.user_id == user.id
                assert res.reason is None
            else:
                assert res.user_id is None
                assert res.reason is not None

        run_isolated(scenario)
