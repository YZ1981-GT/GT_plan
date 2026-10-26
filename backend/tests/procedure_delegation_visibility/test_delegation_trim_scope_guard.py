"""委派只能委派保留项、被委派人须看得到（spec procedure-trim-generation-delegation-chain 需求 4 / 任务 11）。

真实 PostgreSQL，每个用例在回滚事务里建数据（``session`` fixture）。覆盖：
- 有效循环范围 ``resolve_member_scope``：主管（含中文别名）/ 系统管理员全部循环；受限 = 团队分配勾选 ∪ 扩权。
- 底稿主编委派：已粗裁（含跟随母码的子表）拒绝 409、清空不拦；主管免检；团队分配勾选的循环直接可派；
  缺循环拒绝并带 ``cycles``，扩权只写新增循环；非项目成员不能扩权；批量委派一次报全缺少的循环。
- 程序行委派：目标只取保留项（已裁 / 在回收站排除并计数）；按循环选择跟随底稿循环；preview ``scope_gaps``、
  apply 缺循环 400 零写、同一凭证带理由重试扩权；协调器兜底拒绝已裁任务；状态转换端点分配走同一路径。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ProjectUser
from app.models.wp_visibility_models import WorkpaperDelegationHistory, WpVisibilityInvalidationOutbox
from app.services.procedure_delegation_service import ProcedureDelegationService
from app.services.procedure_row_delegation_coordinator import ProcedureRowDelegationCoordinator
from app.services.procedure_service import ProcedureService
from app.services.wp_visibility.delegation_transaction import (
    DelegationError,
    DelegationRejectReason,
    DelegationTransactionService,
    LeadDelegationRequest,
)
from app.services.wp_visibility.effective_scope import STANDARD_CYCLES, resolve_member_scope
from tests.procedure_delegation_visibility._factories import (
    mk_assignment,
    mk_procedure_instance,
    mk_project,
    mk_project_user,
    mk_row_task,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)

pytestmark = pytest.mark.asyncio


async def _member(s, project, *, role="auditor", assigned=None, scope=None, project_user=True):
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    a = await mk_assignment(s, project.id, staff.id, role=role)
    a.assigned_cycles = list(assigned) if assigned is not None else None
    if project_user:
        await mk_project_user(s, project.id, user.id, role="auditor", scope_cycles=scope)
    await s.flush()
    return user, staff


async def _wp(s, project, code, cycle, *, with_instance=True):
    wi = await mk_wp_index(s, project.id, wp_code=code, audit_cycle=cycle)
    wp = await mk_working_paper(s, project.id, wi.id)
    inst = None
    if with_instance:
        inst = await mk_procedure_instance(s, project.id, audit_cycle=cycle, wp_code=code, wp_id=wp.id)
    return wi, wp, inst


async def _trim(s, project, code, cycle):
    inst = await mk_procedure_instance(s, project.id, audit_cycle=cycle, wp_code=code)
    inst.status = "skip"
    await s.flush()
    return inst


async def _scope_cycles(s, project, user):
    return (await s.execute(sa.select(ProjectUser.scope_cycles).where(
        ProjectUser.project_id == project.id, ProjectUser.user_id == user.id))).scalar()


def _lead(project, actor, staff, wi, inst=None, **kw):
    return LeadDelegationRequest(
        project_id=project.id, actor_user_id=actor.id, staff_id=staff.id, wp_index_id=wi.id,
        procedure_instance_id=inst.id if inst else None, wp_code=wi.wp_code, **kw,
    )


# ---------------------------------------------------------------------------
# 有效循环范围
# ---------------------------------------------------------------------------
async def test_member_scope_supervisor_admin_and_restricted(session):
    s = session
    project = await mk_project(s)
    await mk_wp_index(s, project.id, wp_code="Z1", audit_cycle="Z")
    mgr_user, _ = await _member(s, project, role="项目经理")
    admin = await mk_user(s, role="admin")
    aud_user, _ = await _member(s, project, assigned=["D"], scope="E")
    outsider, _ = await _member(s, project, assigned=["D"], project_user=False)

    mgr = await resolve_member_scope(s, project.id, mgr_user.id)
    assert mgr.is_supervisor and mgr.cycles == STANDARD_CYCLES | {"Z"}
    adm = await resolve_member_scope(s, project.id, admin.id)
    assert adm.is_supervisor and adm.is_admin and "Z" in adm.cycles
    aud = await resolve_member_scope(s, project.id, aud_user.id)
    assert not aud.is_supervisor and aud.cycles == {"D", "E"} and aud.assigned == {"D"} and aud.is_member
    out = await resolve_member_scope(s, project.id, outsider.id)
    assert out.cycles == {"D"} and not out.is_member


async def test_member_scope_duplicate_staff_is_restricted(session):
    """同一用户两份人员记录 ⇒ 链路不唯一，经理角色也按受限（与分类器同口径）。"""
    s = session
    project = await mk_project(s)
    user, staff = await _member(s, project, role="manager", assigned=["D"])
    await mk_staff(s, user_id=user.id)
    scope = await resolve_member_scope(s, project.id, user.id)
    assert not scope.is_supervisor and scope.cycles == {"D"}


# ---------------------------------------------------------------------------
# 底稿主编委派
# ---------------------------------------------------------------------------
async def test_lead_rejects_trimmed_child_but_clear_is_allowed(session):
    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    _user, staff = await _member(s, project, assigned=["H"])
    await _trim(s, project, "H3", "H")
    wi, wp, _ = await _wp(s, project, "H3-1", "H", with_instance=False)
    svc = DelegationTransactionService(s)

    with pytest.raises(DelegationError) as ei:
        await svc.delegate_lead(_lead(project, actor, staff, wi))
    assert ei.value.reason == DelegationRejectReason.trimmed
    assert ei.value.http_status == 409
    assert "跟随 H3" in str(ei.value)
    await s.refresh(wp)
    assert wp.assigned_to is None

    res = await svc.delegate_lead(LeadDelegationRequest(
        project_id=project.id, actor_user_id=actor.id, clear=True, wp_index_id=wi.id, wp_code="H3-1"))
    assert res.ok and res.action == "clear"


async def test_lead_supervisor_alias_skips_scope_check(session):
    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    user, staff = await _member(s, project, role="项目经理")
    wi, wp, inst = await _wp(s, project, "A1", "A")
    res = await DelegationTransactionService(s).delegate_lead(_lead(project, actor, staff, wi, inst))
    assert res.ok
    await s.refresh(wp)
    assert wp.assigned_to == user.id
    assert await _scope_cycles(s, project, user) is None  # 主管不扩权、不改范围


async def test_lead_assigned_cycles_count_and_expand_writes_only_missing(session):
    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    user, staff = await _member(s, project, assigned=["D"])
    wi_d, _wp_d, inst_d = await _wp(s, project, "D2", "D")
    wi_a, wp_a, inst_a = await _wp(s, project, "A1", "A")
    svc = DelegationTransactionService(s)

    # 团队分配勾选的 D 直接可派（原先只看 scope_cycles，勾选了也被拒）
    assert (await svc.delegate_lead(_lead(project, actor, staff, wi_d, inst_d))).ok

    with pytest.raises(DelegationError) as ei:
        await svc.delegate_lead(_lead(project, actor, staff, wi_a, inst_a))
    assert ei.value.reason == DelegationRejectReason.out_of_scope
    assert ei.value.cycles == ["A"]
    detail = ei.value.http_detail()
    assert detail["reason"] == "out_of_scope" and detail["cycles"] == ["A"] and "A" in detail["message"]

    res = await svc.delegate_lead(_lead(project, actor, staff, wi_a, inst_a, expand_scope=True, scope_reason="跨循环支援"))
    assert res.ok
    await s.refresh(wp_a)
    assert wp_a.assigned_to == user.id
    assert await _scope_cycles(s, project, user) == "A"  # 只写新增的 A，D 仍来自团队分配


async def test_lead_non_member_cannot_expand(session):
    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    _user, staff = await _member(s, project, assigned=["D"], project_user=False)
    wi_a, _wp_a, inst_a = await _wp(s, project, "A1", "A")
    with pytest.raises(DelegationError) as ei:
        await DelegationTransactionService(s).delegate_lead(
            _lead(project, actor, staff, wi_a, inst_a, expand_scope=True, scope_reason="跨循环支援"))
    assert ei.value.reason == DelegationRejectReason.not_project_member


async def test_batch_lead_reports_every_missing_cycle_once(session):
    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    user, staff = await _member(s, project, assigned=["D"])
    _wi_a, wp_a, inst_a = await _wp(s, project, "A1", "A")
    _wi_e, wp_e, inst_e = await _wp(s, project, "E1", "E")
    batch = [{"procedure_id": inst_a.id, "staff_id": staff.id}, {"procedure_id": inst_e.id, "staff_id": staff.id}]

    with pytest.raises(DelegationError) as ei:
        async with s.begin_nested():  # 路由在拒绝时回滚整批
            await ProcedureService(s).assign_procedures(project.id, batch, actor_user_id=actor.id)
    assert ei.value.reason == DelegationRejectReason.out_of_scope
    assert ei.value.cycles == ["A", "E"]
    await s.refresh(wp_a)
    assert wp_a.assigned_to is None

    n = await ProcedureService(s).assign_procedures(
        project.id, batch, actor_user_id=actor.id, expand_scope=True, scope_reason="跨循环支援")
    assert n == 2
    await s.refresh(wp_e)
    assert wp_e.assigned_to == user.id
    assert await _scope_cycles(s, project, user) == "A,E"


async def test_workpaper_leads_router_maps_status_and_body(session):
    from app.routers.workpaper_leads import WorkpaperLeadAssignment, WorkpaperLeadRequest, set_workpaper_leads

    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    _user, staff = await _member(s, project, assigned=["D"])
    _wi, _wp_x, inst_trim = await _wp(s, project, "H3-1", "H", with_instance=True)
    inst_trim.status = "skip"
    _wi_a, _wp_a, inst_a = await _wp(s, project, "A1", "A")
    await s.flush()
    router_db = AsyncSession(bind=await s.connection(), join_transaction_mode="create_savepoint")
    try:
        cases = ((inst_trim, 409, "trimmed", []), (inst_a, 400, "out_of_scope", ["A"]))
        for inst, status, reason, cycles in cases:
            body = WorkpaperLeadRequest(assignments=[WorkpaperLeadAssignment(procedure_id=inst.id, staff_id=staff.id)])
            with pytest.raises(HTTPException) as ei:
                await set_workpaper_leads(project.id, body, db=router_db, user=actor, _guard=None)
            assert ei.value.status_code == status
            assert ei.value.detail["error"] == "lead_delegation_rejected"
            assert ei.value.detail["reason"] == reason and ei.value.detail["cycles"] == cycles
    finally:
        await router_db.close()


# ---------------------------------------------------------------------------
# 程序行委派
# ---------------------------------------------------------------------------
async def test_row_targets_keep_only_retained_tasks(session):
    s = session
    project = await mk_project(s)
    await _trim(s, project, "H3", "H")
    wi_trim = await mk_wp_index(s, project.id, wp_code="H3-1", audit_cycle="H")
    wi_bin = await mk_wp_index(s, project.id, wp_code="D5", audit_cycle="D", is_deleted=True)
    wi_ok = await mk_wp_index(s, project.id, wp_code="D2", audit_cycle="D")
    tasks = [
        await mk_row_task(s, project.id, wi.id, wp_code=wi.wp_code, audit_cycle=wi.audit_cycle)
        for wi in (wi_trim, wi_bin, wi_ok)
    ]
    stats: dict = {}
    got = await ProcedureDelegationService(s).resolve_targets(
        project.id, {"kind": "row", "task_ids": sorted(str(t.id) for t in tasks)}, stats=stats)
    assert [t.id for t in got] == [tasks[2].id]
    assert stats["trimmed_excluded"] == 2
    assert stats["cycle_of"] == {wi_ok.id: "D"}


async def test_row_cycle_selector_follows_workpaper_cycle(session):
    s = session
    project = await mk_project(s)
    wi = await mk_wp_index(s, project.id, wp_code="I2", audit_cycle="I")
    task = await mk_row_task(s, project.id, wi.id, wp_code="I2", audit_cycle="A")  # 物化兜底的循环快照
    svc = ProcedureDelegationService(s)
    assert [t.id for t in await svc.resolve_targets(project.id, {"kind": "cycle", "cycle": "I"})] == [task.id]
    assert await svc.resolve_targets(project.id, {"kind": "cycle", "cycle": "A"}) == []


async def test_row_scope_gap_preview_reject_then_expand_with_same_preview(session):
    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    user, staff = await _member(s, project, assigned=["D"])
    wi = await mk_wp_index(s, project.id, wp_code="E1", audit_cycle="E")
    task = await mk_row_task(s, project.id, wi.id, wp_code="E1", audit_cycle="E")
    selector = {"kind": "row", "task_ids": [str(task.id)]}

    pv = await ProcedureDelegationService(s).preview(
        project.id, actor_user_id=actor.id, selector=selector, assignee_staff_id=staff.id)
    assert pv["scope_gaps"] == [{
        "role": "assignee", "staff_id": str(staff.id), "name": staff.name, "cycles": ["E"], "is_member": True,
    }]
    assert pv["summary"]["trimmed_excluded"] == 0
    preview_id = uuid.UUID(pv["preview_id"])

    with pytest.raises(HTTPException) as ei:
        async with s.begin_nested():
            await ProcedureDelegationService(s).apply(
                project.id, actor_user_id=actor.id, preview_id=preview_id, request_id="gap-1",
                selector=selector, assignee_staff_id=staff.id)
    assert ei.value.status_code == 400
    d = ei.value.detail
    assert (d["error"], d["reason"], d["cycles"]) == ("row_delegation_rejected", "out_of_scope", ["E"])
    assert d["scope_gaps"][0]["cycles"] == ["E"]
    await s.refresh(task)
    assert task.assignee_staff_id is None

    res = await ProcedureDelegationService(s).apply(
        project.id, actor_user_id=actor.id, preview_id=preview_id, request_id="gap-2",
        selector=selector, assignee_staff_id=staff.id, expand_scope=True, scope_reason="跨循环支援")
    assert res["applied"] == 1
    assert res["scope_expanded"] == [{"role": "assignee", "staff_id": str(staff.id), "cycles": ["E"]}]
    await s.refresh(task)
    assert task.assignee_staff_id == staff.id
    assert await _scope_cycles(s, project, user) == "E"
    scope_rows = (await s.execute(sa.select(sa.func.count()).select_from(WpVisibilityInvalidationOutbox).where(
        WpVisibilityInvalidationOutbox.project_id == project.id,
        WpVisibilityInvalidationOutbox.change_type == "scope"))).scalar_one()
    assert scope_rows == 1


async def test_row_non_member_assignee_rejected_even_with_expand(session):
    """没有本项目成员行的执行人无从扩权：preview 标 is_member=False，apply 带理由也 400 not_project_member。"""
    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    _user, staff = await _member(s, project, assigned=["D"], project_user=False)
    wi = await mk_wp_index(s, project.id, wp_code="E1", audit_cycle="E")
    task = await mk_row_task(s, project.id, wi.id, wp_code="E1", audit_cycle="E")
    selector = {"kind": "row", "task_ids": [str(task.id)]}
    pv = await ProcedureDelegationService(s).preview(
        project.id, actor_user_id=actor.id, selector=selector, assignee_staff_id=staff.id)
    assert pv["scope_gaps"][0]["is_member"] is False
    with pytest.raises(HTTPException) as ei:
        async with s.begin_nested():
            await ProcedureDelegationService(s).apply(
                project.id, actor_user_id=actor.id, preview_id=uuid.UUID(pv["preview_id"]), request_id="nm-1",
                selector=selector, assignee_staff_id=staff.id, expand_scope=True, scope_reason="跨循环支援")
    assert ei.value.status_code == 400 and ei.value.detail["reason"] == "not_project_member"


async def test_row_supervisor_and_admin_have_no_scope_gaps(session):
    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    _mgr, mgr_staff = await _member(s, project, role="manager")
    admin = await mk_user(s, role="admin")
    admin_staff = await mk_staff(s, user_id=admin.id)
    await mk_assignment(s, project.id, admin_staff.id, role="auditor")
    wi = await mk_wp_index(s, project.id, wp_code="E1", audit_cycle="E")
    task = await mk_row_task(s, project.id, wi.id, wp_code="E1", audit_cycle="E")
    for staff in (mgr_staff, admin_staff):
        pv = await ProcedureDelegationService(s).preview(
            project.id, actor_user_id=actor.id, selector={"kind": "row", "task_ids": [str(task.id)]},
            assignee_staff_id=staff.id)
        assert pv["scope_gaps"] == []


async def test_row_coordinator_rejects_task_under_trimmed_workpaper(session):
    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    _user, staff = await _member(s, project, assigned=["H"])
    await _trim(s, project, "H3", "H")
    wi = await mk_wp_index(s, project.id, wp_code="H3-2", audit_cycle="H")
    task = await mk_row_task(s, project.id, wi.id, wp_code="H3-2", audit_cycle="H")
    with pytest.raises(HTTPException) as ei:
        await ProcedureRowDelegationCoordinator(s).assign(
            task, project_id=project.id, new_assignee_staff_id=staff.id, actor_user_id=actor.id)
    assert ei.value.status_code == 409
    assert ei.value.detail["reason"] == "trimmed"
    assert task.workflow_status == "unassigned" and task.assignee_staff_id is None


async def test_transition_assign_checks_scope_and_records_visibility(session):
    from app.routers.procedure_row_tasks import TransitionRequest, _delegate_row_task

    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    _user, staff = await _member(s, project, assigned=["D"])
    wi = await mk_wp_index(s, project.id, wp_code="E1", audit_cycle="E")
    task = await mk_row_task(s, project.id, wi.id, wp_code="E1", audit_cycle="E")

    with pytest.raises(HTTPException) as ei:
        async with s.begin_nested():
            await _delegate_row_task(s, project.id, task, TransitionRequest(
                action="assign", request_id="tr-1", new_assignee_staff_id=staff.id), actor, "assign")
    assert ei.value.status_code == 400 and ei.value.detail["reason"] == "out_of_scope"

    res = await _delegate_row_task(s, project.id, task, TransitionRequest(
        action="assign", request_id="tr-2", new_assignee_staff_id=staff.id,
        expand_scope=True, scope_reason="跨循环支援"), actor, "assign")
    assert res["changed"] is True and task.assignee_staff_id == staff.id
    # 走协调器：记统一委派历史（原先直调状态机，不记、也不递增可见性策略版本）
    hist = (await s.execute(sa.select(sa.func.count()).select_from(WorkpaperDelegationHistory).where(
        WorkpaperDelegationHistory.task_id == task.id))).scalar_one()
    assert hist == 1

    await _trim(s, project, "E1", "E")
    other = await mk_row_task(s, project.id, wi.id, wp_code="E1", audit_cycle="E")
    with pytest.raises(HTTPException) as ei2:
        await _delegate_row_task(s, project.id, other, TransitionRequest(
            action="assign", request_id="tr-3", new_assignee_staff_id=staff.id), actor, "assign")
    assert ei2.value.status_code == 409 and ei2.value.detail["reason"] == "trimmed"


async def test_delegate_row_layer_rejects_not_applicable_and_recycled(session):
    from app.services.wp_visibility.delegation_transaction import RowDelegationRequest

    s = session
    project = await mk_project(s)
    actor = await mk_user(s)
    _user, staff = await _member(s, project, assigned=["D"])
    wi = await mk_wp_index(s, project.id, wp_code="D2", audit_cycle="D")
    na_task = await mk_row_task(s, project.id, wi.id, wp_code="D2")
    na_task.applicability_status = "not_applicable"
    wi_bin = await mk_wp_index(s, project.id, wp_code="D5", audit_cycle="D", is_deleted=True)
    bin_task = await mk_row_task(s, project.id, wi_bin.id, wp_code="D5")
    await s.flush()
    svc = DelegationTransactionService(s)
    for task, reason in ((na_task, DelegationRejectReason.trimmed), (bin_task, DelegationRejectReason.recycled)):
        with pytest.raises(DelegationError) as ei:
            await svc.delegate_row(RowDelegationRequest(
                project_id=project.id, actor_user_id=actor.id, task_id=task.id,
                target_role="assignee", staff_id=staff.id))
        assert ei.value.reason == reason and ei.value.http_status == 409
        await s.refresh(task)
        assert task.assignee_staff_id is None
