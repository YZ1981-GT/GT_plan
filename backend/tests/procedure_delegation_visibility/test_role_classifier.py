# Feature: procedure-delegation-visibility-isolation — Task 3 唯一角色分类
"""VisibilityRoleClassifier 唯一分类 + fail-closed 测试。

Task 3 / Requirements 1.1–1.11 / Design "Role Classification" / Property 1
(Role classification is unique and fail-closed).

覆盖：
- Req 1.2/1.8：system admin → Admin_User，忽略 scope_cycles（即使 ProjectUser 有 scope）。
- Req 1.3：Non_Admin 同时具唯一 active StaffMember + 唯一 active ProjectAssignment
  （角色权威，role ∈ partner/signing_partner/manager/qc/eqcr）+ 唯一 active ProjectUser
  （scope 权威）→ Supervisor。
- Req 1.4/1.5：缺失/重复/inactive/角色不足/查询异常 → Restricted（fail-closed，不 500）。
- Req 1.6/1.7/1.9/1.10：Non_Admin scope 上界；scope 缺失/失败解释为空集。
- Req 1.1/1.11：输出恰为三分类之一且唯一。
- 角色来源单一：Supervisor 角色只认 ProjectAssignment.role（非 ProjectUser.role）。

SQL 语义在真实 PostgreSQL 验证；fail-closed 用注入异常 session 单元验证（无需 PG）。
"""
from __future__ import annotations

import types
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_visibility.contracts import VisibilityRole
from app.services.wp_visibility.role_classifier import (
    SUPERVISOR_ASSIGNMENT_ROLES,
    VisibilityRoleClassifier,
)

from ._factories import (
    IS_PG,
    mk_assignment,
    mk_project,
    mk_project_user,
    mk_staff,
    mk_user,
    run_isolated,
)


def _parse_scope(raw: str | None) -> frozenset[str]:
    if raw and isinstance(raw, str) and raw.strip():
        return frozenset(c.strip() for c in raw.split(",") if c.strip())
    return frozenset()


# ---------------------------------------------------------------------------
# 单元：fail-closed（注入异常 session，无需 PG）
# ---------------------------------------------------------------------------
class _RaisingSession:
    """任何查询都抛异常的假 session：验证分类器 fail-closed 收敛 Restricted。"""

    async def execute(self, *args, **kwargs):  # noqa: D401, ANN001
        raise RuntimeError("boom: simulated query failure")


def _fake_user(role: str):
    return types.SimpleNamespace(id=uuid4(), role=types.SimpleNamespace(value=role))


class TestFailClosedUnit:
    @pytest.mark.asyncio
    async def test_query_failure_non_admin_is_restricted_empty_scope(self):
        """Req 1.5/1.10：Non_Admin 查询异常 → Restricted + 空 scope，不 500。"""
        clf = VisibilityRoleClassifier(_RaisingSession())
        pid = uuid4()
        ctx = await clf.classify(_fake_user("auditor"), pid)
        assert ctx.role is VisibilityRole.restricted
        assert ctx.is_admin is False
        assert ctx.scope_cycles == frozenset()

    @pytest.mark.asyncio
    async def test_admin_short_circuits_without_query(self):
        """Req 1.2/1.8：admin 不查库即分类，异常 session 也返回 Admin + 空 scope。"""
        clf = VisibilityRoleClassifier(_RaisingSession())
        ctx = await clf.classify(_fake_user("admin"), uuid4())
        assert ctx.role is VisibilityRole.admin
        assert ctx.is_admin is True
        assert ctx.scope_cycles == frozenset()

    @pytest.mark.asyncio
    async def test_unknown_role_non_admin_restricted(self):
        """Req 1.5：未知/未登记角色（非 admin）→ Restricted。"""
        clf = VisibilityRoleClassifier(_RaisingSession())
        ctx = await clf.classify(_fake_user("bogus_role"), uuid4())
        assert ctx.role is VisibilityRole.restricted
        assert ctx.is_admin is False


# ---------------------------------------------------------------------------
# PG 示例：三分类代表性场景
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestClassificationExamples:
    async def test_admin_ignores_scope_even_with_project_user_scope(self, session):
        user = await mk_user(session, "admin")
        proj = await mk_project(session)
        # 即使有 ProjectUser scope，admin 也忽略
        await mk_project_user(session, proj.id, user.id, scope_cycles="现金,收入")
        ctx = await VisibilityRoleClassifier(session).classify(user, proj.id)
        assert ctx.role is VisibilityRole.admin
        assert ctx.is_admin is True
        assert ctx.scope_cycles == frozenset()

    async def test_supervisor_happy_path_with_scope(self, session):
        user = await mk_user(session, "auditor")  # system role 无关，链路决定分类
        proj = await mk_project(session)
        staff = await mk_staff(session, user_id=user.id)
        await mk_assignment(session, proj.id, staff.id, role="manager")
        await mk_project_user(session, proj.id, user.id, scope_cycles="现金, 收入 ,")
        ctx = await VisibilityRoleClassifier(session).classify(user, proj.id)
        assert ctx.role is VisibilityRole.supervisor
        assert ctx.is_admin is False
        assert ctx.scope_cycles == frozenset({"现金", "收入"})

    async def test_assignment_role_not_in_allowed_set_is_restricted(self, session):
        """角色权威=ProjectAssignment：auditor 不在 Supervisor 允许集 → Restricted。"""
        user = await mk_user(session, "auditor")
        proj = await mk_project(session)
        staff = await mk_staff(session, user_id=user.id)
        await mk_assignment(session, proj.id, staff.id, role="auditor")
        await mk_project_user(session, proj.id, user.id, scope_cycles="现金")
        ctx = await VisibilityRoleClassifier(session).classify(user, proj.id)
        assert ctx.role is VisibilityRole.restricted
        assert ctx.scope_cycles == frozenset({"现金"})

    async def test_missing_project_user_is_restricted(self, session):
        """缺 scope 权威链路（无 active ProjectUser）→ Restricted，scope 空集。"""
        user = await mk_user(session, "manager")
        proj = await mk_project(session)
        staff = await mk_staff(session, user_id=user.id)
        await mk_assignment(session, proj.id, staff.id, role="manager")
        ctx = await VisibilityRoleClassifier(session).classify(user, proj.id)
        assert ctx.role is VisibilityRole.restricted
        assert ctx.scope_cycles == frozenset()

    async def test_duplicate_active_staff_is_restricted(self, session):
        """映射数≠1（同 user 两个 active staff）→ Restricted。"""
        user = await mk_user(session, "manager")
        proj = await mk_project(session)
        s1 = await mk_staff(session, user_id=user.id)
        await mk_staff(session, user_id=user.id)  # 第二个 active staff → 非唯一
        await mk_assignment(session, proj.id, s1.id, role="manager")
        await mk_project_user(session, proj.id, user.id, scope_cycles="现金")
        ctx = await VisibilityRoleClassifier(session).classify(user, proj.id)
        assert ctx.role is VisibilityRole.restricted

    async def test_inactive_assignment_is_restricted(self, session):
        """assignment inactive（软删）→ 无唯一 active 链路 → Restricted。"""
        user = await mk_user(session, "manager")
        proj = await mk_project(session)
        staff = await mk_staff(session, user_id=user.id)
        await mk_assignment(session, proj.id, staff.id, role="manager", is_deleted=True)
        await mk_project_user(session, proj.id, user.id, scope_cycles="现金")
        ctx = await VisibilityRoleClassifier(session).classify(user, proj.id)
        assert ctx.role is VisibilityRole.restricted


# ---------------------------------------------------------------------------
# PBT Property 1：分类唯一 & fail-closed & Non_Admin scope 上界
# Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11
# ---------------------------------------------------------------------------
_SUPERVISOR_SET = set(SUPERVISOR_ASSIGNMENT_ROLES)


@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestProperty1ClassificationUniqueFailClosed:
    @given(
        system_role=st.sampled_from(
            ["admin", "auditor", "manager", "qc", "partner", "eqcr", "readonly"]
        ),
        staff_case=st.sampled_from(["none", "one", "two"]),
        assign_role=st.sampled_from(
            ["manager", "partner", "signing_partner", "qc", "eqcr", "auditor", "readonly", None]
        ),
        assign_active=st.booleans(),
        has_project_user=st.booleans(),
        scope_str=st.sampled_from([None, "", "A,B", "现金 , 收入 ,", "   "]),
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_classification_matrix(
        self,
        system_role,
        staff_case,
        assign_role,
        assign_active,
        has_project_user,
        scope_str,
    ):
        async def scenario(s):
            user = await mk_user(s, system_role)
            proj = await mk_project(s)

            staff_ids = []
            if staff_case in ("one", "two"):
                staff_ids.append((await mk_staff(s, user_id=user.id)).id)
            if staff_case == "two":
                staff_ids.append((await mk_staff(s, user_id=user.id)).id)

            if staff_ids and assign_role is not None:
                await mk_assignment(
                    s, proj.id, staff_ids[0], role=assign_role,
                    is_deleted=not assign_active,
                )
            if has_project_user:
                await mk_project_user(
                    s, proj.id, user.id, scope_cycles=scope_str
                )

            ctx = await VisibilityRoleClassifier(s).classify(user, proj.id)

            # Req 1.1：输出恰为三分类之一（enum 本身保证唯一）
            assert ctx.role in (
                VisibilityRole.admin,
                VisibilityRole.supervisor,
                VisibilityRole.restricted,
            )
            assert ctx.is_admin == (ctx.role is VisibilityRole.admin)

            if system_role == "admin":
                # Req 1.2/1.8：admin 忽略 scope
                assert ctx.role is VisibilityRole.admin
                assert ctx.scope_cycles == frozenset()
                return

            # Non_Admin
            assert ctx.is_admin is False
            expected_supervisor = (
                staff_case == "one"
                and assign_role in _SUPERVISOR_SET
                and assign_active
                and has_project_user
            )
            assert ctx.role is (
                VisibilityRole.supervisor
                if expected_supervisor
                else VisibilityRole.restricted
            )
            # Req 1.6/1.7/1.9/1.10：scope 上界；缺失/空白 → 空集
            expected_scope = _parse_scope(scope_str) if has_project_user else frozenset()
            assert ctx.scope_cycles == expected_scope

        run_isolated(scenario)
