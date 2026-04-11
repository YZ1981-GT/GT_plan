"""复核批注服务 — 添加/回复/解决复核意见

状态机：open → replied → resolved
         open → resolved (经理直接解决)

Validates: Requirements 5.2, 5.3, 5.4
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import ReviewCommentStatus, ReviewRecord

logger = logging.getLogger(__name__)


class WpReviewService:
    """复核批注服务

    Validates: Requirements 5.2, 5.3, 5.4
    """

    async def list_reviews(
        self,
        db: AsyncSession,
        working_paper_id: UUID,
        status: str | None = None,
    ) -> list[dict]:
        """获取复核意见列表。"""
        query = sa.select(ReviewRecord).where(
            ReviewRecord.working_paper_id == working_paper_id,
            ReviewRecord.is_deleted == sa.false(),
        )
        if status:
            query = query.where(ReviewRecord.status == status)
        query = query.order_by(ReviewRecord.created_at.desc())

        result = await db.execute(query)
        items = result.scalars().all()

        return [self._to_dict(r) for r in items]

    async def add_comment(
        self,
        db: AsyncSession,
        working_paper_id: UUID,
        commenter_id: UUID,
        comment_text: str,
        cell_reference: str | None = None,
    ) -> dict:
        """添加复核意见。

        Validates: Requirements 5.2
        """
        record = ReviewRecord(
            working_paper_id=working_paper_id,
            cell_reference=cell_reference,
            comment_text=comment_text,
            commenter_id=commenter_id,
            status=ReviewCommentStatus.open,
        )
        db.add(record)
        await db.flush()
        return self._to_dict(record)

    async def reply(
        self,
        db: AsyncSession,
        review_id: UUID,
        replier_id: UUID,
        reply_text: str,
    ) -> dict:
        """回复复核意见 (open → replied)。

        Validates: Requirements 5.3
        """
        result = await db.execute(
            sa.select(ReviewRecord).where(ReviewRecord.id == review_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise ValueError("复核意见不存在")

        if record.status != ReviewCommentStatus.open:
            raise ValueError(
                f"当前状态 {record.status.value} 不允许回复，仅 open 状态可回复"
            )

        record.status = ReviewCommentStatus.replied
        record.reply_text = reply_text
        record.replier_id = replier_id
        record.replied_at = datetime.now(timezone.utc)
        record.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return self._to_dict(record)

    async def resolve(
        self,
        db: AsyncSession,
        review_id: UUID,
        resolved_by: UUID,
    ) -> dict:
        """标记为已解决 (open/replied → resolved)。

        Validates: Requirements 5.4
        """
        result = await db.execute(
            sa.select(ReviewRecord).where(ReviewRecord.id == review_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise ValueError("复核意见不存在")

        if record.status == ReviewCommentStatus.resolved:
            raise ValueError("复核意见已解决，不可重复操作")

        record.status = ReviewCommentStatus.resolved
        record.resolved_by = resolved_by
        record.resolved_at = datetime.now(timezone.utc)
        record.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return self._to_dict(record)

    @staticmethod
    def _to_dict(record: ReviewRecord) -> dict:
        return {
            "id": str(record.id),
            "working_paper_id": str(record.working_paper_id),
            "cell_reference": record.cell_reference,
            "comment_text": record.comment_text,
            "commenter_id": str(record.commenter_id),
            "status": record.status.value if record.status else None,
            "reply_text": record.reply_text,
            "replier_id": str(record.replier_id) if record.replier_id else None,
            "replied_at": record.replied_at.isoformat() if record.replied_at else None,
            "resolved_by": str(record.resolved_by) if record.resolved_by else None,
            "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
