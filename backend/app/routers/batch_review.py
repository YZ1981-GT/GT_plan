"""批量复核通过路由

Requirements: 7.1, 7.3, 7.4, 7.5, 7.6

POST /api/projects/{project_id}/batch-review-pass
请求体：BatchReviewRequest（wp_ids + comment）
RBAC：仅 manager/partner/admin 角色可调用。
注册到 router_registry 协作域 §100。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.workpaper_models import (
    ReviewRecord,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WorkingPaper,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/batch-review-pass",
    tags=["batch-review"],
)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class BatchReviewRequest(BaseModel):
    wp_ids: list[UUID]
    comment: str = "已审阅，无异议"


class BatchReviewResult(BaseModel):
    success_count: int
    skipped_count: int
    skipped_items: list[dict[str, Any]]  # [{wp_id, reason}]


# ---------------------------------------------------------------------------
# RBAC: only manager/partner/admin
# ---------------------------------------------------------------------------

ALLOWED_ROLES = {"manager", "partner", "admin"}

# Statuses that allow review pass
REVIEWABLE_STATUSES = {
    WpFileStatus.under_review,
    WpFileStatus.edit_complete,
}

REVIEWABLE_REVIEW_STATUSES = {
    WpReviewStatus.pending_level1,
    WpReviewStatus.level1_in_progress,
    WpReviewStatus.pending_level2,
    WpReviewStatus.level2_in_progress,
    WpReviewStatus.pending_level3,
    WpReviewStatus.level3_in_progress,
    WpReviewStatus.pending_level4,
    WpReviewStatus.level4_in_progress,
}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", response_model=BatchReviewResult)
async def batch_review_pass(
    project_id: UUID,
    body: BatchReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> BatchReviewResult:
    """批量复核通过。

    Requirements: 7.1, 7.3, 7.4, 7.5, 7.6

    RBAC: 仅 manager/partner/admin 角色可调用。
    单事务中遍历所有选中底稿：
    - 状态允许通过的 → 更新为 review_passed
    - 状态不允许通过的 → 跳过并记录原因
    返回 BatchReviewResult（success_count + skipped_count + skipped_items）。
    操作结果写入 audit_log。
    """
    start_time = time.time()

    # RBAC check
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="仅 manager/partner/admin 角色可执行批量复核通过",
        )

    if not body.wp_ids:
        return BatchReviewResult(success_count=0, skipped_count=0, skipped_items=[])

    # Execute batch review in single transaction
    result = await _execute_batch_review(
        db=db,
        project_id=project_id,
        wp_ids=body.wp_ids,
        comment=body.comment,
        reviewer_id=current_user.id,
    )

    await db.commit()

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "[BATCH-REVIEW] project=%s user=%s success=%d skipped=%d elapsed=%.1fms",
        project_id,
        current_user.id,
        result.success_count,
        result.skipped_count,
        elapsed_ms,
    )

    return result


# ---------------------------------------------------------------------------
# Transaction Logic (Task 9.2)
# ---------------------------------------------------------------------------


async def _execute_batch_review(
    db: AsyncSession,
    project_id: UUID,
    wp_ids: list[UUID],
    comment: str,
    reviewer_id: UUID,
) -> BatchReviewResult:
    """单事务中遍历所有选中底稿，执行批量复核通过。

    Requirements: 7.4, 7.5, 7.6

    - 状态允许通过的 → 更新 status=review_passed, review_status=level1_passed
    - 状态不允许通过的 → 跳过并记录原因
    - 操作结果写入 audit_log
    """
    # Load all target workpapers
    stmt = (
        select(WorkingPaper)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.id.in_(wp_ids),
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
    )
    result = await db.execute(stmt)
    workpapers = {wp.id: wp for wp in result.scalars().all()}

    success_count = 0
    skipped_items: list[dict[str, Any]] = []

    for wp_id in wp_ids:
        wp = workpapers.get(wp_id)

        if wp is None:
            skipped_items.append({
                "wp_id": str(wp_id),
                "reason": "底稿不存在或已删除",
            })
            continue

        # Check if status allows review pass
        skip_reason = _check_reviewable(wp)
        if skip_reason:
            skipped_items.append({
                "wp_id": str(wp_id),
                "reason": skip_reason,
            })
            continue

        # Update workpaper status to review_passed
        wp.status = WpFileStatus.review_passed
        wp.review_status = WpReviewStatus.level1_passed
        wp.updated_at = datetime.now(timezone.utc)

        # Create review record
        review_record = ReviewRecord(
            working_paper_id=wp_id,
            comment_text=comment,
            commenter_id=reviewer_id,
            status="resolved",
        )
        db.add(review_record)

        success_count += 1

    # Audit log
    logger.info(
        "[BATCH-REVIEW-AUDIT] reviewer=%s project=%s total=%d success=%d skipped=%d details=%s",
        reviewer_id,
        project_id,
        len(wp_ids),
        success_count,
        len(skipped_items),
        skipped_items[:10],  # Limit log size
    )

    return BatchReviewResult(
        success_count=success_count,
        skipped_count=len(skipped_items),
        skipped_items=skipped_items,
    )


def _check_reviewable(wp: WorkingPaper) -> str | None:
    """检查底稿是否允许复核通过。返回 None 表示可以通过，否则返回跳过原因。"""
    # Already passed or archived
    if wp.status in (WpFileStatus.review_passed, WpFileStatus.archived):
        return f"底稿已处于 {wp.status.value} 状态，无需重复通过"

    # Must be in a reviewable state (under_review or edit_complete)
    if wp.status not in REVIEWABLE_STATUSES:
        return f"底稿当前状态为 {wp.status.value}，不允许复核通过（需先提交复核）"

    return None
