"""批量复核路由（通过 / 退回）

Requirements: 7.1, 7.3, 7.4, 7.5, 7.6

POST /api/projects/{project_id}/batch-review
请求体：BatchReviewRequest（wp_ids + action + comment）
逐张走 WorkingPaperService.update_review_status（F8 配置驱动状态机），
不符合的跳过并写原因回报。

RBAC：project review 级（复核人可用）。
注册到 router_registry 协作域 §100。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.working_paper_service import WorkingPaperService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["batch-review"],
)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class BatchReviewRequest(BaseModel):
    wp_ids: list[UUID]
    action: str = "approve"  # "approve" | "reject"
    comment: str = ""


class BatchReviewResult(BaseModel):
    success_count: int
    skipped_count: int
    skipped_items: list[dict[str, Any]]  # [{wp_id, reason}]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

_LEVEL_RE = re.compile(r"pending_level(\d)|level(\d)_in_progress")


def _resolve_level(review_status: str) -> int | None:
    """从 review_status 值里提取当前在哪一级（1~4），提取不到返回 None。"""
    m = _LEVEL_RE.match(review_status)
    if m:
        return int(m.group(1) or m.group(2))
    return None


@router.post("/batch-review", response_model=BatchReviewResult)
async def batch_review(
    project_id: UUID,
    body: BatchReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
) -> BatchReviewResult:
    """批量复核（通过或退回）。

    逐张走 ``WorkingPaperService.update_review_status``（F8 配置驱动状态机）：
    - approve: 从当前级的 pending/in_progress 推到 levelN_passed（状态机自动推进下一级或标终态）
    - reject:  从当前级推到 levelN_rejected（退回编制人修改）
    不符合条件的跳过并回报原因。

    Requirements: 7.1, 7.3, 7.4, 7.5, 7.6
    """
    start_time = time.time()

    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail=f"action 必须是 approve 或 reject，收到: {body.action}")

    if not body.wp_ids:
        return BatchReviewResult(success_count=0, skipped_count=0, skipped_items=[])

    svc = WorkingPaperService()
    success_count = 0
    skipped_items: list[dict[str, Any]] = []

    for wp_id in body.wp_ids:
        # 先读底稿当前 review_status，推导目标状态
        from sqlalchemy import select
        from app.models.workpaper_models import WorkingPaper
        wp_row = (await db.execute(
            select(WorkingPaper.review_status).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )).scalar_one_or_none()

        if wp_row is None:
            skipped_items.append({"wp_id": str(wp_id), "reason": "底稿不存在或已删除"})
            continue

        current_status = wp_row.value if hasattr(wp_row, "value") else str(wp_row)
        level = _resolve_level(current_status)
        if level is None:
            skipped_items.append({"wp_id": str(wp_id), "reason": f"当前状态 {current_status} 不在待复核/复核中"})
            continue

        target = f"level{level}_passed" if body.action == "approve" else f"level{level}_rejected"
        reason = body.comment if body.action == "reject" else None

        try:
            await svc.update_review_status(
                db=db, wp_id=wp_id, new_review_status=target, project_id=project_id,
                reason=reason, rejected_by_id=current_user.id if body.action == "reject" else None,
            )
            success_count += 1
        except ValueError as e:
            skipped_items.append({"wp_id": str(wp_id), "reason": str(e)})

    await db.commit()

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "[BATCH-REVIEW] project=%s user=%s action=%s success=%d skipped=%d elapsed=%.1fms",
        project_id, current_user.id, body.action, success_count, len(skipped_items), elapsed_ms,
    )

    return BatchReviewResult(
        success_count=success_count,
        skipped_count=len(skipped_items),
        skipped_items=skipped_items,
    )
