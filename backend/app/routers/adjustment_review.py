"""调整分录复核流转端点（spec adjustment-hall-entry-review-closure 需求 4）。

与 ``routers/adjustments.py`` 同前缀。提交复核独立成端点、门禁 ``adjustment:edit``：审计员 / 质控
能提交、仍不能审批（``/{gid}/review`` 的 ``adjustment:review`` 门禁不变）。
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, require_project_access, require_project_permission
from app.models.audit_platform_models import ReviewStatus
from app.models.core import User
from app.services import adjustment_hall_notify as notify
from app.services import adjustment_review_service as review
from app.services import adjustment_review_task_service as review_tasks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/adjustments", tags=["adjustments"])


class SubmitReviewRequest(BaseModel):
    entry_group_ids: list[UUID] = Field(min_length=1, max_length=500)
    reviewer_ids: list[UUID] | None = None
    note: str | None = Field(default=None, max_length=500)


class BatchReviewRequest(BaseModel):
    entry_group_ids: list[UUID] = Field(min_length=1, max_length=500)
    status: ReviewStatus
    reason: str | None = Field(default=None, max_length=1000)
    reasons: dict[str, str] | None = None


def _http(e: review.ReviewFlowError) -> HTTPException:
    if e.code in {"NOT_ASSIGNED_REVIEWER", "SELF_REVIEW_FORBIDDEN", "NOT_TASK_SUBMITTER", "PARTNER_APPROVAL_REQUIRED"}:
        code = 403
    elif e.code in {"NO_REVIEWER", "PARTNER_REVIEWER_REQUIRED", "REVIEW_TASK_REQUIRED", "REVIEW_TASK_STALE", "GROUP_REVISION_INCONSISTENT"}:
        code = 409
    elif e.code == "NOT_FOUND":
        code = 404
    else:
        code = 400
    return HTTPException(status_code=code, detail={"error_code": e.code, "message": str(e), "detail": e.detail})


def broadcast_review_changed(project_id: UUID, items: list[dict], new_status: str) -> None:
    """SSE：在线的大厅与底稿调整 tab 刷新状态（best-effort）。"""
    if not items:
        return
    try:
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw("adjustment:review-changed", extra={
            "project_id": str(project_id),
            "year": items[0].get("year"),
            "entry_group_id": items[0].get("entry_group_id"),
            "entry_group_ids": [it.get("entry_group_id") for it in items],
            "new_status": new_status,
        })
    except Exception:  # noqa: BLE001
        pass


async def publish_review_events(db: AsyncSession) -> None:
    """提交后投递本事务记住的耐久事件；失败留在 outbox 自动重试。"""
    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    await DurableEventOutboxService.publish_pending(db)


@router.get("/review-tasks")
async def list_adjustment_review_tasks(
    project_id: UUID,
    year: int | None = Query(None),
    mine_only: bool = Query(True),
    status: str | None = Query("pending"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """调整分录复核任务；默认只返回分配给当前用户的待办。"""
    if not mine_only:
        from app.services.project_permissions import resolve_project_context

        context = await resolve_project_context(db, current_user, project_id)
        if "adjustment:review" not in context.permissions:
            raise HTTPException(status_code=403, detail="没有查看团队调整复核任务的权限")
    rows = await review_tasks.list_tasks(
        db,
        project_id=project_id,
        year=year,
        actor_id=current_user.id if mine_only else None,
        status=status,
    )
    return [{
        "id": str(row.id),
        "entry_group_id": str(row.entry_group_id),
        "year": row.year,
        "status": row.status,
        "required_level": row.required_level,
        "revision": row.revision,
        "group_content_revision": row.group_content_revision,
        "assigned_reviewer_ids": [str(value) for value in row.assigned_reviewer_ids or []],
        "submitted_by": str(row.submitted_by),
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "submit_note": row.submit_note,
        "decided_by": str(row.decided_by) if row.decided_by else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decision_reason": row.decision_reason,
    } for row in rows]


@router.get("/reviewers")
async def list_adjustment_reviewers(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """本项目可复核调整分录的成员（提交复核时选择通知谁）。"""
    return await notify.review_candidates(db, project_id)


@router.post("/submit-review")
async def submit_adjustments_for_review(
    project_id: UUID,
    body: SubmitReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_permission("adjustment:submit")),
    _lock_check=Depends(check_consol_lock),
):
    """草稿 / 已驳回分录提交复核（批量逐笔），并创建持久化任务。"""
    try:
        result = await review.submit_for_review(
            db, project_id, group_ids=body.entry_group_ids, actor=user,
            reviewer_ids=body.reviewer_ids, note=body.note,
        )
    except review.ReviewFlowError as e:
        raise _http(e)
    await db.commit()
    broadcast_review_changed(project_id, result["succeeded"], ReviewStatus.pending_review.value)
    return result


@router.post("/{entry_group_id}/withdraw-submission")
async def withdraw_adjustment_submission(
    project_id: UUID,
    entry_group_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_permission("adjustment:submit")),
    _lock_check=Depends(check_consol_lock),
):
    """撤回提交：待复核 → 草稿，同时关闭持久化复核任务。"""
    try:
        info = await review.withdraw_submission(db, project_id, entry_group_id, actor=user)
    except review.ReviewFlowError as e:
        raise _http(e)
    await db.commit()
    broadcast_review_changed(project_id, [info], ReviewStatus.draft.value)
    return info


@router.post("/review-batch")
async def review_adjustments_batch(
    project_id: UUID,
    body: BatchReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_permission("adjustment:review")),
    _lock_check=Depends(check_consol_lock),
):
    """批量通过 / 驳回（逐笔独立），通知编制人与受影响底稿负责人。"""
    if body.status == ReviewStatus.approved:
        from app.services.project_permissions import resolve_project_context

        context = await resolve_project_context(db, user, project_id)
        if "adjustment:approve" not in context.permissions:
            raise HTTPException(status_code=403, detail="没有批准调整分录的权限")
    try:
        result = await review.review_groups(
            db, project_id, group_ids=body.entry_group_ids, status=body.status, actor=user,
            reason=body.reason, reasons=body.reasons,
        )
    except review.ReviewFlowError as e:
        raise _http(e)
    await db.commit()
    await publish_review_events(db)
    broadcast_review_changed(project_id, result["succeeded"], body.status.value)
    return result
