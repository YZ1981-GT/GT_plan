"""归档前完整性自检报告服务

Requirements: 3.2, 3.3, 3.4, 3.5

四类检查：
1. missing — 缺失底稿（WpIndex 有记录但无对应 WorkingPaper）
2. unsigned — 未签字底稿（status 非 review_passed / archived）
3. unresolved_reviews — 有未解决复核意见
4. stale — 数据过期底稿（prefill_stale=true）

每类计算 count + items 列表 + is_blocking 标记。
can_proceed = True 当且仅当无 blocking 类别有 count > 0。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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


class CheckItem(BaseModel):
    wp_code: str
    wp_name: str
    assignee: str | None
    status: str


class CheckCategory(BaseModel):
    category: Literal["missing", "unsigned", "unresolved_reviews", "stale"]
    count: int
    items: list[CheckItem]
    is_blocking: bool


class CompletenessReportResponse(BaseModel):
    categories: list[CheckCategory]  # 固定 4 类
    can_proceed: bool  # 无 blocking 项时 True
    generated_at: datetime


# ---------------------------------------------------------------------------
# Blocking rules
# ---------------------------------------------------------------------------

# missing 和 unsigned 是 blocking（阻断归档）
# unresolved_reviews 和 stale 是 blocking（阻断归档）
BLOCKING_CATEGORIES: set[str] = {"missing", "unsigned", "unresolved_reviews", "stale"}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


async def get_archive_completeness_report(
    db: AsyncSession,
    project_id: UUID,
) -> CompletenessReportResponse:
    """生成归档前完整性自检报告。

    Returns 4 categories with counts, items, and blocking flags.
    can_proceed is True only if no blocking category has count > 0.
    """

    # --- 1. 缺失底稿：WpIndex 有记录但无对应 WorkingPaper ---
    missing_items = await _check_missing(db, project_id)

    # --- 2. 未签字底稿：status 非 review_passed / archived ---
    unsigned_items = await _check_unsigned(db, project_id)

    # --- 3. 未解决复核意见 ---
    unresolved_items = await _check_unresolved_reviews(db, project_id)

    # --- 4. Stale 底稿 ---
    stale_items = await _check_stale(db, project_id)

    # Build categories
    categories = [
        CheckCategory(
            category="missing",
            count=len(missing_items),
            items=missing_items,
            is_blocking=True,
        ),
        CheckCategory(
            category="unsigned",
            count=len(unsigned_items),
            items=unsigned_items,
            is_blocking=True,
        ),
        CheckCategory(
            category="unresolved_reviews",
            count=len(unresolved_items),
            items=unresolved_items,
            is_blocking=True,
        ),
        CheckCategory(
            category="stale",
            count=len(stale_items),
            items=stale_items,
            is_blocking=True,
        ),
    ]

    # can_proceed: True iff no blocking category has count > 0
    can_proceed = all(
        not (cat.is_blocking and cat.count > 0) for cat in categories
    )

    return CompletenessReportResponse(
        categories=categories,
        can_proceed=can_proceed,
        generated_at=datetime.now(timezone.utc),
    )


async def _check_missing(
    db: AsyncSession, project_id: UUID
) -> list[CheckItem]:
    """缺失底稿：WpIndex 有记录但无对应 WorkingPaper（或已删除）。"""
    # Subquery: wp_index_ids that have a non-deleted WorkingPaper
    existing_wp_subq = (
        select(WorkingPaper.wp_index_id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
        .scalar_subquery()
    )

    stmt = (
        select(
            WpIndex.wp_code,
            WpIndex.wp_name,
            WpIndex.assigned_to,
        )
        .where(
            WpIndex.project_id == project_id,
            WpIndex.is_deleted == False,  # noqa: E712
            WpIndex.id.notin_(
                select(WorkingPaper.wp_index_id).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == False,  # noqa: E712
                )
            ),
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        CheckItem(
            wp_code=row[0],
            wp_name=row[1],
            assignee=str(row[2]) if row[2] else None,
            status="missing",
        )
        for row in rows
    ]


async def _check_unsigned(
    db: AsyncSession, project_id: UUID
) -> list[CheckItem]:
    """未签字底稿：status 非 review_passed / archived。"""
    stmt = (
        select(
            WpIndex.wp_code,
            WpIndex.wp_name,
            WorkingPaper.assigned_to,
            WorkingPaper.status,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
            WorkingPaper.status.notin_(["review_passed", "archived"]),
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        CheckItem(
            wp_code=row[0],
            wp_name=row[1],
            assignee=str(row[2]) if row[2] else None,
            status=row[3].value if hasattr(row[3], "value") else str(row[3]),
        )
        for row in rows
    ]


async def _check_unresolved_reviews(
    db: AsyncSession, project_id: UUID
) -> list[CheckItem]:
    """有未解决复核意见的底稿。"""
    # Find working papers with open review comments
    stmt = (
        select(
            WpIndex.wp_code,
            WpIndex.wp_name,
            WorkingPaper.assigned_to,
            WorkingPaper.status,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
            WorkingPaper.id.in_(
                select(ReviewRecord.working_paper_id)
                .where(
                    ReviewRecord.status == ReviewCommentStatus.open,
                    ReviewRecord.is_deleted == False,  # noqa: E712
                )
                .distinct()
            ),
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        CheckItem(
            wp_code=row[0],
            wp_name=row[1],
            assignee=str(row[2]) if row[2] else None,
            status="unresolved_reviews",
        )
        for row in rows
    ]


async def _check_stale(
    db: AsyncSession, project_id: UUID
) -> list[CheckItem]:
    """Stale 底稿：prefill_stale=true。"""
    stmt = (
        select(
            WpIndex.wp_code,
            WpIndex.wp_name,
            WorkingPaper.assigned_to,
            WorkingPaper.status,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
            WorkingPaper.prefill_stale == True,  # noqa: E712
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        CheckItem(
            wp_code=row[0],
            wp_name=row[1],
            assignee=str(row[2]) if row[2] else None,
            status="stale",
        )
        for row in rows
    ]
