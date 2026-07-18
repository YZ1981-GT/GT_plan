# Feature: procedure-delegation-visibility-isolation — Task 7 (C12 DelegationTransaction)
"""两层委派原子事务的 Hypothesis 属性测试（fast profile · 真实 PostgreSQL）。

每个 Hypothesis example 经 ``_factories.run_isolated`` 在独立引擎/连接/事务内插入并回滚，
绝不污染 dev 库。SQL 集合语义与事务原子性必须在 PostgreSQL 验证（非 sqlite）。

**属性编号以 design.md 为权威**（Requirements Traceability 表 + Correctness Properties 段）：
  - **P2**（Staff/user identity require a unique active mapping）：user/staff 仅通过目标项目
    唯一 active 双向映射判同人，字段值直接相等不放行；映射不成立即拒绝且不改数据。
    Validates: Req 2.4–2.6, 3.1–3.6。
  - **P3**（Delegation layers never overwrite each other）：row 角色不产生 Staff_Projection；
    任一层变更或定向清空保留另一层及非目标 row 角色。Validates: Req 2.1–2.3, 2.11–2.15,
    3.7, 3.9–3.12, 3.15。
  - **P17**（Permission changes and persistent invalidation commit atomically）：每次委派同事务
    持久递增 policy epoch 并写 invalidation outbox（幂等不重复递增）。Validates: Req 3.14,
    14.20；崩溃恢复 outbox pending 见 P18/Req 14.21。
  - Req 6.1–6.8（跨循环 scope 扩权事务；design 追溯 Req6→P10/atomic 归 P17）：目标循环不在
    scope 且未扩权拒绝；显式 ``expand_scope`` + 非空 reason 才同事务写 scope 并集 + 委派 + 审计。

**prompt 属性编号 → design 属性编号映射**（本仓 design 为唯一权威）：
  - prompt "Property 3（two-layer authority + mapping same-person）" → design **P2 + P3**
  - prompt "Property 4（layers never overwrite + targeted clear）"    → design **P3**
  - prompt "Property 5（mapping-transaction invariants）"             → design **P2**
  - prompt "Property 11（Scope_Expansion atomic tx）"                 → design **Req 6 / P17（原子提交）**
  - prompt "Property 17（permission-change + epoch/invalidation commit atomically）" → design **P17**

fast profile：不显式设置 ``max_examples``，沿用 backend/tests/conftest.py 注册的全局 ``fast``
profile（``max_examples=5``，deadline=None）。CI Correctness_Profile（每属性 ≥100 有效样例）由
Task 14 统一收集同源属性函数，本文件为委派事务的属性定义与 smoke 落点。
"""
from __future__ import annotations

import sqlalchemy as sa
from hypothesis import given
from hypothesis import strategies as st

from app.models.core import ProjectUser
from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import WorkingPaper
from app.models.wp_visibility_models import (
    WorkpaperDelegationHistory,
    WpVisibilityInvalidationOutbox,
    WpVisibilityPolicyEpoch,
)
from app.services.wp_visibility.delegation_transaction import (
    DelegationError,
    DelegationRejectReason,
    DelegationTransactionService,
    LeadDelegationRequest,
    RowDelegationRequest,
)
from tests.procedure_delegation_visibility._factories import (
    IS_PG,
    mk_assignment,
    mk_procedure_instance,
    mk_project,
    mk_project_user,
    mk_row_task,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
    run_isolated,
)

import pytest

pytestmark = pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (delegation SQL/txn semantics)")


# ---------------------------------------------------------------------------
# 局部 setup helpers（复用 _factories；构造一名合法自然人与底稿）
# ---------------------------------------------------------------------------
async def _person(s, project, *, scope="D", role="manager"):
    """项目内唯一 active staff↔user 映射 + scope（合法可委派自然人）。"""
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    await mk_assignment(s, project.id, staff.id, role=role)
    await mk_project_user(s, project.id, user.id, role="auditor", scope_cycles=scope)
    return user, staff


async def _wp(s, project, *, cycle="D", wp_code="D2"):
    wi = await mk_wp_index(s, project.id, wp_code=wp_code, audit_cycle=cycle)
    wp = await mk_working_paper(s, project.id, wi.id)
    inst = await mk_procedure_instance(
        s, project.id, audit_cycle=cycle, wp_code=wp_code, wp_id=wp.id
    )
    return wi, wp, inst


# ===========================================================================
# design P2 — staff↔user 唯一 active 映射判同人；映射不成立即拒绝且不改数据
# （prompt P5 mapping-transaction invariants + prompt P3 same-person）
# Validates: Requirements 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
# ===========================================================================
@given(
    scenario=st.sampled_from(["valid", "cross_project", "inactive_staff", "no_user_id"]),
    nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
)
def test_pbt_mapping_transaction_invariants(scenario, nonce):
    async def _scenario(s):
        project = await mk_project(s)
        wi, wp, inst = await _wp(s, project)
        svc = DelegationTransactionService(s)

        if scenario == "valid":
            user, staff = await _person(s, project)
            res = await svc.delegate_lead(
                LeadDelegationRequest(
                    project_id=project.id, actor_user_id=user.id, staff_id=staff.id,
                    wp_index_id=wi.id, procedure_instance_id=inst.id,
                )
            )
            assert res.ok and res.user_id == user.id and res.staff_id == staff.id
            await s.refresh(wp)
            await s.refresh(inst)
            # 权威=user_id、投影=staff_id：值不同，靠映射判同人（Req 2.4–2.6）
            assert wp.assigned_to == user.id
            assert inst.assigned_to == staff.id
            assert user.id != staff.id
            return

        # ---- 非法映射：构造后 delegate 必须拒绝且不改数据（Req 3.5）----
        if scenario == "cross_project":
            other = await mk_project(s)
            user, staff = await _person(s, other, scope="D")  # staff 属于 other_project
            await mk_project_user(s, project.id, user.id, role="auditor", scope_cycles="D")
        elif scenario == "inactive_staff":
            user = await mk_user(s)
            staff = await mk_staff(s, user_id=user.id, is_deleted=True)  # inactive
            await mk_assignment(s, project.id, staff.id, role="manager")
            await mk_project_user(s, project.id, user.id, role="auditor", scope_cycles="D")
        else:  # no_user_id
            staff = await mk_staff(s, user_id=None)  # 无 user_id
            await mk_assignment(s, project.id, staff.id, role="manager")
            user = await mk_user(s)

        with pytest.raises(DelegationError) as ei:
            await svc.delegate_lead(
                LeadDelegationRequest(
                    project_id=project.id, actor_user_id=user.id, staff_id=staff.id,
                    wp_index_id=wi.id, procedure_instance_id=inst.id,
                )
            )
        assert ei.value.reason == DelegationRejectReason.mapping_invalid
        await s.refresh(wp)
        await s.refresh(inst)
        assert wp.assigned_to is None      # 未改权威
        assert inst.assigned_to is None    # 未改投影

    run_isolated(_scenario)


# ===========================================================================
# design P3 — 两层永不互相覆盖；row 不写投影；定向清空保留另一层/另一 row 角色
# （prompt P4 layers never overwrite + targeted clear）
# Validates: Requirements 2.1–2.3, 2.11–2.15, 3.7, 3.9–3.12, 3.15
# ===========================================================================
@given(
    op_order=st.permutations(["lead", "assignee", "reviewer"]),
    clear_target=st.sampled_from([None, "assignee", "reviewer", "lead"]),
    nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
)
def test_pbt_layers_never_overwrite(op_order, clear_target, nonce):
    async def _scenario(s):
        project = await mk_project(s)
        lead_u, lead_st = await _person(s, project)
        a_u, a_st = await _person(s, project)
        r_u, r_st = await _person(s, project)
        wi, wp, inst = await _wp(s, project)
        task = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_id=wp.id)
        svc = DelegationTransactionService(s)

        async def _do(layer):
            if layer == "lead":
                await svc.delegate_lead(
                    LeadDelegationRequest(
                        project_id=project.id, actor_user_id=lead_u.id, staff_id=lead_st.id,
                        wp_index_id=wi.id, procedure_instance_id=inst.id,
                    )
                )
            else:
                staff = a_st if layer == "assignee" else r_st
                actor = a_u if layer == "assignee" else r_u
                await svc.delegate_row(
                    RowDelegationRequest(
                        project_id=project.id, actor_user_id=actor.id,
                        task_id=task.id, target_role=layer, staff_id=staff.id,
                    )
                )

        # 任意顺序执行三层委派 —— 无论顺序，最终三层各自独立生效、互不覆盖
        for layer in op_order:
            await _do(layer)

        await s.refresh(wp)
        await s.refresh(inst)
        await s.refresh(task)
        assert wp.assigned_to == lead_u.id           # lead 权威
        assert inst.assigned_to == lead_st.id         # lead 投影（row 从不写此字段，Req 3.15）
        assert task.assignee_staff_id == a_st.id      # row assignee
        assert task.reviewer_staff_id == r_st.id      # row reviewer

        # ---- 定向清空：只清目标，保留其余层 ----
        if clear_target == "assignee":
            await svc.delegate_row(RowDelegationRequest(
                project_id=project.id, actor_user_id=a_u.id,
                task_id=task.id, target_role="assignee", clear=True))
            await s.refresh(task); await s.refresh(wp); await s.refresh(inst)
            assert task.assignee_staff_id is None
            assert task.reviewer_staff_id == r_st.id
            assert wp.assigned_to == lead_u.id and inst.assigned_to == lead_st.id
        elif clear_target == "reviewer":
            await svc.delegate_row(RowDelegationRequest(
                project_id=project.id, actor_user_id=r_u.id,
                task_id=task.id, target_role="reviewer", clear=True))
            await s.refresh(task); await s.refresh(wp); await s.refresh(inst)
            assert task.reviewer_staff_id is None
            assert task.assignee_staff_id == a_st.id
            assert wp.assigned_to == lead_u.id and inst.assigned_to == lead_st.id
        elif clear_target == "lead":
            await svc.delegate_lead(LeadDelegationRequest(
                project_id=project.id, actor_user_id=lead_u.id, clear=True,
                wp_index_id=wi.id, procedure_instance_id=inst.id))
            await s.refresh(task); await s.refresh(wp); await s.refresh(inst)
            assert wp.assigned_to is None and inst.assigned_to is None
            assert task.assignee_staff_id == a_st.id   # row 未受 lead 清空影响
            assert task.reviewer_staff_id == r_st.id

    run_isolated(_scenario)


# ===========================================================================
# design P17 — 权限变更同事务持久递增 epoch + 写 invalidation outbox；幂等不重复
# （prompt P17 permission-change + epoch/invalidation commit atomically）
# Validates: Requirements 3.14, 14.20
# ===========================================================================
@given(
    n=st.integers(min_value=1, max_value=4),
    reuse_request_id=st.booleans(),
    nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
)
def test_pbt_epoch_monotonic_and_atomic(n, reuse_request_id, nonce):
    async def _scenario(s):
        project = await mk_project(s)
        wi, wp, inst = await _wp(s, project)
        svc = DelegationTransactionService(s)
        persons = [await _person(s, project) for _ in range(n)]

        epochs: list[int] = []
        idem_hits = 0
        rid = "req-fixed" if reuse_request_id else None
        for user, staff in persons:
            res = await svc.delegate_lead(
                LeadDelegationRequest(
                    project_id=project.id, actor_user_id=user.id, staff_id=staff.id,
                    wp_index_id=wi.id, procedure_instance_id=inst.id, request_id=rid,
                )
            )
            if res.idempotent:
                idem_hits += 1
            else:
                epochs.append(res.epoch)

        # 非幂等委派数 = epoch 递增次数；epoch 严格单调
        assert epochs == sorted(epochs)
        assert len(set(epochs)) == len(epochs)

        if reuse_request_id and n > 1:
            # 复用同 request_id：仅首个落地，其余幂等命中，不重复递增/写 outbox
            assert idem_hits == n - 1
            assert len(epochs) == 1
        else:
            assert idem_hits == 0
            assert len(epochs) == n

        # 持久 epoch 行 = 最后一次递增值；outbox 行数 = 递增次数且全 pending（崩溃恢复）
        cur_epoch = (
            await s.execute(
                sa.select(WpVisibilityPolicyEpoch.epoch).where(
                    WpVisibilityPolicyEpoch.project_id == project.id
                )
            )
        ).scalar_one()
        assert cur_epoch == epochs[-1]
        outbox = (
            await s.execute(
                sa.select(WpVisibilityInvalidationOutbox).where(
                    WpVisibilityInvalidationOutbox.project_id == project.id
                )
            )
        ).scalars().all()
        assert len(outbox) == len(epochs)
        assert all(o.delivery_state == "pending" for o in outbox)
        assert {o.epoch for o in outbox} == set(epochs)

    run_isolated(_scenario)


# ===========================================================================
# Req 6.1–6.8 — 跨循环 scope 扩权原子事务（prompt P11 Scope_Expansion atomic tx）
# design 追溯：Req6→C12；原子提交属性归 P17（epoch/scope/委派/审计同事务）
# Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
# ===========================================================================
@given(
    in_scope=st.booleans(),
    expand=st.booleans(),
    reason=st.sampled_from(["", "   ", "跨循环支援复核"]),
    nonce=st.integers(min_value=0, max_value=2_000_000_000),  # Task14: correctness>=100 有效样例（宽域防早停）
)
def test_pbt_scope_expansion_atomic(in_scope, expand, reason, nonce):
    async def _scenario(s):
        project = await mk_project(s)
        # 目标底稿 cycle=D；被委派人 scope 含 D（in_scope）或仅 A（跨循环）
        user, staff = await _person(s, project, scope="D" if in_scope else "A")
        wi, wp, inst = await _wp(s, project, cycle="D", wp_code="D2")
        svc = DelegationTransactionService(s)
        req = LeadDelegationRequest(
            project_id=project.id, actor_user_id=user.id, staff_id=staff.id,
            wp_index_id=wi.id, procedure_instance_id=inst.id,
            expand_scope=expand, scope_reason=reason,
        )

        async def _scope_now():
            return (
                await s.execute(
                    sa.select(ProjectUser.scope_cycles).where(
                        ProjectUser.project_id == project.id,
                        ProjectUser.user_id == user.id,
                    )
                )
            ).scalar_one()

        if in_scope:
            # 目标循环在 scope：直接委派成功，scope 不变
            res = await svc.delegate_lead(req)
            assert res.ok
            assert set((await _scope_now()).split(",")) == {"D"}
            return

        # 跨循环
        if not expand:
            # Req 6.1：未扩权 → 拒绝且不改数据
            with pytest.raises(DelegationError) as ei:
                await svc.delegate_lead(req)
            assert ei.value.reason == DelegationRejectReason.out_of_scope
            await s.refresh(wp)
            assert wp.assigned_to is None
            assert set((await _scope_now()).split(",")) == {"A"}  # scope 未扩
            return

        if not reason.strip():
            # Req 6.3：扩权缺非空 reason → 拒绝且不改数据
            with pytest.raises(DelegationError) as ei:
                await svc.delegate_lead(req)
            assert ei.value.reason == DelegationRejectReason.scope_reason_missing
            await s.refresh(wp)
            assert wp.assigned_to is None
            assert set((await _scope_now()).split(",")) == {"A"}
            return

        # Req 6.2–6.6：显式扩权 + 非空 reason → 同事务写 scope 并集 + 委派 + 审计
        res = await svc.delegate_lead(req)
        assert res.ok
        await s.refresh(wp)
        await s.refresh(inst)
        assert wp.assigned_to == user.id and inst.assigned_to == staff.id  # 委派已写
        assert set((await _scope_now()).split(",")) == {"A", "D"}          # scope 并集
        hist = (
            await s.execute(
                sa.select(WorkpaperDelegationHistory).where(
                    WorkpaperDelegationHistory.wp_index_id == wi.id,
                    WorkpaperDelegationHistory.layer == "lead",
                )
            )
        ).scalars().all()
        assert len(hist) == 1
        assert hist[0].scope_before == ["A"] and hist[0].scope_after == ["A", "D"]  # 审计快照
        # 原子：epoch + outbox 同事务写入
        epoch = (
            await s.execute(
                sa.select(WpVisibilityPolicyEpoch.epoch).where(
                    WpVisibilityPolicyEpoch.project_id == project.id
                )
            )
        ).scalar_one()
        assert epoch == res.epoch

    run_isolated(_scenario)
