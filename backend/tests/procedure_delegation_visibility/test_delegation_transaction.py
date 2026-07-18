# Feature: procedure-delegation-visibility-isolation — Task 7 (C12 DelegationTransaction)
"""两层委派、清空、scope expansion 与 epoch 原子事务集成测试（真实 PostgreSQL）。

覆盖：
  - Property 3（两层永不互相覆盖）：lead 变更不动 row task；row 变更不动 lead/投影；
    定向清空一个 row 角色保留另一角色 + lead + 投影。
  - Property 17/18（权限变更 + epoch/invalidation 同事务原子）：delegate 写 policy epoch 递增
    + invalidation outbox（delivery_state=pending，供崩溃恢复）。
  - Req 2.4–2.6：两层通过唯一 active staff↔user 映射表达同一自然人（非字段值直接相等）。
  - Req 6.1–6.8：跨循环默认拒绝；显式 expand_scope + 非空 reason 才扩权；撤销不缩 scope。
  - Req 3.1–3.6：staff→user 映射不成立即拒绝并回滚。
  - request_id 幂等；顺序转派一致性（并发转派由 with_for_update 串行化）；崩溃恢复。

所有数据在事务隔离 session 内插入并回滚，不污染 dev 库。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.procedure_models import ProcedureInstance, ProcedureRowTask
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
    mk_assignment,
    mk_project,
    mk_project_user,
    mk_row_task,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
    mk_procedure_instance,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# setup helper：一名合法自然人（user↔staff 唯一 active 映射）+ 底稿/实例
# ---------------------------------------------------------------------------
async def _setup_person(s, project, *, cycle="D", scope="D", role="manager"):
    """在 project 内建立唯一 active staff↔user 映射 + scope。"""
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    await mk_assignment(s, project.id, staff.id, role=role)
    await mk_project_user(s, project.id, user.id, role="auditor", scope_cycles=scope)
    return user, staff


async def _setup_wp(s, project, *, cycle="D", wp_code="D2"):
    wi = await mk_wp_index(s, project.id, wp_code=wp_code, audit_cycle=cycle)
    wp = await mk_working_paper(s, project.id, wi.id)
    inst = await mk_procedure_instance(
        s, project.id, audit_cycle=cycle, wp_code=wp_code, wp_id=wp.id
    )
    return wi, wp, inst


async def test_lead_two_layer_same_person(session):
    """Req 2.2–2.5：lead 委派同事务写 working_paper.assigned_to=user_id +
    procedure_instances.assigned_to=staff_id，二者经映射表达同一自然人。"""
    s = session
    project = await mk_project(s)
    user, staff = await _setup_person(s, project)
    wi, wp, inst = await _setup_wp(s, project)

    svc = DelegationTransactionService(s)
    result = await svc.delegate_lead(
        LeadDelegationRequest(
            project_id=project.id,
            actor_user_id=user.id,
            staff_id=staff.id,
            wp_index_id=wi.id,
            procedure_instance_id=inst.id,
        )
    )
    assert result.ok and result.action == "assign"
    assert result.user_id == user.id and result.staff_id == staff.id

    await s.refresh(wp)
    await s.refresh(inst)
    # 权威字段是 user_id，投影字段是 staff_id（值不相等，靠映射判同人）
    assert wp.assigned_to == user.id
    assert inst.assigned_to == staff.id
    assert user.id != staff.id

    # 统一 delegation history 写入
    hist = (
        await s.execute(
            sa.select(WorkpaperDelegationHistory).where(
                WorkpaperDelegationHistory.wp_index_id == wi.id,
                WorkpaperDelegationHistory.layer == "lead",
            )
        )
    ).scalars().all()
    assert len(hist) == 1
    assert hist[0].new_user_id == user.id and hist[0].new_staff_id == staff.id


async def test_layers_never_overwrite(session):
    """Property 3：row 委派不改 lead/投影；lead 委派不改 row task。"""
    s = session
    project = await mk_project(s)
    lead_user, lead_staff = await _setup_person(s, project)
    row_user, row_staff = await _setup_person(s, project)
    wi, wp, inst = await _setup_wp(s, project)
    task = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_id=wp.id)

    svc = DelegationTransactionService(s)
    # 先 lead
    await svc.delegate_lead(
        LeadDelegationRequest(
            project_id=project.id, actor_user_id=lead_user.id,
            staff_id=lead_staff.id, wp_index_id=wi.id, procedure_instance_id=inst.id,
        )
    )
    # 再 row assignee —— 不得改动 lead/投影
    await svc.delegate_row(
        RowDelegationRequest(
            project_id=project.id, actor_user_id=row_user.id,
            task_id=task.id, target_role="assignee", staff_id=row_staff.id,
        )
    )
    await s.refresh(wp)
    await s.refresh(inst)
    await s.refresh(task)
    assert wp.assigned_to == lead_user.id       # lead 未被 row 覆盖
    assert inst.assigned_to == lead_staff.id      # 投影未被 row 覆盖
    assert task.assignee_staff_id == row_staff.id  # row 写入生效
    assert task.reviewer_staff_id is None

    # 再次 lead 转派 —— 不得改动 row task
    lead2_user, lead2_staff = await _setup_person(s, project)
    await svc.delegate_lead(
        LeadDelegationRequest(
            project_id=project.id, actor_user_id=lead2_user.id,
            staff_id=lead2_staff.id, wp_index_id=wi.id, procedure_instance_id=inst.id,
        )
    )
    await s.refresh(task)
    assert task.assignee_staff_id == row_staff.id  # row 未被 lead 覆盖


async def test_row_clear_preserves_other_role_and_lead(session):
    """Req 3.10–3.12：清空 assignee 保留 reviewer + lead + 投影。"""
    s = session
    project = await mk_project(s)
    lead_user, lead_staff = await _setup_person(s, project)
    a_user, a_staff = await _setup_person(s, project)
    r_user, r_staff = await _setup_person(s, project)
    wi, wp, inst = await _setup_wp(s, project)
    task = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_id=wp.id)

    svc = DelegationTransactionService(s)
    await svc.delegate_lead(
        LeadDelegationRequest(
            project_id=project.id, actor_user_id=lead_user.id,
            staff_id=lead_staff.id, wp_index_id=wi.id, procedure_instance_id=inst.id,
        )
    )
    await svc.delegate_row(
        RowDelegationRequest(project_id=project.id, actor_user_id=a_user.id,
                             task_id=task.id, target_role="assignee", staff_id=a_staff.id)
    )
    await svc.delegate_row(
        RowDelegationRequest(project_id=project.id, actor_user_id=r_user.id,
                             task_id=task.id, target_role="reviewer", staff_id=r_staff.id)
    )
    # 清空 assignee
    await svc.delegate_row(
        RowDelegationRequest(project_id=project.id, actor_user_id=a_user.id,
                             task_id=task.id, target_role="assignee", clear=True)
    )
    await s.refresh(task)
    await s.refresh(wp)
    await s.refresh(inst)
    assert task.assignee_staff_id is None            # 已清空
    assert task.reviewer_staff_id == r_staff.id      # 另一 row 角色保留
    assert wp.assigned_to == lead_user.id            # lead 保留
    assert inst.assigned_to == lead_staff.id          # 投影保留


async def test_lead_clear_preserves_row_tasks(session):
    """Req 3.9 + 2.14：清空 lead 同事务清 WP+投影，但保留全部 row task。"""
    s = session
    project = await mk_project(s)
    lead_user, lead_staff = await _setup_person(s, project)
    a_user, a_staff = await _setup_person(s, project)
    wi, wp, inst = await _setup_wp(s, project)
    task = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_id=wp.id)

    svc = DelegationTransactionService(s)
    await svc.delegate_lead(
        LeadDelegationRequest(project_id=project.id, actor_user_id=lead_user.id,
                              staff_id=lead_staff.id, wp_index_id=wi.id,
                              procedure_instance_id=inst.id)
    )
    await svc.delegate_row(
        RowDelegationRequest(project_id=project.id, actor_user_id=a_user.id,
                             task_id=task.id, target_role="assignee", staff_id=a_staff.id)
    )
    # 清空 lead
    res = await svc.delegate_lead(
        LeadDelegationRequest(project_id=project.id, actor_user_id=lead_user.id,
                              clear=True, wp_index_id=wi.id, procedure_instance_id=inst.id)
    )
    assert res.action == "clear"
    await s.refresh(wp)
    await s.refresh(inst)
    await s.refresh(task)
    assert wp.assigned_to is None
    assert inst.assigned_to is None
    assert task.assignee_staff_id == a_staff.id  # row 未受影响


async def test_epoch_and_outbox_atomic(session):
    """Property 17：每次委派同事务递增 policy epoch + 写 invalidation outbox。"""
    s = session
    project = await mk_project(s)
    user, staff = await _setup_person(s, project)
    wi, wp, inst = await _setup_wp(s, project)

    svc = DelegationTransactionService(s)
    r1 = await svc.delegate_lead(
        LeadDelegationRequest(project_id=project.id, actor_user_id=user.id,
                              staff_id=staff.id, wp_index_id=wi.id,
                              procedure_instance_id=inst.id)
    )
    epoch_row = (
        await s.execute(
            sa.select(WpVisibilityPolicyEpoch.epoch).where(
                WpVisibilityPolicyEpoch.project_id == project.id
            )
        )
    ).scalar_one()
    assert epoch_row == r1.epoch
    outbox = (
        await s.execute(
            sa.select(WpVisibilityInvalidationOutbox).where(
                WpVisibilityInvalidationOutbox.project_id == project.id
            )
        )
    ).scalars().all()
    assert len(outbox) == 1
    assert outbox[0].epoch == r1.epoch
    # 崩溃恢复：outbox 记录持久为 pending（即使 Redis fan-out 未发生）
    assert outbox[0].delivery_state == "pending"


async def test_request_id_idempotent(session):
    """request_id 幂等：重复请求不重复写 history / 不重复递增 epoch。"""
    s = session
    project = await mk_project(s)
    user, staff = await _setup_person(s, project)
    wi, wp, inst = await _setup_wp(s, project)
    svc = DelegationTransactionService(s)
    rid = f"req-{uuid.uuid4().hex[:12]}"

    r1 = await svc.delegate_lead(
        LeadDelegationRequest(project_id=project.id, actor_user_id=user.id,
                              staff_id=staff.id, wp_index_id=wi.id,
                              procedure_instance_id=inst.id, request_id=rid)
    )
    r2 = await svc.delegate_lead(
        LeadDelegationRequest(project_id=project.id, actor_user_id=user.id,
                              staff_id=staff.id, wp_index_id=wi.id,
                              procedure_instance_id=inst.id, request_id=rid)
    )
    assert r1.idempotent is False and r2.idempotent is True
    hist = (
        await s.execute(
            sa.select(sa.func.count()).select_from(WorkpaperDelegationHistory).where(
                WorkpaperDelegationHistory.request_id == rid
            )
        )
    ).scalar_one()
    assert hist == 1  # 未重复写
    outbox = (
        await s.execute(
            sa.select(sa.func.count()).select_from(WpVisibilityInvalidationOutbox).where(
                WpVisibilityInvalidationOutbox.project_id == project.id
            )
        )
    ).scalar_one()
    assert outbox == 1  # 未重复递增/写 outbox


async def test_sequential_reassignment_consistency(session):
    """并发转派（由 with_for_update 串行化）→ 顺序转派一致性：最终一人，两条历史，epoch 递增。"""
    s = session
    project = await mk_project(s)
    u1, st1 = await _setup_person(s, project)
    u2, st2 = await _setup_person(s, project)
    wi, wp, inst = await _setup_wp(s, project)
    svc = DelegationTransactionService(s)

    r1 = await svc.delegate_lead(
        LeadDelegationRequest(project_id=project.id, actor_user_id=u1.id,
                              staff_id=st1.id, wp_index_id=wi.id, procedure_instance_id=inst.id)
    )
    r2 = await svc.delegate_lead(
        LeadDelegationRequest(project_id=project.id, actor_user_id=u2.id,
                              staff_id=st2.id, wp_index_id=wi.id, procedure_instance_id=inst.id)
    )
    assert r1.action == "assign" and r2.action == "reassign"
    assert r2.epoch > r1.epoch
    await s.refresh(wp)
    await s.refresh(inst)
    assert wp.assigned_to == u2.id and inst.assigned_to == st2.id
    hist = (
        await s.execute(
            sa.select(sa.func.count()).select_from(WorkpaperDelegationHistory).where(
                WorkpaperDelegationHistory.wp_index_id == wi.id,
                WorkpaperDelegationHistory.layer == "lead",
            )
        )
    ).scalar_one()
    assert hist == 2


async def test_cross_cycle_default_reject(session):
    """Req 6.1：目标循环不在被委派人 scope 且未扩权 → 拒绝并回滚。"""
    s = session
    project = await mk_project(s)
    user, staff = await _setup_person(s, project, scope="A")  # scope 只有 A
    wi, wp, inst = await _setup_wp(s, project, wp_code="D2")   # wp_index cycle=D
    svc = DelegationTransactionService(s)
    with pytest.raises(DelegationError) as ei:
        await svc.delegate_lead(
            LeadDelegationRequest(project_id=project.id, actor_user_id=user.id,
                                  staff_id=staff.id, wp_index_id=wi.id,
                                  procedure_instance_id=inst.id)
        )
    assert ei.value.reason == DelegationRejectReason.out_of_scope
    await s.refresh(wp)
    assert wp.assigned_to is None  # 未改数据


async def test_scope_expansion_requires_reason_and_unions(session):
    """Req 6.2–6.5：显式 expand_scope + 非空 reason → 同事务写 scope 并集 + 委派。"""
    s = session
    project = await mk_project(s)
    user, staff = await _setup_person(s, project, scope="A")
    wi, wp, inst = await _setup_wp(s, project, wp_code="D2")  # cycle=D
    svc = DelegationTransactionService(s)

    # 缺 reason → 拒绝
    with pytest.raises(DelegationError) as ei:
        await svc.delegate_lead(
            LeadDelegationRequest(project_id=project.id, actor_user_id=user.id,
                                  staff_id=staff.id, wp_index_id=wi.id,
                                  procedure_instance_id=inst.id, expand_scope=True)
        )
    assert ei.value.reason == DelegationRejectReason.scope_reason_missing

    # 有 reason → 扩权成功，scope 并集 A,D
    res = await svc.delegate_lead(
        LeadDelegationRequest(project_id=project.id, actor_user_id=user.id,
                              staff_id=staff.id, wp_index_id=wi.id,
                              procedure_instance_id=inst.id,
                              expand_scope=True, scope_reason="跨循环支援")
    )
    assert res.ok
    from app.models.core import ProjectUser
    scope = (
        await s.execute(
            sa.select(ProjectUser.scope_cycles).where(
                ProjectUser.project_id == project.id, ProjectUser.user_id == user.id
            )
        )
    ).scalar_one()
    assert set(scope.split(",")) == {"A", "D"}
    # history 记录 scope_before/after
    h = (
        await s.execute(
            sa.select(WorkpaperDelegationHistory).where(
                WorkpaperDelegationHistory.wp_index_id == wi.id
            )
        )
    ).scalars().all()
    assert h[0].scope_before == ["A"] and h[0].scope_after == ["A", "D"]


async def test_revocation_does_not_shrink_scope(session):
    """Req 6.8：清空/撤销委派不缩 scope。"""
    s = session
    project = await mk_project(s)
    user, staff = await _setup_person(s, project, scope="A")
    wi, wp, inst = await _setup_wp(s, project, wp_code="D2")
    svc = DelegationTransactionService(s)
    await svc.delegate_lead(
        LeadDelegationRequest(project_id=project.id, actor_user_id=user.id,
                              staff_id=staff.id, wp_index_id=wi.id,
                              procedure_instance_id=inst.id,
                              expand_scope=True, scope_reason="跨循环支援")
    )
    # 撤销 lead
    await svc.delegate_lead(
        LeadDelegationRequest(project_id=project.id, actor_user_id=user.id,
                              clear=True, wp_index_id=wi.id, procedure_instance_id=inst.id)
    )
    from app.models.core import ProjectUser
    scope = (
        await s.execute(
            sa.select(ProjectUser.scope_cycles).where(
                ProjectUser.project_id == project.id, ProjectUser.user_id == user.id
            )
        )
    ).scalar_one()
    assert set(scope.split(",")) == {"A", "D"}  # 未缩回


async def test_mapping_invalid_rejects(session):
    """Req 3.1–3.6：staff 不属于目标项目（无 active assignment）→ 拒绝并回滚。"""
    s = session
    project = await mk_project(s)
    other_project = await mk_project(s)
    # staff 属于 other_project，不属于 project
    user, staff = await _setup_person(s, other_project, scope="D")
    await mk_project_user(s, project.id, user.id, role="auditor", scope_cycles="D")
    wi, wp, inst = await _setup_wp(s, project)
    svc = DelegationTransactionService(s)
    with pytest.raises(DelegationError) as ei:
        await svc.delegate_lead(
            LeadDelegationRequest(project_id=project.id, actor_user_id=user.id,
                                  staff_id=staff.id, wp_index_id=wi.id,
                                  procedure_instance_id=inst.id)
        )
    assert ei.value.reason == DelegationRejectReason.mapping_invalid
    await s.refresh(wp)
    assert wp.assigned_to is None


async def test_binding_conflict_rejects(session):
    """Req 4.11：wp_index 无法唯一解析（不存在的 wp_index）→ 拒绝。"""
    s = session
    project = await mk_project(s)
    user, staff = await _setup_person(s, project)
    svc = DelegationTransactionService(s)
    with pytest.raises(DelegationError) as ei:
        await svc.delegate_lead(
            LeadDelegationRequest(project_id=project.id, actor_user_id=user.id,
                                  staff_id=staff.id, wp_index_id=uuid.uuid4())
        )
    assert ei.value.reason == DelegationRejectReason.binding_conflict


async def test_projection_not_written_with_row_staff(session):
    """Req 3.15：row 委派绝不写 Staff_Projection（procedure_instances.assigned_to）。"""
    s = session
    project = await mk_project(s)
    r_user, r_staff = await _setup_person(s, project)
    wi, wp, inst = await _setup_wp(s, project)
    task = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_id=wp.id)
    svc = DelegationTransactionService(s)
    await svc.delegate_row(
        RowDelegationRequest(project_id=project.id, actor_user_id=r_user.id,
                             task_id=task.id, target_role="assignee", staff_id=r_staff.id)
    )
    await s.refresh(inst)
    assert inst.assigned_to is None  # 投影未被 row staff 写入


# ---------------------------------------------------------------------------
# 真实并发转派：两条已提交连接对同一 WP 行竞争，由 with_for_update 串行化
# （committed 数据 + finally 显式清理，不污染 dev 库）
# ---------------------------------------------------------------------------
async def test_concurrent_reassignment_serialized(session):
    """两个 delegator 并发对同一 wp_index 转派 lead：with_for_update 串行化 →
    最终恰好一人、epoch 严格递增、两条 lead history、无脏写。"""
    import asyncio as _asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.config import settings as app_settings

    # ---- 已提交 setup（并发连接需能互相看到）----
    setup_engine = create_async_engine(app_settings.DATABASE_URL)
    ids: dict = {}
    async with AsyncSession(setup_engine, expire_on_commit=False) as s:
        project = await mk_project(s)
        u1, st1 = await _setup_person(s, project)
        u2, st2 = await _setup_person(s, project)
        wi, wp, inst = await _setup_wp(s, project)
        # 提交前捕获 id（commit 后 ORM 属性过期会触发意外 IO）
        ids = {
            "project": project.id, "u1": u1.id, "u2": u2.id,
            "st1": st1.id, "st2": st2.id, "wi": wi.id, "wp": wp.id, "inst": inst.id,
        }
        await s.commit()

    async def _delegate(actor_id, staff_id):
        eng = create_async_engine(app_settings.DATABASE_URL)
        try:
            async with AsyncSession(eng) as s:
                svc = DelegationTransactionService(s)
                res = await svc.delegate_lead(
                    LeadDelegationRequest(
                        project_id=ids["project"], actor_user_id=actor_id,
                        staff_id=staff_id, wp_index_id=ids["wi"],
                        procedure_instance_id=ids["inst"],
                    )
                )
                await s.commit()
                return res
        finally:
            await eng.dispose()

    try:
        results = await _asyncio.gather(
            _delegate(ids["u1"], ids["st1"]),
            _delegate(ids["u2"], ids["st2"]),
        )
        assert all(r.ok for r in results)
        # 一条 assign + 一条 reassign（串行化后第二个看到第一个的已提交值）
        actions = sorted(r.action for r in results)
        assert actions == ["assign", "reassign"]
        epochs = sorted(r.epoch for r in results)
        assert epochs[0] < epochs[1]  # epoch 严格递增，无并发覆盖

        verify_engine = create_async_engine(app_settings.DATABASE_URL)
        async with AsyncSession(verify_engine) as s:
            wp_row = (
                await s.execute(
                    sa.select(WorkingPaper.assigned_to).where(WorkingPaper.id == ids["wp"])
                )
            ).scalar_one()
            assert wp_row in (ids["u1"], ids["u2"])  # 最终恰好一人
            inst_row = (
                await s.execute(
                    sa.select(ProcedureInstance.assigned_to).where(
                        ProcedureInstance.id == ids["inst"]
                    )
                )
            ).scalar_one()
            assert inst_row in (ids["st1"], ids["st2"])
            hist_n = (
                await s.execute(
                    sa.select(sa.func.count()).select_from(WorkpaperDelegationHistory).where(
                        WorkpaperDelegationHistory.wp_index_id == ids["wi"],
                        WorkpaperDelegationHistory.layer == "lead",
                    )
                )
            ).scalar_one()
            assert hist_n == 2
        await verify_engine.dispose()
    finally:
        # 显式清理（FK 安全顺序）
        clean_engine = create_async_engine(app_settings.DATABASE_URL)
        async with AsyncSession(clean_engine) as s:
            pid = ids["project"]
            for stmt in (
                sa.text("DELETE FROM wp_visibility_invalidation_outbox WHERE project_id=:p"),
                sa.text("DELETE FROM wp_visibility_policy_epoch WHERE project_id=:p"),
                sa.text("DELETE FROM workpaper_delegation_history WHERE project_id=:p"),
                sa.text("DELETE FROM procedure_instances WHERE project_id=:p"),
                sa.text("DELETE FROM working_paper WHERE project_id=:p"),
                sa.text("DELETE FROM wp_index WHERE project_id=:p"),
                sa.text("DELETE FROM project_assignments WHERE project_id=:p"),
                sa.text("DELETE FROM project_users WHERE project_id=:p"),
                sa.text("DELETE FROM staff_members WHERE id = ANY(:ids)"),
                sa.text("DELETE FROM users WHERE id = ANY(:ids)"),
                sa.text("DELETE FROM projects WHERE id=:p"),
            ):
                try:
                    if "staff_members" in stmt.text or "FROM users" in stmt.text:
                        await s.execute(
                            stmt, {"ids": [ids["st1"], ids["st2"]] if "staff" in stmt.text
                                    else [ids["u1"], ids["u2"]]}
                        )
                    else:
                        await s.execute(stmt, {"p": pid})
                except Exception:  # noqa: BLE001
                    pass
            await s.commit()
        await clean_engine.dispose()
    await setup_engine.dispose()


async def test_crash_recovery_outbox_persisted(session):
    """Property 18 / Req 14.21：权限已提交但 Redis fan-out 未发生（崩溃）→ 持久 policy epoch +
    invalidation outbox（delivery_state=pending）仍在 DB，供恢复期重查/拒绝 stale。"""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.config import settings as app_settings

    setup_engine = create_async_engine(app_settings.DATABASE_URL)
    ids: dict = {}
    async with AsyncSession(setup_engine, expire_on_commit=False) as s:
        project = await mk_project(s)
        user, staff = await _setup_person(s, project)
        wi, wp, inst = await _setup_wp(s, project)
        ids = {
            "project": project.id, "user": user.id, "staff": staff.id,
            "wi": wi.id, "inst": inst.id,
        }
        await s.commit()

    # ---- 提交委派（模拟"权限已提交"），全程无任何 Redis/publish 调用 ----
    commit_engine = create_async_engine(app_settings.DATABASE_URL)
    async with AsyncSession(commit_engine) as s:
        svc = DelegationTransactionService(s)
        res = await svc.delegate_lead(
            LeadDelegationRequest(project_id=ids["project"], actor_user_id=ids["user"],
                                  staff_id=ids["staff"], wp_index_id=ids["wi"],
                                  procedure_instance_id=ids["inst"])
        )
        committed_epoch = res.epoch
        await s.commit()
    await commit_engine.dispose()

    try:
        # ---- 全新连接（模拟恢复期节点）：持久 epoch + outbox 仍在 ----
        verify_engine = create_async_engine(app_settings.DATABASE_URL)
        async with AsyncSession(verify_engine) as s:
            epoch = (
                await s.execute(
                    sa.select(WpVisibilityPolicyEpoch.epoch).where(
                        WpVisibilityPolicyEpoch.project_id == ids["project"]
                    )
                )
            ).scalar_one()
            assert epoch == committed_epoch  # 持久 epoch 已提交
            ob = (
                await s.execute(
                    sa.select(WpVisibilityInvalidationOutbox).where(
                        WpVisibilityInvalidationOutbox.project_id == ids["project"]
                    )
                )
            ).scalars().all()
            assert len(ob) == 1
            assert ob[0].epoch == committed_epoch
            assert ob[0].delivery_state == "pending"  # fan-out 未投递，等待恢复重投
        await verify_engine.dispose()
    finally:
        clean_engine = create_async_engine(app_settings.DATABASE_URL)
        async with AsyncSession(clean_engine) as s:
            pid = ids["project"]
            for stmt in (
                sa.text("DELETE FROM wp_visibility_invalidation_outbox WHERE project_id=:p"),
                sa.text("DELETE FROM wp_visibility_policy_epoch WHERE project_id=:p"),
                sa.text("DELETE FROM workpaper_delegation_history WHERE project_id=:p"),
                sa.text("DELETE FROM procedure_instances WHERE project_id=:p"),
                sa.text("DELETE FROM working_paper WHERE project_id=:p"),
                sa.text("DELETE FROM wp_index WHERE project_id=:p"),
                sa.text("DELETE FROM project_assignments WHERE project_id=:p"),
                sa.text("DELETE FROM project_users WHERE project_id=:p"),
                sa.text("DELETE FROM staff_members WHERE id=:sid"),
                sa.text("DELETE FROM users WHERE id=:uid"),
                sa.text("DELETE FROM projects WHERE id=:p"),
            ):
                try:
                    params = {"p": pid}
                    if ":sid" in stmt.text:
                        params = {"sid": ids["staff"]}
                    elif ":uid" in stmt.text:
                        params = {"uid": ids["user"]}
                    await s.execute(stmt, params)
                except Exception:  # noqa: BLE001
                    pass
            await s.commit()
        await clean_engine.dispose()
    await setup_engine.dispose()
