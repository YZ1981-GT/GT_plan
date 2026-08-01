"""程序行委派单一事务协调器。

状态机负责 task + ProcedureRowTaskHistory/TaskEvent；visibility transaction 只负责
统一委派历史、scope、policy epoch 与 invalidation outbox。两部分共用调用方事务，
本服务只 flush、不 commit。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureRowTask
from app.services.procedure_authorization import (
    assert_sod_distinct,
    require_staff_active_user,
)
from app.services.procedure_task_transition_service import ProcedureTaskTransitionService
from app.services.wp_visibility.delegation_transaction import DelegationTransactionService


class ProcedureRowDelegationCoordinator:
    """在一个数据库事务内闭合 row 状态与可见性副作用。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.transition = ProcedureTaskTransitionService(db)
        self.visibility = DelegationTransactionService(db)

    @staticmethod
    def _assert_owner(task: ProcedureRowTask, project_id: UUID) -> None:
        if task.project_id != project_id or task.is_deleted:
            raise HTTPException(status_code=404, detail="程序行任务不存在")

    async def _preflight(
        self,
        task: ProcedureRowTask,
        project_id: UUID,
        assignee_staff_id: UUID | None,
        reviewer_staff_id: UUID | None,
    ) -> None:
        self._assert_owner(task, project_id)
        if assignee_staff_id is not None:
            await require_staff_active_user(self.db, assignee_staff_id)
        if reviewer_staff_id is not None:
            await require_staff_active_user(self.db, reviewer_staff_id)
        await assert_sod_distinct(self.db, assignee_staff_id, reviewer_staff_id)

    async def _record(
        self,
        *,
        project_id: UUID,
        task: ProcedureRowTask,
        actor_user_id: UUID,
        request_id: str | None,
        reason: str | None,
        old_assignee: UUID | None,
        old_reviewer: UUID | None,
        result: dict,
    ) -> dict:
        if not result.get("changed"):
            return result
        visibility = await self.visibility.record_row_visibility_effects(
            project_id=project_id,
            task=task,
            actor_user_id=actor_user_id,
            old_assignee_staff_id=old_assignee,
            new_assignee_staff_id=task.assignee_staff_id,
            old_reviewer_staff_id=old_reviewer,
            new_reviewer_staff_id=task.reviewer_staff_id,
            request_id=request_id,
            reason=reason,
        )
        return {**result, "visibility_epoch": visibility.get("epoch")}

    async def assign(
        self,
        task: ProcedureRowTask,
        *,
        project_id: UUID,
        new_assignee_staff_id: UUID,
        actor_user_id: UUID,
        request_id: str | None = None,
        new_reviewer_staff_id: UUID | None = None,
        due_at: datetime | None = None,
        reason: str | None = None,
        delegation_batch_id: UUID | None = None,
    ) -> dict:
        old_assignee = task.assignee_staff_id
        old_reviewer = task.reviewer_staff_id
        effective_reviewer = (
            new_reviewer_staff_id
            if new_reviewer_staff_id is not None
            else old_reviewer
        )
        await self._preflight(
            task, project_id, new_assignee_staff_id, effective_reviewer
        )
        result = await self.transition.assign(
            task,
            new_assignee_staff_id=new_assignee_staff_id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            new_reviewer_staff_id=new_reviewer_staff_id,
            due_at=due_at,
            reason=reason,
            delegation_batch_id=delegation_batch_id,
        )
        return await self._record(
            project_id=project_id,
            task=task,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=reason,
            old_assignee=old_assignee,
            old_reviewer=old_reviewer,
            result=result,
        )

    async def reassign(
        self,
        task: ProcedureRowTask,
        *,
        project_id: UUID,
        new_assignee_staff_id: UUID,
        actor_user_id: UUID,
        reason: str,
        request_id: str | None = None,
        new_reviewer_staff_id: UUID | None = None,
        delegation_batch_id: UUID | None = None,
    ) -> dict:
        old_assignee = task.assignee_staff_id
        old_reviewer = task.reviewer_staff_id
        effective_reviewer = (
            new_reviewer_staff_id
            if new_reviewer_staff_id is not None
            else old_reviewer
        )
        await self._preflight(
            task, project_id, new_assignee_staff_id, effective_reviewer
        )
        result = await self.transition.reassign(
            task,
            new_assignee_staff_id=new_assignee_staff_id,
            actor_user_id=actor_user_id,
            reason=reason,
            request_id=request_id,
            new_reviewer_staff_id=(
                new_reviewer_staff_id
                if new_reviewer_staff_id is not None
                else old_reviewer
            ),
            delegation_batch_id=delegation_batch_id,
        )
        return await self._record(
            project_id=project_id,
            task=task,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=reason,
            old_assignee=old_assignee,
            old_reviewer=old_reviewer,
            result=result,
        )

    async def set_reviewer(
        self,
        task: ProcedureRowTask,
        *,
        project_id: UUID,
        new_reviewer_staff_id: UUID | None,
        actor_user_id: UUID,
        request_id: str | None = None,
        reason: str | None = None,
        delegation_batch_id: UUID | None = None,
    ) -> dict:
        old_assignee = task.assignee_staff_id
        old_reviewer = task.reviewer_staff_id
        await self._preflight(
            task, project_id, old_assignee, new_reviewer_staff_id
        )
        result = await self.transition.set_reviewer(
            task,
            new_reviewer_staff_id=new_reviewer_staff_id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=reason,
            delegation_batch_id=delegation_batch_id,
        )
        return await self._record(
            project_id=project_id,
            task=task,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=reason,
            old_assignee=old_assignee,
            old_reviewer=old_reviewer,
            result=result,
        )
