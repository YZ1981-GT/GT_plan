"""待办聚合服务

Requirements: 1.1, 1.2, 1.3

聚合查询 working_paper + wp_index + review_records + issue_tickets，
按紧急度降序排序返回 TodoItem 列表。

紧急度计算逻辑：
1. critical（红）：prefill_stale = true
2. high（橙）：SLA 剩余 ≤ 24h（IssueTicket.due_at）
3. medium（黄）：有未解决复核意见
4. normal（灰）：普通未完成
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase15_models import IssueTicket
from app.models.workpaper_models import (
    ReviewCommentStatus,
    ReviewRecord,
    WpIndex,
    WorkingPaper,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

URGENCY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "normal": 3,
}


class TodoItem(BaseModel):
    wp_id: UUID
    wp_code: str
    wp_name: str
    cycle: str
    urgency: Literal["critical", "high", "medium", "normal"]
    urgency_reason: str
    updated_at: datetime


class MyTodoResponse(BaseModel):
    items: list[TodoItem]
    total: int


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


async def get_my_todo(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
) -> MyTodoResponse:
    """聚合当前用户在指定项目中的待办底稿列表。

    性能目标：≤ 500ms（50 底稿规模）。
    """
    # Step 1: 查询用户负责的未完成底稿（排除 archived）
    stmt = (
        select(
            WorkingPaper.id,
            WorkingPaper.prefill_stale,
            WorkingPaper.updated_at,
            WpIndex.wp_code,
            WpIndex.wp_name,
            WpIndex.audit_cycle,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.assigned_to == user_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
            WorkingPaper.status != "archived",
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return MyTodoResponse(items=[], total=0)

    wp_ids = [row[0] for row in rows]

    # Step 2: 查询有 SLA ≤ 24h 的问题单关联的底稿
    now = datetime.now(timezone.utc)
    t_24h = now + timedelta(hours=24)

    sla_stmt = (
        select(IssueTicket.wp_id)
        .where(
            IssueTicket.project_id == project_id,
            IssueTicket.wp_id.in_(wp_ids),
            IssueTicket.status.in_(["open", "in_fix"]),
            IssueTicket.due_at.isnot(None),
            IssueTicket.due_at > now,
            IssueTicket.due_at <= t_24h,
        )
        .distinct()
    )
    sla_result = await db.execute(sla_stmt)
    sla_wp_ids: set[UUID] = {r[0] for r in sla_result.all() if r[0] is not None}

    # Step 3: 查询有未解决复核意见的底稿
    review_stmt = (
        select(ReviewRecord.working_paper_id)
        .where(
            ReviewRecord.working_paper_id.in_(wp_ids),
            ReviewRecord.status == ReviewCommentStatus.open,
            ReviewRecord.is_deleted == False,  # noqa: E712
        )
        .distinct()
    )
    review_result = await db.execute(review_stmt)
    review_wp_ids: set[UUID] = {r[0] for r in review_result.all()}

    # Step 4: 计算紧急度并构建 TodoItem 列表
    items: list[TodoItem] = []
    for row in rows:
        wp_id, prefill_stale, updated_at, wp_code, wp_name, audit_cycle = row

        urgency: Literal["critical", "high", "medium", "normal"]
        urgency_reason: str

        if prefill_stale:
            urgency = "critical"
            urgency_reason = "底稿数据过期，需重新填充"
        elif wp_id in sla_wp_ids:
            urgency = "high"
            urgency_reason = "关联问题单 SLA 即将到期（≤24h）"
        elif wp_id in review_wp_ids:
            urgency = "medium"
            urgency_reason = "有未解决的复核意见"
        else:
            urgency = "normal"
            urgency_reason = "常规待办"

        items.append(
            TodoItem(
                wp_id=wp_id,
                wp_code=wp_code,
                wp_name=wp_name,
                cycle=audit_cycle or "",
                urgency=urgency,
                urgency_reason=urgency_reason,
                updated_at=updated_at,
            )
        )

    # Step 5: 按紧急度降序排序（critical > high > medium > normal）
    items.sort(key=lambda item: (URGENCY_ORDER[item.urgency], item.updated_at))

    return MyTodoResponse(items=items, total=len(items))
