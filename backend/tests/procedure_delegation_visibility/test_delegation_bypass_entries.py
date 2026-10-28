"""旁路委派入口收口（spec procedure-trim-generation-delegation-chain 需求 4.3 / 任务 12）。

真实 PostgreSQL，每个用例在回滚事务里建数据（``session`` fixture）；路由函数直接调用，路由会话用
``create_savepoint`` 吸收路由里的 commit / rollback。审计日志与事件总线打桩（它们可能另开会话写库）。

覆盖：批量分配（只改本项目、委派人鉴权、编制人走主编委派：已裁 409 / 缺循环 400 零写 / 带理由扩权、复核人须是成员）、
增强批量分配（已裁整批回滚且不发通知、成功发通知）、复核页指派（改编制人须委派人、人员 id 落为用户 id、展示镜像）、
人员交接（人员 → 用户换算、已裁跳过、带交接理由扩权、工单与通知按用户、接收人无账号拒绝）、wp_mapping 按姓名分配 410。
"""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Notification, ProjectUser
from app.models.phase15_models import IssueTicket
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.models.wp_visibility_models import WorkpaperDelegationHistory
from tests.procedure_delegation_visibility._factories import (
    mk_assignment,
    mk_procedure_instance,
    mk_project,
    mk_project_user,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)

pytestmark = pytest.mark.asyncio


async def _member(s, project, *, role="auditor", assigned=None, scope=None):
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    a = await mk_assignment(s, project.id, staff.id, role=role)
    a.assigned_cycles = list(assigned) if assigned is not None else None
    await mk_project_user(s, project.id, user.id, role="auditor", scope_cycles=scope)
    await s.flush()
    return user, staff


async def _wp(s, project, code, cycle):
    wi = await mk_wp_index(s, project.id, wp_code=code, audit_cycle=cycle)
    wp = await mk_working_paper(s, project.id, wi.id)
    return wi, wp


async def _trim(s, project, code, cycle):
    inst = await mk_procedure_instance(s, project.id, audit_cycle=cycle, wp_code=code)
    inst.status = "skip"
    await s.flush()


async def _col(s, column, where):
    return (await s.execute(sa.select(column).where(where))).scalar()


async def _history_count(s, wp_index_id):
    return (await s.execute(sa.select(sa.func.count()).select_from(WorkpaperDelegationHistory).where(
        WorkpaperDelegationHistory.wp_index_id == wp_index_id,
        WorkpaperDelegationHistory.layer == "lead"))).scalar_one()


async def _router_db(s) -> AsyncSession:
    await s.flush()
    return AsyncSession(bind=await s.connection(), join_transaction_mode="create_savepoint")


# ---------------------------------------------------------------------------
# POST /api/projects/{pid}/working-papers/batch-assign
# ---------------------------------------------------------------------------
async def test_batch_assign_only_touches_own_project_and_records_delegation(session):
    from app.routers.wp_batch_router import BatchAssignRequest, batch_assign

    s = session
    project, other = await mk_project(s), await mk_project(s)
    admin = await mk_user(s, role="admin")
    user, staff = await _member(s, project, assigned=["D"])
    wi, wp = await _wp(s, project, "D2", "D")
    _wi_o, wp_o = await _wp(s, other, "D2", "D")
    db = await _router_db(s)
    try:
        res = await batch_assign(project.id, BatchAssignRequest(
            wp_ids=[str(wp.id), str(wp_o.id)], assigned_to=staff.id), db=db, current_user=admin)
    finally:
        await db.close()
    assert res["updated"] == 1
    assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp.id) == user.id
    assert await _col(s, WpIndex.assigned_to, WpIndex.id == wi.id) == user.id  # 展示镜像
    assert await _history_count(s, wi.id) == 1
    assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp_o.id) is None  # 别的项目不动


async def test_batch_assign_rejects_trimmed_out_of_scope_and_expands(session):
    from app.routers.wp_batch_router import BatchAssignRequest, batch_assign

    s = session
    project = await mk_project(s)
    admin = await mk_user(s, role="admin")
    user, staff = await _member(s, project, assigned=["D"])
    await _trim(s, project, "H3", "H")
    _wi_h, wp_h = await _wp(s, project, "H3-1", "H")
    _wi_a, wp_a = await _wp(s, project, "A1", "A")
    db = await _router_db(s)
    try:
        with pytest.raises(HTTPException) as ei:
            await batch_assign(project.id, BatchAssignRequest(wp_ids=[str(wp_h.id)], assigned_to=user.id),
                               db=db, current_user=admin)
        assert ei.value.status_code == 409 and ei.value.detail["reason"] == "trimmed"

        with pytest.raises(HTTPException) as ei2:
            await batch_assign(project.id, BatchAssignRequest(wp_ids=[str(wp_a.id)], assigned_to=user.id),
                               db=db, current_user=admin)
        d = ei2.value.detail
        assert ei2.value.status_code == 400
        assert (d["error"], d["reason"], d["cycles"]) == ("lead_delegation_rejected", "out_of_scope", ["A"])
        assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp_a.id) is None  # 零写

        res = await batch_assign(project.id, BatchAssignRequest(
            wp_ids=[str(wp_a.id)], assigned_to=user.id, expand_scope=True, scope_reason="跨循环支援"),
            db=db, current_user=admin)
    finally:
        await db.close()
    assert res["updated"] == 1
    assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp_a.id) == user.id
    assert await _col(s, ProjectUser.scope_cycles, sa.and_(
        ProjectUser.project_id == project.id, ProjectUser.user_id == user.id)) == "A"


async def test_batch_assign_reviewer_must_be_member_and_auditor_forbidden(session):
    from app.routers.wp_batch_router import BatchAssignRequest, batch_assign

    s = session
    project = await mk_project(s)
    admin = await mk_user(s, role="admin")
    auditor_user, _ = await _member(s, project, assigned=["D"])
    outsider = await mk_user(s)
    _wi, wp = await _wp(s, project, "D2", "D")
    db = await _router_db(s)
    try:
        with pytest.raises(HTTPException) as ei:
            await batch_assign(project.id, BatchAssignRequest(wp_ids=[str(wp.id)], reviewer=outsider.id),
                               db=db, current_user=admin)
        assert ei.value.status_code == 400 and ei.value.detail["error"] == "reviewer_not_member"

        res = await batch_assign(project.id, BatchAssignRequest(wp_ids=[str(wp.id)], reviewer=auditor_user.id),
                                 db=db, current_user=admin)
        assert res["updated"] == 1

        with pytest.raises(HTTPException) as ei2:  # 审计员不是项目委派人
            await batch_assign(project.id, BatchAssignRequest(wp_ids=[str(wp.id)], assigned_to=auditor_user.id),
                               db=db, current_user=auditor_user)
        assert ei2.value.status_code == 403
    finally:
        await db.close()
    assert await _col(s, WorkingPaper.reviewer, WorkingPaper.id == wp.id) == auditor_user.id
    assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp.id) is None


# ---------------------------------------------------------------------------
# POST /api/workpapers/batch-assign-enhanced
# ---------------------------------------------------------------------------
@patch("app.services.event_bus.event_bus.publish", new_callable=AsyncMock)
@patch("app.services.audit_logger_enhanced.audit_logger.log_action", new_callable=AsyncMock)
async def test_batch_assign_enhanced_trimmed_rolls_back_whole_batch(_log, _pub, session):
    from app.routers.batch_assign_enhanced import BatchAssignEnhancedRequest, batch_assign_enhanced

    s = session
    project = await mk_project(s)
    manager, _ = await _member(s, project, role="manager")
    user, _staff = await _member(s, project, assigned=["D", "H"])
    await _trim(s, project, "H3", "H")
    _wi_d, wp_d = await _wp(s, project, "D2", "D")
    _wi_h, wp_h = await _wp(s, project, "H3-1", "H")
    db = await _router_db(s)
    try:
        with pytest.raises(HTTPException) as ei:
            await batch_assign_enhanced(BatchAssignEnhancedRequest(
                wp_ids=[wp_d.id, wp_h.id], strategy="manual", candidates=[user.id]), db=db, current_user=manager)
        assert ei.value.status_code == 409 and ei.value.detail["reason"] == "trimmed"
        assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp_d.id) is None  # 同批另一张也回滚
        assert (await s.execute(sa.select(sa.func.count()).select_from(Notification).where(
            Notification.recipient_id == user.id))).scalar_one() == 0
        _pub.assert_not_awaited()

        res = await batch_assign_enhanced(BatchAssignEnhancedRequest(
            wp_ids=[wp_d.id], strategy="manual", candidates=[user.id]), db=db, current_user=manager)
    finally:
        await db.close()
    assert res.updated == 1 and res.notifications_sent == 1
    assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp_d.id) == user.id


@patch("app.services.audit_logger_enhanced.audit_logger.log_action", new_callable=AsyncMock)
async def test_batch_assign_enhanced_auditor_forbidden(_log, session):
    from app.routers.batch_assign_enhanced import BatchAssignEnhancedRequest, batch_assign_enhanced

    s = session
    project = await mk_project(s)
    auditor_user, _ = await _member(s, project, assigned=["D"])
    _wi, wp = await _wp(s, project, "D2", "D")
    db = await _router_db(s)
    try:
        with pytest.raises(HTTPException) as ei:
            await batch_assign_enhanced(BatchAssignEnhancedRequest(
                wp_ids=[wp.id], strategy="manual", candidates=[auditor_user.id]), db=db, current_user=auditor_user)
    finally:
        await db.close()
    assert ei.value.status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/projects/{pid}/working-papers/{wp_id}/assign
# ---------------------------------------------------------------------------
async def test_review_assign_requires_delegator_and_stores_user_id(session):
    from app.routers.wp_review_router import assign_workpaper
    from app.schemas.workpaper_requests import AssignRequest

    s = session
    project = await mk_project(s)
    manager, _ = await _member(s, project, role="manager")
    auditor_user, auditor_staff = await _member(s, project, assigned=["D"])
    reviewer_user, _ = await _member(s, project, assigned=["D"])
    await _trim(s, project, "H3", "H")
    wi, wp = await _wp(s, project, "D2", "D")
    _wi_h, wp_h = await _wp(s, project, "H3-1", "H")
    db = await _router_db(s)
    try:
        with pytest.raises(HTTPException) as ei:  # 审计员改编制人 ⇒ 不是委派人
            await assign_workpaper(project.id, wp.id, AssignRequest(assigned_to=auditor_staff.id),
                                   db=db, current_user=auditor_user, _lock_check=None)
        assert ei.value.status_code == 403

        # 只改复核人不要求委派人
        r1 = await assign_workpaper(project.id, wp.id, AssignRequest(reviewer=reviewer_user.id),
                                    db=db, current_user=auditor_user, _lock_check=None)
        assert r1["reviewer"] == str(reviewer_user.id)

        # 传人员 id ⇒ 落为其用户 id，展示镜像与委派历史同步
        r2 = await assign_workpaper(project.id, wp.id, AssignRequest(assigned_to=auditor_staff.id),
                                    db=db, current_user=manager, _lock_check=None)
        assert r2["assigned_to"] == str(auditor_user.id)

        with pytest.raises(HTTPException) as ei2:
            await assign_workpaper(project.id, wp_h.id, AssignRequest(assigned_to=auditor_user.id),
                                   db=db, current_user=manager, _lock_check=None)
        assert ei2.value.status_code == 409 and ei2.value.detail["reason"] == "trimmed"
    finally:
        await db.close()
    assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp.id) == auditor_user.id
    assert await _col(s, WpIndex.assigned_to, WpIndex.id == wi.id) == auditor_user.id
    assert await _history_count(s, wi.id) == 1
    assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp_h.id) is None


# ---------------------------------------------------------------------------
# 人员交接
# ---------------------------------------------------------------------------
@patch("app.services.handover_service.audit_logger.log_action", new_callable=AsyncMock)
async def test_handover_converts_staff_to_user_and_skips_trimmed(_log, session):
    from app.services.handover_service import HandoverService

    s = session
    project = await mk_project(s)
    admin = await mk_user(s, role="admin")
    from_user, from_staff = await _member(s, project, assigned=["E"])
    to_user = await mk_user(s)
    to_staff = await mk_staff(s, user_id=to_user.id)
    await mk_project_user(s, project.id, to_user.id, role="auditor")
    await _trim(s, project, "H3", "H")
    wi_d, wp_d = await _wp(s, project, "D2", "D")
    _wi_h, wp_h = await _wp(s, project, "H3-1", "H")
    _wi_e, wp_e = await _wp(s, project, "E1", "E")
    wp_d.assigned_to = from_user.id
    wp_h.assigned_to = from_user.id
    wp_e.reviewer = from_user.id
    s.add(IssueTicket(project_id=project.id, source="L2", severity="major", category="data_mismatch",
                      title="待处理", owner_id=from_user.id, status="open", trace_id=uuid.uuid4().hex))
    await s.flush()

    preview = await HandoverService(s).get_handover_preview(from_staff.id, "by_project", [project.id])
    assert preview == {"workpapers": 3, "issues": 1, "assignments": 1}

    res = await HandoverService(s).execute(
        from_staff_id=from_staff.id, to_staff_id=to_staff.id, scope="by_project", project_ids=[project.id],
        reason_code="rotation", reason_detail="岗位轮换", effective_date=date.today(), executed_by=admin.id,
    )
    assert res["workpapers_moved"] == 2  # D2 编制人 + E1 复核人；H3-1 已裁跳过
    assert res["issues_moved"] == 1 and res["assignments_moved"] == 1
    assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp_d.id) == to_user.id
    assert await _col(s, WorkingPaper.assigned_to, WorkingPaper.id == wp_h.id) == from_user.id
    assert await _col(s, WorkingPaper.reviewer, WorkingPaper.id == wp_e.id) == to_user.id
    assert await _col(s, IssueTicket.owner_id, IssueTicket.project_id == project.id) == to_user.id
    # D 不在接收人继承的团队分配（E）里：交接即授权，带交接理由扩大可见范围并记入委派历史
    assert await _col(s, ProjectUser.scope_cycles, sa.and_(
        ProjectUser.project_id == project.id, ProjectUser.user_id == to_user.id)) == "D"
    hist = (await s.execute(sa.select(WorkpaperDelegationHistory.reason).where(
        WorkpaperDelegationHistory.wp_index_id == wi_d.id))).scalars().all()
    assert len(hist) == 1 and "人员交接" in hist[0]
    assert (await s.execute(sa.select(sa.func.count()).select_from(Notification).where(
        Notification.recipient_id == to_user.id,
        Notification.message_type == "handover_received"))).scalar_one() == 1


@patch("app.services.handover_service.audit_logger.log_action", new_callable=AsyncMock)
async def test_handover_rejects_receiver_without_user_account(_log, session):
    from app.services.handover_service import HandoverService

    s = session
    project = await mk_project(s)
    admin = await mk_user(s, role="admin")
    from_user, from_staff = await _member(s, project, assigned=["D"])
    to_staff = await mk_staff(s, user_id=None)
    _wi, wp = await _wp(s, project, "D2", "D")
    wp.reviewer = from_user.id
    await s.flush()
    with pytest.raises(ValueError, match="没有关联可登录的用户账号"):
        await HandoverService(s).execute(
            from_staff_id=from_staff.id, to_staff_id=to_staff.id, scope="by_project", project_ids=[project.id],
            reason_code="rotation", reason_detail=None, effective_date=date.today(), executed_by=admin.id,
        )


# ---------------------------------------------------------------------------
# POST /api/projects/{pid}/wp-mapping/assign/{wp_code}
# ---------------------------------------------------------------------------
async def test_wp_mapping_assign_by_name_is_gone():
    from app.routers.wp_mapping import assign_workpaper_gone

    with pytest.raises(HTTPException) as ei:
        await assign_workpaper_gone(uuid.uuid4(), "D2")
    assert ei.value.status_code == 410
    assert ei.value.detail["replacement"] == "PUT /api/projects/{pid}/workpaper-leads"
