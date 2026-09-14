# Feature: procedure-delegation-visibility-isolation — Task 5 AccessGrant CTE / 页面集 / 历史只读
"""VisibilityQueryService（组件 C5）grant 产出不变量测试。

Task 5 / Requirements 5.1–5.18, 11.1–11.5, 16.5–16.13 / Design 组件 C5 "AccessGrant query"。

属性编号以 **design.md 权威编号** 为准（prompt 用了另一套编号，此处按 design 标注并记录映射）：
  - **Property 5**（"Restricted visibility equals the fixed set formula"，Validates 5.1–5.4）：
    Restricted 可见集 = ``(Delegated∪History)∩scope``，按 wp_index 去重，空集不回退循环级。
    → prompt 称其为 "Property 7"。
  - **Property 6**（"Delegation history remains stable after rebinding"，Validates 3.13/3.14/5.2/5.18）：
    history 只读事件时不可变快照，staff/task 重绑不改变历史归属。→ prompt 也称 "Property 6"。
  - **Property 7**（"Page visibility follows role and immutable history"，Validates 5.5–5.14/5.17/5.18）：
    lead/admin/supervisor_scope=all，row 当前/历史=对应 sheet_key，History_Only 只读（readonly=True）。
    → prompt 拆为 "Property 9（Sheet_Key 页面隔离）" 与 "Property 10（history current-version-only）"。
  - **Property 8**（"Every grant has one known kind and cannot splice matrix dimensions"，
    Validates 5.15/5.16/7.x）：每个 grant 恰一个已登记 access_kind；未登记 kind 丢弃。
    → prompt 称 "Property 8"。
  - **no-N+1**（Design Testing Strategy："运行 EXPLAIN/query-count 证明无按底稿 N+1"）：可见集用
    常量条查询构建，不随底稿数量增长。→ prompt 称 "Property 20"（design 无该编号属性，归 Testing Strategy）。

SQL 语义在真实 PostgreSQL（audit_platform）验证，非 sqlite。每用例/每 example 事务隔离回滚。
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.models.wp_visibility_models import WorkpaperDelegationHistory
from app.services.wp_visibility.contracts import VisibilityContext, VisibilityRole
from app.services.wp_visibility.visibility_query import (
    ACCESS_KIND_ADMIN,
    ACCESS_KIND_ASSIGNEE,
    ACCESS_KIND_LEAD,
    ACCESS_KIND_LEAD_HISTORY,
    ACCESS_KIND_REVIEWER,
    ACCESS_KIND_ROW_HISTORY,
    ACCESS_KIND_SUPERVISOR_SCOPE,
    ALL_PAGES,
    REGISTERED_ACCESS_KINDS,
    VisibilityQueryService,
)

from ._factories import (
    IS_PG,
    mk_project,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
    run_isolated,
)


# ---------------------------------------------------------------------------
# 本地工厂：委派历史快照（Task 2 append-only 表；仅在事务内 insert，回滚清理）
# ---------------------------------------------------------------------------
async def mk_delegation_history(
    s: AsyncSession,
    project_id,
    wp_index_id,
    *,
    target_role: str,
    new_user_id,
    actor_user_id,
    layer: str | None = None,
    action: str = "assign",
    new_staff_id=None,
    sheet_key: str | None = None,
) -> WorkpaperDelegationHistory:
    h = WorkpaperDelegationHistory(
        project_id=project_id,
        wp_index_id=wp_index_id,
        layer=layer or ("lead" if target_role == "lead" else "row"),
        target_role=target_role,
        action=action,
        new_user_id=new_user_id,
        new_staff_id=new_staff_id,
        actor_user_id=actor_user_id,
        sheet_key=sheet_key,
    )
    s.add(h)
    await s.flush()
    return h


def _ctx(user_id: UUID, project_id: UUID, role: VisibilityRole, scope) -> VisibilityContext:
    is_admin = role is VisibilityRole.admin
    return VisibilityContext(
        user_id=user_id,
        project_id=project_id,
        role=role,
        is_admin=is_admin,
        scope_cycles=frozenset() if is_admin else frozenset(scope),
    )


def _kinds(grants) -> set[str]:
    return {g.access_kind for g in grants}


def _grant(grants, access_kind):
    for g in grants:
        if g.access_kind == access_kind:
            return g
    return None


# ===========================================================================
# 示例：grant kinds 与页面范围（Property 5 / 7 / 8）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestGrantExamples:
    async def test_lead_grant_all_pages(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        wp = await mk_working_paper(session, proj.id, wi.id)
        wp.assigned_to = user.id
        await session.flush()

        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        gs = await VisibilityQueryService(session).grants_for_project(ctx)
        grants = gs.grants_for(wi.id)
        lead = _grant(grants, ACCESS_KIND_LEAD)
        assert lead is not None
        assert lead.allowed_sheet_keys == ALL_PAGES
        assert lead.readonly is False
        assert lead.identity == "workpaper_lead"

    async def test_assignee_grant_only_mapped_sheet(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        from ._factories import mk_row_task

        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="页甲",
            assignee_staff_id=staff.id,
        )
        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2B", sheet_name="页乙",
            assignee_staff_id=staff.id,
        )
        # 一张我不负责的行任务（别的 staff）→ 不进 assignee 页面集
        other_staff = await mk_staff(session, user_id=(await mk_user(session)).id)
        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2C", sheet_name="页丙",
            assignee_staff_id=other_staff.id,
        )

        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        grants = await VisibilityQueryService(session).grants_for_wp_index(ctx, wi.id)
        assignee = _grant(grants, ACCESS_KIND_ASSIGNEE)
        assert assignee is not None
        # 仅我负责的 sheet_key，且是页面级 frozenset（非整稿）
        assert assignee.allowed_sheet_keys == frozenset({"D2A", "D2B"})
        assert assignee.covers_sheet("D2A") is True
        assert assignee.covers_sheet("D2C") is False

    async def test_reviewer_grant_mapped_sheet(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        from ._factories import mk_row_task

        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="页甲",
            reviewer_staff_id=staff.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        grants = await VisibilityQueryService(session).grants_for_wp_index(ctx, wi.id)
        rev = _grant(grants, ACCESS_KIND_REVIEWER)
        assert rev is not None
        assert rev.allowed_sheet_keys == frozenset({"D2A"})
        assert rev.readonly is False

    async def test_cancelled_task_excluded(self, session):
        """active = is_deleted=false AND workflow_status<>'cancelled'。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        from ._factories import mk_row_task

        t = await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="页",
            assignee_staff_id=staff.id,
        )
        t.workflow_status = "cancelled"
        await session.flush()

        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        gs = await VisibilityQueryService(session).grants_for_project(ctx)
        assert gs.is_visible(wi.id) is False

    async def test_nullable_wp_still_counted(self, session):
        """assignee 行任务 wp_id=NULL 仍以 wp_index 计入可见集。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        from ._factories import mk_row_task

        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="页",
            wp_id=None, assignee_staff_id=staff.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        gs = await VisibilityQueryService(session).grants_for_project(ctx)
        assert gs.is_visible(wi.id) is True

    async def test_admin_all_project_ignores_scope(self, session):
        proj = await mk_project(session)
        admin = await mk_user(session)
        wi_d = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        wi_k = await mk_wp_index(session, proj.id, wp_code="K1-1", audit_cycle="K")
        # admin scope 恒空，但应看到全部 cycle 的 wp
        ctx = _ctx(admin.id, proj.id, VisibilityRole.admin, set())
        gs = await VisibilityQueryService(session).grants_for_project(ctx)
        assert gs.is_visible(wi_d.id) and gs.is_visible(wi_k.id)
        g = gs.grants_for(wi_d.id)
        assert _kinds(g) == {ACCESS_KIND_ADMIN}
        assert _grant(g, ACCESS_KIND_ADMIN).allowed_sheet_keys == ALL_PAGES

    async def test_supervisor_scope_grant(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        wi_d = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        wi_k = await mk_wp_index(session, proj.id, wp_code="K1-1", audit_cycle="K")
        ctx = _ctx(user.id, proj.id, VisibilityRole.supervisor, {"D"})
        gs = await VisibilityQueryService(session).grants_for_project(ctx)
        # scope 内 D 可见（supervisor_scope, all pages）；scope 外 K 不可见
        assert gs.is_visible(wi_d.id) is True
        assert gs.is_visible(wi_k.id) is False
        sup = _grant(gs.grants_for(wi_d.id), ACCESS_KIND_SUPERVISOR_SCOPE)
        assert sup is not None and sup.allowed_sheet_keys == ALL_PAGES

    async def test_history_lead_all_pages_readonly(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        actor = await mk_user(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await mk_delegation_history(
            session, proj.id, wi.id, target_role="lead",
            new_user_id=user.id, actor_user_id=actor.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        grants = await VisibilityQueryService(session).grants_for_wp_index(ctx, wi.id)
        lh = _grant(grants, ACCESS_KIND_LEAD_HISTORY)
        assert lh is not None
        assert lh.allowed_sheet_keys == ALL_PAGES  # Req 5.17
        assert lh.readonly is True  # Req 5.12

    async def test_history_row_snapshot_sheet_readonly(self, session):
        proj = await mk_project(session)
        user = await mk_user(session)
        actor = await mk_user(session)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        await mk_delegation_history(
            session, proj.id, wi.id, target_role="assignee",
            new_user_id=user.id, actor_user_id=actor.id, sheet_key="D2A",
        )
        await mk_delegation_history(
            session, proj.id, wi.id, target_role="reviewer",
            new_user_id=user.id, actor_user_id=actor.id, sheet_key="D2B",
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        grants = await VisibilityQueryService(session).grants_for_wp_index(ctx, wi.id)
        rh = _grant(grants, ACCESS_KIND_ROW_HISTORY)
        assert rh is not None
        assert rh.allowed_sheet_keys == frozenset({"D2A", "D2B"})  # Req 5.18 快照 sheet
        assert rh.readonly is True

    async def test_history_out_of_scope_excluded(self, session):
        """Non_Admin history grants 也与 scope 相交。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        actor = await mk_user(session)
        wi_k = await mk_wp_index(session, proj.id, wp_code="K1-1", audit_cycle="K")
        await mk_delegation_history(
            session, proj.id, wi_k.id, target_role="lead",
            new_user_id=user.id, actor_user_id=actor.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})  # scope 无 K
        gs = await VisibilityQueryService(session).grants_for_project(ctx)
        assert gs.is_visible(wi_k.id) is False

    async def test_multi_identity_union_same_wp(self, session):
        """同一 wp_index 同时是 lead + assignee → 两个独立 grant（Req 5.11/5.15）。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        wp = await mk_working_paper(session, proj.id, wi.id)
        wp.assigned_to = user.id
        await session.flush()
        from ._factories import mk_row_task

        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="页",
            assignee_staff_id=staff.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        grants = await VisibilityQueryService(session).grants_for_wp_index(ctx, wi.id)
        assert _kinds(grants) == {ACCESS_KIND_LEAD, ACCESS_KIND_ASSIGNEE}

    async def test_empty_scope_no_fallback(self, session):
        """scope 为空 → 空可见集（不回退循环级，Req 5.3）。"""
        proj = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi = await mk_wp_index(session, proj.id, wp_code="D2-1", audit_cycle="D")
        from ._factories import mk_row_task

        await mk_row_task(
            session, proj.id, wi.id, sheet_key="D2A", sheet_name="页",
            assignee_staff_id=staff.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, set())
        gs = await VisibilityQueryService(session).grants_for_project(ctx)
        assert gs.wp_index_ids() == frozenset()

    async def test_cross_project_wp_excluded(self, session):
        """别的项目的 wp_index 不进本项目可见集。"""
        proj = await mk_project(session)
        other = await mk_project(session)
        user = await mk_user(session)
        staff = await mk_staff(session, user_id=user.id)
        wi_other = await mk_wp_index(session, other.id, wp_code="D2-1", audit_cycle="D")
        from ._factories import mk_row_task

        await mk_row_task(
            session, other.id, wi_other.id, sheet_key="D2A", sheet_name="页",
            assignee_staff_id=staff.id,
        )
        ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
        gs = await VisibilityQueryService(session).grants_for_project(ctx)
        assert gs.is_visible(wi_other.id) is False


# ===========================================================================
# PBT Property 5: Restricted visibility equals the fixed set formula
# Validates: Requirements 5.1, 5.2, 5.3, 5.4
# (prompt "Property 7")
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestProperty5FixedSetFormula:
    @given(
        give_lead=st.booleans(),
        give_assignee=st.booleans(),
        give_history=st.booleans(),
        in_scope=st.booleans(),
        empty_scope=st.booleans(),
        nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_visible_equals_delegated_union_history_intersect_scope(
        self, give_lead, give_assignee, give_history, in_scope, empty_scope, nonce
    ):
        async def scenario(s):
            from ._factories import mk_row_task

            proj = await mk_project(s)
            user = await mk_user(s)
            actor = await mk_user(s)
            staff = await mk_staff(s, user_id=user.id)
            cycle = "D" if in_scope else "K"
            wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle=cycle)

            delegated = False
            history = False
            if give_lead:
                wp = await mk_working_paper(s, proj.id, wi.id)
                wp.assigned_to = user.id
                await s.flush()
                delegated = True
            if give_assignee:
                await mk_row_task(
                    s, proj.id, wi.id, sheet_key="D2A", sheet_name="页",
                    assignee_staff_id=staff.id,
                )
                delegated = True
            if give_history:
                await mk_delegation_history(
                    s, proj.id, wi.id, target_role="lead",
                    new_user_id=user.id, actor_user_id=actor.id,
                )
                history = True

            scope = set() if empty_scope else {"D"}
            ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, scope)
            gs = await VisibilityQueryService(s).grants_for_project(ctx)

            # 固定公式：可见 ⇔ (delegated ∪ history) ∧ (wp 在 scope) ∧ scope 非空
            in_formula = (
                (delegated or history)
                and (not empty_scope)
                and in_scope
            )
            assert gs.is_visible(wi.id) is in_formula
            # 去重：wp_index 作为 dict key，至多一条
            assert len(gs.by_wp_index) == (1 if in_formula else 0)

        run_isolated(scenario)


# ===========================================================================
# PBT Property 8: every grant has exactly one registered access_kind
# Validates: Requirements 5.15, 5.16
# (prompt "Property 8")
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestProperty8OneKnownKindPerGrant:
    @given(
        as_lead=st.booleans(),
        as_assignee=st.booleans(),
        as_reviewer=st.booleans(),
        as_history=st.booleans(),
        nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_each_grant_single_registered_kind(
        self, as_lead, as_assignee, as_reviewer, as_history, nonce
    ):
        async def scenario(s):
            from ._factories import mk_row_task

            proj = await mk_project(s)
            user = await mk_user(s)
            actor = await mk_user(s)
            staff = await mk_staff(s, user_id=user.id)
            wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")

            if as_lead:
                wp = await mk_working_paper(s, proj.id, wi.id)
                wp.assigned_to = user.id
                await s.flush()
            if as_assignee:
                await mk_row_task(
                    s, proj.id, wi.id, sheet_key="D2A", sheet_name="甲",
                    assignee_staff_id=staff.id,
                )
            if as_reviewer:
                await mk_row_task(
                    s, proj.id, wi.id, sheet_key="D2B", sheet_name="乙",
                    reviewer_staff_id=staff.id,
                )
            if as_history:
                await mk_delegation_history(
                    s, proj.id, wi.id, target_role="assignee",
                    new_user_id=user.id, actor_user_id=actor.id, sheet_key="D2C",
                )

            ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
            grants = await VisibilityQueryService(s).grants_for_wp_index(ctx, wi.id)
            # 每个 grant 恰一个已登记 access_kind；同 wp 内 access_kind 唯一（不重复）
            kinds = [g.access_kind for g in grants]
            for k in kinds:
                assert k in REGISTERED_ACCESS_KINDS
            assert len(kinds) == len(set(kinds))
            # 页面级 kind 的范围必为 frozenset；all-page kind 必为 'all'
            for g in grants:
                if g.access_kind in {ACCESS_KIND_ASSIGNEE, ACCESS_KIND_REVIEWER,
                                     ACCESS_KIND_ROW_HISTORY}:
                    assert isinstance(g.allowed_sheet_keys, frozenset)
                else:
                    assert g.allowed_sheet_keys == ALL_PAGES

        run_isolated(scenario)


# ===========================================================================
# PBT Property 7: page visibility follows role + history current-version-only
# Validates: Requirements 5.5–5.14, 5.17, 5.18
# (prompt "Property 9 Sheet_Key 页面隔离" + "Property 10 history current-version-only")
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestProperty7PageVisibilityAndHistoryReadonly:
    @given(
        my_sheet=st.sampled_from(["D2A", "D2B"]),
        query_sheet=st.sampled_from(["D2A", "D2B", "D2Z"]),
        nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_row_only_page_isolation(self, my_sheet, query_sheet, nonce):
        async def scenario(s):
            from ._factories import mk_row_task

            proj = await mk_project(s)
            user = await mk_user(s)
            staff = await mk_staff(s, user_id=user.id)
            wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
            await mk_row_task(
                s, proj.id, wi.id, sheet_key=my_sheet, sheet_name=f"n-{my_sheet}",
                assignee_staff_id=staff.id,
            )
            ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
            grants = await VisibilityQueryService(s).grants_for_wp_index(ctx, wi.id)
            assignee = _grant(grants, ACCESS_KIND_ASSIGNEE)
            assert assignee is not None
            # 只覆盖被委派 sheet；其他 sheet 不覆盖（页面隔离，未映射页交 gate 转 404）
            assert assignee.covers_sheet(query_sheet) is (query_sheet == my_sheet)
            # row 级 grant 绝不退化整稿
            assert assignee.allowed_sheet_keys != ALL_PAGES

        run_isolated(scenario)

    @given(
        role=st.sampled_from(["lead", "assignee", "reviewer"]),
        nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_history_grants_are_readonly(self, role, nonce):
        async def scenario(s):
            proj = await mk_project(s)
            user = await mk_user(s)
            actor = await mk_user(s)
            wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
            await mk_delegation_history(
                s, proj.id, wi.id, target_role=role,
                new_user_id=user.id, actor_user_id=actor.id,
                sheet_key=None if role == "lead" else "D2A",
            )
            ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
            grants = await VisibilityQueryService(s).grants_for_wp_index(ctx, wi.id)
            hist_kind = ACCESS_KIND_LEAD_HISTORY if role == "lead" else ACCESS_KIND_ROW_HISTORY
            g = _grant(grants, hist_kind)
            assert g is not None
            assert g.readonly is True  # History_Only 只读 Current_Version
            if role == "lead":
                assert g.allowed_sheet_keys == ALL_PAGES  # 整稿当前页面
            else:
                assert g.allowed_sheet_keys == frozenset({"D2A"})  # 快照 sheet

        run_isolated(scenario)


# ===========================================================================
# PBT Property 6: delegation history is immutable after rebinding
# Validates: Requirements 3.13, 3.14, 5.2, 5.18
# (prompt "Property 6")
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestProperty6HistoryImmutableAfterRebind:
    @given(
        rebind_staff=st.booleans(),
        soft_delete_task=st.booleans(),
        nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
    )
    @settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_history_attribution_unchanged_by_rebind(self, rebind_staff, soft_delete_task, nonce):
        async def scenario(s):
            from ._factories import mk_row_task

            proj = await mk_project(s)
            user = await mk_user(s)
            actor = await mk_user(s)
            staff = await mk_staff(s, user_id=user.id)
            wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")

            # 历史事件：user 曾作为 assignee 参与（快照 new_user_id + new_staff_id + sheet_key）
            await mk_delegation_history(
                s, proj.id, wi.id, target_role="assignee",
                new_user_id=user.id, new_staff_id=staff.id,
                actor_user_id=actor.id, sheet_key="D2A",
            )
            # 一张当前行任务（可被重绑/软删）
            t = await mk_row_task(
                s, proj.id, wi.id, sheet_key="D2A", sheet_name="页",
                assignee_staff_id=staff.id,
            )

            ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
            before = await VisibilityQueryService(s).grants_for_wp_index(ctx, wi.id)
            rh_before = _grant(before, ACCESS_KIND_ROW_HISTORY)
            assert rh_before is not None
            assert rh_before.allowed_sheet_keys == frozenset({"D2A"})

            # 重绑：改 staff 的 user_id（映射变更）/ 软删当前行任务
            if rebind_staff:
                staff.user_id = (await mk_user(s)).id
                await s.flush()
            if soft_delete_task:
                t.is_deleted = True
                await s.flush()

            after = await VisibilityQueryService(s).grants_for_wp_index(ctx, wi.id)
            rh_after = _grant(after, ACCESS_KIND_ROW_HISTORY)
            # 历史归属只依赖不可变快照 new_user_id + snapshot sheet_key，重绑/软删不改变
            assert rh_after is not None
            assert rh_after.allowed_sheet_keys == frozenset({"D2A"})
            assert rh_after.readonly is True

        run_isolated(scenario)


# ===========================================================================
# no-N+1: 可见集用常量条查询构建（Design Testing Strategy；prompt "Property 20"）
# Validates: Requirements 5.1–5.4（可见集构建）+ Design Testing Strategy（无按底稿 N+1）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
class TestNoPerWorkpaperN1:
    @staticmethod
    def _run_with_query_count(n_wps: int) -> int:
        async def _wrap() -> int:
            engine = create_async_engine(app_settings.DATABASE_URL)
            counter = {"n": 0}

            @event.listens_for(engine.sync_engine, "before_cursor_execute")
            def _count(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
                counter["n"] += 1

            conn = await engine.connect()
            trans = await conn.begin()
            s = AsyncSession(bind=conn)
            try:
                from ._factories import mk_row_task

                proj = await mk_project(s)
                user = await mk_user(s)
                staff = await mk_staff(s, user_id=user.id)
                # n_wps 张底稿，各一张 assignee 行任务
                for i in range(n_wps):
                    wi = await mk_wp_index(
                        s, proj.id, wp_code=f"D2-{i}", audit_cycle="D"
                    )
                    await mk_row_task(
                        s, proj.id, wi.id, sheet_key=f"S{i}", sheet_name=f"页{i}",
                        assignee_staff_id=staff.id,
                    )
                await s.flush()

                ctx = _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"})
                counter["n"] = 0  # 只统计 grants 构建阶段的往返
                gs = await VisibilityQueryService(s).grants_for_project(ctx)
                assert len(gs.by_wp_index) == n_wps  # 全部可见
                return counter["n"]
            finally:
                await s.close()
                await trans.rollback()
                await conn.close()
                await engine.dispose()

        return asyncio.run(_wrap())

    def test_query_count_constant_regardless_of_wp_count(self):
        small = self._run_with_query_count(2)
        large = self._run_with_query_count(12)
        # Restricted：active_staff_ids(1) + 单次 UNION(1) = 常量，不随底稿数量增长
        assert small == large
        assert small <= 3
