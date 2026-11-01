"""调整分录持久化复核任务。

指定复核人是授权与个人待办依据，不再只是一次通知名单。所有函数只 flush，
事务由调整复核路由统一提交。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adjustment_review_models import AdjustmentReviewTask
from app.models.audit_platform_models import Adjustment


class AdjustmentReviewTaskError(ValueError):
    """可向 API 映射的复核任务错误。"""

    def __init__(self, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


def group_content_revision(rows: list[Adjustment]) -> int:
    """返回组修订号；活跃行不一致视为数据损坏并 fail closed。"""
    revisions = {int(row.content_revision or 1) for row in rows}
    if len(revisions) != 1:
        raise AdjustmentReviewTaskError(
            "GROUP_REVISION_INCONSISTENT",
            "分录组内容版本不一致，请联系管理员修复后再复核",
            {"revisions": sorted(revisions)},
        )
    return next(iter(revisions))


async def pending_task(
    db: AsyncSession,
    project_id: UUID,
    entry_group_id: UUID,
    *,
    for_update: bool = False,
) -> AdjustmentReviewTask | None:
    stmt = sa.select(AdjustmentReviewTask).where(
        AdjustmentReviewTask.project_id == project_id,
        AdjustmentReviewTask.entry_group_id == entry_group_id,
        AdjustmentReviewTask.status == "pending",
        AdjustmentReviewTask.is_deleted == sa.false(),
    )
    if for_update and db.get_bind() is not None and db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalars().first()


async def create_task(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    rows: list[Adjustment],
    reviewer_ids: list[str],
    submitted_by: UUID,
    note: str | None,
    required_level: str = "manager",
) -> AdjustmentReviewTask:
    """为一笔分录创建当前轮复核任务。相同版本的重复提交幂等返回。"""
    if not rows:
        raise AdjustmentReviewTaskError("GROUP_NOT_FOUND", "分录不存在或已删除")
    group_id = rows[0].entry_group_id
    revision = group_content_revision(rows)
    existing = await pending_task(db, project_id, group_id, for_update=True)
    normalized_reviewers = sorted({str(value) for value in reviewer_ids if str(value)})
    if not normalized_reviewers:
        raise AdjustmentReviewTaskError(
            "NO_REVIEWER",
            "本项目没有可接收任务的复核人，请先在项目团队中委派项目经理或合伙人",
        )
    if existing is not None:
        if (
            existing.group_content_revision == revision
            and sorted(str(value) for value in (existing.assigned_reviewer_ids or [])) == normalized_reviewers
        ):
            return existing
        existing.status = "stale"
        existing.decision_reason = "分录内容或复核人已变化，旧任务作废"
        existing.decided_at = datetime.now(timezone.utc)
        existing.revision += 1

    task = AdjustmentReviewTask(
        project_id=project_id,
        year=year,
        entry_group_id=group_id,
        group_content_revision=revision,
        assigned_reviewer_ids=normalized_reviewers,
        submitted_by=submitted_by,
        submit_note=(note or "").strip() or None,
        required_level=required_level,
    )
    db.add(task)
    await db.flush()
    return task


async def require_decidable_task(
    db: AsyncSession,
    *,
    project_id: UUID,
    rows: list[Adjustment],
    actor: Any,
) -> AdjustmentReviewTask:
    """锁定并验证当前任务、分录版本、指派关系和职责分离。"""
    if not rows:
        raise AdjustmentReviewTaskError("GROUP_NOT_FOUND", "分录不存在或已删除")
    group_id = rows[0].entry_group_id
    task = await pending_task(db, project_id, group_id, for_update=True)
    if task is None:
        raise AdjustmentReviewTaskError(
            "REVIEW_TASK_REQUIRED",
            "该分录没有有效复核任务，请先提交复核",
        )
    current_revision = group_content_revision(rows)
    if task.group_content_revision != current_revision:
        task.status = "stale"
        task.decision_reason = "分录内容在提交复核后发生变化"
        task.decided_at = datetime.now(timezone.utc)
        task.revision += 1
        await db.flush()
        raise AdjustmentReviewTaskError(
            "REVIEW_TASK_STALE",
            "分录内容在提交复核后已变化，请重新提交复核",
            {"task_revision": task.group_content_revision, "current_revision": current_revision},
        )
    actor_id = str(actor.id)
    assigned = {str(value) for value in (task.assigned_reviewer_ids or [])}
    if actor_id not in assigned and str(getattr(actor, "role", "")) != "UserRole.admin" and getattr(getattr(actor, "role", None), "value", None) != "admin":
        raise AdjustmentReviewTaskError(
            "NOT_ASSIGNED_REVIEWER",
            "该复核任务未分配给当前用户",
        )
    if task.required_level == "partner":
        from app.services.project_permissions import resolve_project_context
        context = await resolve_project_context(db, actor, project_id)
        if context.system_role not in {"admin", "partner"} and context.project_role not in {"partner", "signing_partner"}:
            raise AdjustmentReviewTaskError(
                "PARTNER_APPROVAL_REQUIRED",
                "该分录达到执行重要性或命中高风险事项，必须由项目合伙人终审",
            )
    creators = {str(row.created_by) for row in rows if row.created_by}
    if actor_id in creators:
        raise AdjustmentReviewTaskError(
            "SELF_REVIEW_FORBIDDEN",
            "编制人不能复核自己的调整分录，请转交其他经理或合伙人",
        )
    return task


async def decide_task(
    db: AsyncSession,
    task: AdjustmentReviewTask,
    *,
    actor_id: UUID,
    status: str,
    reason: str | None = None,
) -> None:
    if status not in {"approved", "rejected"}:
        raise AdjustmentReviewTaskError("INVALID_TASK_STATUS", "复核任务只能批准或驳回")
    task.status = status
    task.decided_by = actor_id
    task.decided_at = datetime.now(timezone.utc)
    task.decision_reason = (reason or "").strip() or None
    task.revision += 1
    await db.flush()


async def withdraw_task(
    db: AsyncSession,
    *,
    project_id: UUID,
    entry_group_id: UUID,
    actor_id: UUID,
) -> None:
    task = await pending_task(db, project_id, entry_group_id, for_update=True)
    if task is None:
        raise AdjustmentReviewTaskError("REVIEW_TASK_REQUIRED", "没有可撤回的复核任务")
    if task.submitted_by != actor_id:
        raise AdjustmentReviewTaskError("NOT_TASK_SUBMITTER", "只有提交人可以撤回该复核任务")
    task.status = "withdrawn"
    task.decided_by = actor_id
    task.decided_at = datetime.now(timezone.utc)
    task.decision_reason = "提交人撤回"
    task.revision += 1
    await db.flush()


async def list_tasks(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int | None = None,
    actor_id: UUID | None = None,
    status: str | None = "pending",
) -> list[AdjustmentReviewTask]:
    stmt = sa.select(AdjustmentReviewTask).where(
        AdjustmentReviewTask.project_id == project_id,
        AdjustmentReviewTask.is_deleted == sa.false(),
    )
    if year is not None:
        stmt = stmt.where(AdjustmentReviewTask.year == year)
    if status:
        stmt = stmt.where(AdjustmentReviewTask.status == status)
    if actor_id is not None:
        # JSONB containment is PG-only; portable fallback filters after the project-scoped query.
        rows = list((await db.execute(stmt.order_by(AdjustmentReviewTask.submitted_at))).scalars().all())
        return [row for row in rows if str(actor_id) in {str(value) for value in row.assigned_reviewer_ids or []}]
    return list((await db.execute(stmt.order_by(AdjustmentReviewTask.submitted_at))).scalars().all())
