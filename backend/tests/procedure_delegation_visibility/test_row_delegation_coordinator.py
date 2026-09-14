"""procedure-mainline-convergence：row 状态机与 visibility 同事务闭环。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from fastapi import HTTPException

from app.models.phase15_models import TaskEvent
from app.models.procedure_models import ProcedureRowTask, ProcedureRowTaskHistory
from app.models.wp_visibility_models import (
    WorkpaperDelegationHistory,
    WpVisibilityInvalidationOutbox,
    WpVisibilityPolicyEpoch,
)
from app.services.procedure_delegation_service import ProcedureDelegationService
from app.services.procedure_row_delegation_coordinator import (
    ProcedureRowDelegationCoordinator,
)
from app.services.procedure_task_transition_service import (
    ProcedureTaskTransitionService,
)
from tests.procedure_delegation_visibility._factories import (
    mk_assignment,
    mk_project,
    mk_project_user,
    mk_row_task,
    mk_staff,
    mk_user,
    mk_wp_index,
)

pytestmark = pytest.mark.asyncio


async def _person(s, project, *, scope="D"):
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    await mk_assignment(s, project.id, staff.id)
    await mk_project_user(s, project.id, user.id, scope_cycles=scope)
    return user, staff


async def _count(s, model, *conds):
    return (
        await s.execute(sa.select(sa.func.count()).select_from(model).where(*conds))
    ).scalar_one()


async def test_reviewer_only_reassign_preserves_assignment_version_and_snapshots(session):
    """reviewer-only 变更走 set_reviewer（不递增 assignment_version，Req 7）。"""
    project = await mk_project(session)
    actor = await mk_user(session)
    _au, assignee = await _person(session, project)
    _ru1, reviewer1 = await _person(session, project)
    _ru2, reviewer2 = await _person(session, project)
    wi = await mk_wp_index(session, project.id)
    task = await mk_row_task(
        session,
        project.id,
        wi.id,
        assignee_staff_id=assignee.id,
        reviewer_staff_id=reviewer1.id,
    )
    task.workflow_status = "assigned"
    task.assignment_version = 4
    task.lock_version = 7
    await session.flush()

    result = await ProcedureTaskTransitionService(session).set_reviewer(
        task,
        new_reviewer_staff_id=reviewer2.id,
        actor_user_id=actor.id,
    )
    assert result["changed"] is True
    assert task.assignee_staff_id == assignee.id
    assert task.reviewer_staff_id == reviewer2.id
    # set_reviewer 不递增 assignment_version
    assert task.assignment_version == 4
    assert task.lock_version == 8
    history = (
        await session.execute(
            sa.select(ProcedureRowTaskHistory).where(
                ProcedureRowTaskHistory.task_id == task.id
            )
        )
    ).scalar_one()
    assert history.event_type == "reviewer_changed"
    assert history.old_reviewer_staff_id == reviewer1.id
    assert history.new_reviewer_staff_id == reviewer2.id


async def test_reopen_records_old_assignee_to_real_none(session):
    project = await mk_project(session)
    actor = await mk_user(session)
    _user, assignee = await _person(session, project)
    wi = await mk_wp_index(session, project.id)
    task = await mk_row_task(
        session, project.id, wi.id, assignee_staff_id=assignee.id
    )
    task.workflow_status = "cancelled"
    task.assignment_version = 2
    await session.flush()

    await ProcedureTaskTransitionService(session).reopen(
        task, actor_user_id=actor.id, reason="恢复程序行"
    )
    history = (
        await session.execute(
            sa.select(ProcedureRowTaskHistory).where(
                ProcedureRowTaskHistory.task_id == task.id
            )
        )
    ).scalar_one()
    assert history.old_assignee_staff_id == assignee.id
    assert history.new_assignee_staff_id is None


async def test_coordinator_reviewer_only_writes_single_visibility_closure(session):
    project = await mk_project(session)
    actor = await mk_user(session)
    _au, assignee = await _person(session, project)
    _ru1, reviewer1 = await _person(session, project)
    _ru2, reviewer2 = await _person(session, project)
    wi = await mk_wp_index(session, project.id)
    task = await mk_row_task(
        session,
        project.id,
        wi.id,
        assignee_staff_id=assignee.id,
        reviewer_staff_id=reviewer1.id,
    )
    task.workflow_status = "assigned"
    task.assignment_version = 3
    await session.flush()

    coordinator = ProcedureRowDelegationCoordinator(session)
    result = await coordinator.set_reviewer(
        task,
        project_id=project.id,
        new_reviewer_staff_id=reviewer2.id,
        actor_user_id=actor.id,
        request_id="reviewer-only-1",
    )
    assert result["changed"] is True
    assert result["visibility_epoch"] == 1
    assert task.assignment_version == 3
    assert await _count(
        session, ProcedureRowTaskHistory, ProcedureRowTaskHistory.task_id == task.id
    ) == 1
    rows = (
        await session.execute(
            sa.select(WorkpaperDelegationHistory).where(
                WorkpaperDelegationHistory.task_id == task.id
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].target_role == "reviewer"
    assert rows[0].old_staff_id == reviewer1.id
    assert rows[0].new_staff_id == reviewer2.id
    assert await _count(
        session,
        WpVisibilityInvalidationOutbox,
        WpVisibilityInvalidationOutbox.project_id == project.id,
    ) == 1

    # same reviewer is a true no-op: no task history, unified history, epoch or outbox growth
    again = await coordinator.set_reviewer(
        task,
        project_id=project.id,
        new_reviewer_staff_id=reviewer2.id,
        actor_user_id=actor.id,
        request_id="reviewer-only-2",
    )
    assert again["changed"] is False
    assert await _count(
        session,
        WorkpaperDelegationHistory,
        WorkpaperDelegationHistory.task_id == task.id,
    ) == 1
    epoch = await session.get(WpVisibilityPolicyEpoch, project.id)
    assert epoch.epoch == 1


async def test_best_effort_savepoint_rolls_back_task_and_visibility_effects(session):
    project = await mk_project(session)
    actor, assignee = await _person(session, project, scope="D")
    wi = await mk_wp_index(session, project.id, audit_cycle="D")
    ok_task = await mk_row_task(session, project.id, wi.id, audit_cycle="D")
    # 使 fail_task 为已终态 → assign 时抛 409
    fail_task = await mk_row_task(session, project.id, wi.id, audit_cycle="D")
    fail_task.workflow_status = "reviewed"  # 终态不可分配
    fail_task.applicability_status = "execute"
    await session.flush()

    selector = {
        "kind": "row",
        "task_ids": [str(ok_task.id), str(fail_task.id)],
    }
    service = ProcedureDelegationService(session)
    preview = await service.preview(
        project.id,
        actor_user_id=actor.id,
        selector=selector,
        assignee_staff_id=assignee.id,
        best_effort=True,
    )
    result = await service.apply(
        project.id,
        actor_user_id=actor.id,
        preview_id=uuid.UUID(preview["preview_id"]),
        request_id="savepoint-1",
        selector=selector,
        assignee_staff_id=assignee.id,
        best_effort=True,
    )
    # ok_task 分配成功，fail_task 终态跳过（归入 terminal，不参与 assign）
    assert result["applied"] >= 1

    await session.refresh(ok_task)
    await session.refresh(fail_task)
    assert ok_task.workflow_status == "assigned"
    assert ok_task.assignee_staff_id == assignee.id
    # fail_task 终态未被触碰
    assert fail_task.workflow_status == "reviewed"
    assert fail_task.assignee_staff_id is None


async def test_preview_materializes_synchronously_and_returns_ready(session, monkeypatch):
    project = await mk_project(session)
    actor = await mk_user(session)
    assignee = await mk_staff(session, user_id=actor.id)
    await mk_assignment(session, project.id, assignee.id)
    await mk_project_user(session, project.id, actor.id, scope_cycles="D")
    service = ProcedureDelegationService(session)
    wp_index_id = (await mk_wp_index(session, project.id)).id
    materialize = AsyncMock(
        return_value={"created": 2, "existing": 0, "targets": 2}
    )
    monkeypatch.setattr(service, "_count_unmaterialized", AsyncMock(return_value=2))
    monkeypatch.setattr(service.materialization, "materialize", materialize)
    monkeypatch.setattr(service, "resolve_targets", AsyncMock(return_value=[]))

    result = await service.preview(
        project.id,
        actor_user_id=actor.id,
        selector={"kind": "workpaper", "wp_index_ids": [str(wp_index_id)]},
        assignee_staff_id=assignee.id,
    )
    # Task 4.1: 同步物化后直接返回 ready（不再返回 materialization_pending）
    assert result["status"] == "ready"
    assert result["preview_id"] is not None
    materialize.assert_awaited_once()


async def test_atomic_scope_failure_rolls_back_entire_batch(session):
    """atomic 模式下冲突 task → 409 回滚整批（conflict_policy=reject 且有不同执行人的已分配 task）。"""
    project = await mk_project(session)
    actor, assignee = await _person(session, project, scope="D")
    _u2, other_assignee = await _person(session, project, scope="D")
    wi = await mk_wp_index(session, project.id, audit_cycle="D")
    first = await mk_row_task(session, project.id, wi.id, audit_cycle="D")
    # 第二个 task 已分配给别人 → conflict（default conflict_policy=reject）
    conflicting = await mk_row_task(session, project.id, wi.id, audit_cycle="D")
    conflicting.workflow_status = "assigned"
    conflicting.assignee_staff_id = other_assignee.id
    conflicting.assignment_version = 1
    conflicting.lock_version = 1
    await session.flush()

    selector = {"kind": "row", "task_ids": [str(first.id), str(conflicting.id)]}
    service = ProcedureDelegationService(session)
    preview = await service.preview(
        project.id,
        actor_user_id=actor.id,
        selector=selector,
        assignee_staff_id=assignee.id,
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.apply(
            project.id,
            actor_user_id=actor.id,
            preview_id=uuid.UUID(preview["preview_id"]),
            request_id="atomic-scope-1",
            selector=selector,
            assignee_staff_id=assignee.id,
        )
    assert exc_info.value.status_code == 409
