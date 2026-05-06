"""复核人深度指标服务

Refinement Round 3 — 需求 6：复核人深度指标。

5 个核心指标：
- avg_review_time_min: 平均复核时长（分钟），从 ReviewRecord.created_at 到 status 变为 resolved 的 updated_at
- avg_comments_per_wp: 平均每张底稿意见条数
- rejection_rate: 退回率（退回次数 / 总复核次数）
- qc_rule_catch_rate: 复核人发现问题占所有问题的比例
- sampled_rework_rate: 被质控抽查后发现漏审的比例

指标用于年度考评，非实时数据，每天凌晨刷新一次落 reviewer_metrics_snapshots 表。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, select, distinct, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qc_rating_models import ReviewerMetricsSnapshot
from app.models.workpaper_models import ReviewRecord, ReviewCommentStatus, WorkingPaper

logger = logging.getLogger(__name__)


class ReviewerMetricsService:
    """复核人深度指标计算与查询服务。"""

    async def compute_metrics(
        self, db: AsyncSession, reviewer_id: UUID, year: int
    ) -> dict:
        """计算单个复核人在指定年份的 5 项指标。

        Returns:
            dict with keys: avg_review_time_min, avg_comments_per_wp,
            rejection_rate, qc_rule_catch_rate, sampled_rework_rate
        """
        avg_review_time = await self._compute_avg_review_time(db, reviewer_id, year)
        avg_comments = await self._compute_avg_comments_per_wp(db, reviewer_id, year)
        rejection_rate = await self._compute_rejection_rate(db, reviewer_id, year)
        qc_catch_rate = await self._compute_qc_rule_catch_rate(db, reviewer_id, year)
        rework_rate = await self._compute_sampled_rework_rate(db, reviewer_id, year)

        return {
            "avg_review_time_min": avg_review_time,
            "avg_comments_per_wp": avg_comments,
            "rejection_rate": rejection_rate,
            "qc_rule_catch_rate": qc_catch_rate,
            "sampled_rework_rate": rework_rate,
        }

    async def compute_all_reviewers(self, db: AsyncSession, year: int) -> int:
        """批量计算所有复核人的指标并持久化到 reviewer_metrics_snapshots。

        Returns:
            int: 计算的复核人数量
        """
        # 找出该年度所有有复核记录的复核人
        stmt = (
            select(distinct(ReviewRecord.commenter_id))
            .where(extract("year", ReviewRecord.created_at) == year)
            .where(ReviewRecord.is_deleted == False)  # noqa: E712
        )
        result = await db.execute(stmt)
        reviewer_ids = [row[0] for row in result.all()]

        today = date.today()
        count = 0

        for rid in reviewer_ids:
            try:
                metrics = await self.compute_metrics(db, rid, year)
                snapshot = ReviewerMetricsSnapshot(
                    reviewer_id=rid,
                    year=year,
                    snapshot_date=today,
                    avg_review_time_min=metrics["avg_review_time_min"],
                    avg_comments_per_wp=metrics["avg_comments_per_wp"],
                    rejection_rate=metrics["rejection_rate"],
                    qc_rule_catch_rate=metrics["qc_rule_catch_rate"],
                    sampled_rework_rate=metrics["sampled_rework_rate"],
                )
                db.add(snapshot)
                count += 1
            except Exception as e:
                logger.warning(
                    "Failed to compute metrics for reviewer %s: %s", rid, e
                )

        await db.flush()
        return count

    async def get_metrics(
        self,
        db: AsyncSession,
        reviewer_id: UUID | None = None,
        year: int | None = None,
    ) -> list[dict]:
        """查询已存储的复核人指标快照。

        支持按 reviewer_id 和/或 year 过滤。
        返回每个复核人最新的快照记录。
        """
        # 子查询：每个 reviewer_id + year 取最新 snapshot_date
        subq = (
            select(
                ReviewerMetricsSnapshot.reviewer_id,
                ReviewerMetricsSnapshot.year,
                func.max(ReviewerMetricsSnapshot.snapshot_date).label("max_date"),
            )
            .group_by(
                ReviewerMetricsSnapshot.reviewer_id,
                ReviewerMetricsSnapshot.year,
            )
        )

        if reviewer_id:
            subq = subq.where(ReviewerMetricsSnapshot.reviewer_id == reviewer_id)
        if year:
            subq = subq.where(ReviewerMetricsSnapshot.year == year)

        subq = subq.subquery()

        stmt = (
            select(ReviewerMetricsSnapshot)
            .join(
                subq,
                and_(
                    ReviewerMetricsSnapshot.reviewer_id == subq.c.reviewer_id,
                    ReviewerMetricsSnapshot.year == subq.c.year,
                    ReviewerMetricsSnapshot.snapshot_date == subq.c.max_date,
                ),
            )
            .order_by(
                ReviewerMetricsSnapshot.year.desc(),
                ReviewerMetricsSnapshot.reviewer_id,
            )
        )

        result = await db.execute(stmt)
        snapshots = result.scalars().all()

        return [
            {
                "id": str(s.id),
                "reviewer_id": str(s.reviewer_id),
                "year": s.year,
                "snapshot_date": s.snapshot_date.isoformat() if s.snapshot_date else None,
                "avg_review_time_min": s.avg_review_time_min,
                "avg_comments_per_wp": s.avg_comments_per_wp,
                "rejection_rate": s.rejection_rate,
                "qc_rule_catch_rate": s.qc_rule_catch_rate,
                "sampled_rework_rate": s.sampled_rework_rate,
            }
            for s in snapshots
        ]

    # -----------------------------------------------------------------------
    # 内部计算方法
    # -----------------------------------------------------------------------

    async def _compute_avg_review_time(
        self, db: AsyncSession, reviewer_id: UUID, year: int
    ) -> float | None:
        """平均复核时长（分钟）。

        从 ReviewRecord.created_at 到 status 变为 resolved 的 updated_at 差值。
        只统计已 resolved 的记录。
        """
        from sqlalchemy import select as sa_select

        # Fetch resolved records and compute in Python for DB portability
        stmt = (
            sa_select(ReviewRecord.created_at, ReviewRecord.updated_at)
            .where(ReviewRecord.commenter_id == reviewer_id)
            .where(extract("year", ReviewRecord.created_at) == year)
            .where(ReviewRecord.status == ReviewCommentStatus.resolved)
            .where(ReviewRecord.is_deleted == False)  # noqa: E712
        )
        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return None

        total_minutes = 0.0
        count = 0
        for created_at, updated_at in rows:
            if created_at and updated_at:
                diff = (updated_at - created_at).total_seconds() / 60.0
                total_minutes += diff
                count += 1

        if count == 0:
            return None

        return round(total_minutes / count, 2)

    async def _compute_avg_comments_per_wp(
        self, db: AsyncSession, reviewer_id: UUID, year: int
    ) -> float | None:
        """平均每张底稿意见条数。

        该复核人在该年度的总意见数 / 涉及的底稿数。
        """
        # 总意见数
        total_stmt = (
            select(func.count(ReviewRecord.id))
            .where(ReviewRecord.commenter_id == reviewer_id)
            .where(extract("year", ReviewRecord.created_at) == year)
            .where(ReviewRecord.is_deleted == False)  # noqa: E712
        )
        total_result = await db.execute(total_stmt)
        total_comments = total_result.scalar_one_or_none() or 0

        if total_comments == 0:
            return None

        # 涉及的底稿数
        wp_count_stmt = (
            select(func.count(distinct(ReviewRecord.working_paper_id)))
            .where(ReviewRecord.commenter_id == reviewer_id)
            .where(extract("year", ReviewRecord.created_at) == year)
            .where(ReviewRecord.is_deleted == False)  # noqa: E712
        )
        wp_result = await db.execute(wp_count_stmt)
        wp_count = wp_result.scalar_one_or_none() or 0

        if wp_count == 0:
            return None

        return round(total_comments / wp_count, 2)

    async def _compute_rejection_rate(
        self, db: AsyncSession, reviewer_id: UUID, year: int
    ) -> float | None:
        """退回率 = 退回次数 / 总复核次数。

        退回：WorkingPaper.rejected_by == reviewer_id 在该年度的次数。
        总复核次数：该复核人在该年度涉及的不同底稿数。
        """
        # 退回次数：该复核人作为 rejected_by 的底稿数
        rejection_stmt = (
            select(func.count(WorkingPaper.id))
            .where(WorkingPaper.rejected_by == reviewer_id)
            .where(extract("year", WorkingPaper.rejected_at) == year)
            .where(WorkingPaper.is_deleted == False)  # noqa: E712
        )
        rej_result = await db.execute(rejection_stmt)
        rejection_count = rej_result.scalar_one_or_none() or 0

        # 总复核底稿数（该复核人在该年度有复核记录的底稿数）
        total_wp_stmt = (
            select(func.count(distinct(ReviewRecord.working_paper_id)))
            .where(ReviewRecord.commenter_id == reviewer_id)
            .where(extract("year", ReviewRecord.created_at) == year)
            .where(ReviewRecord.is_deleted == False)  # noqa: E712
        )
        total_result = await db.execute(total_wp_stmt)
        total_wp = total_result.scalar_one_or_none() or 0

        if total_wp == 0:
            return None

        return round(rejection_count / total_wp, 4)

    async def _compute_qc_rule_catch_rate(
        self, db: AsyncSession, reviewer_id: UUID, year: int
    ) -> float | None:
        """复核人发现问题占所有问题的比例。

        分子：IssueTicket where source='review_comment' and 关联到该复核人的 ReviewRecord
        分母：同年度所有 review_comment 类型的问题总数

        如果该复核人在该年度没有任何复核记录，返回 None。
        """
        from app.models.phase15_models import IssueTicket

        # 先检查该复核人是否有复核记录
        has_records_stmt = (
            select(func.count(ReviewRecord.id))
            .where(ReviewRecord.commenter_id == reviewer_id)
            .where(extract("year", ReviewRecord.created_at) == year)
            .where(ReviewRecord.is_deleted == False)  # noqa: E712
        )
        has_records_result = await db.execute(has_records_stmt)
        record_count = has_records_result.scalar_one_or_none() or 0

        if record_count == 0:
            return None

        # 该复核人通过复核发现的问题数（source='review_comment' 且关联到该复核人的 ReviewRecord）
        reviewer_issues_stmt = (
            select(func.count(IssueTicket.id))
            .join(
                ReviewRecord,
                ReviewRecord.id == IssueTicket.source_ref_id,
            )
            .where(IssueTicket.source == "review_comment")
            .where(ReviewRecord.commenter_id == reviewer_id)
            .where(extract("year", IssueTicket.created_at) == year)
        )
        reviewer_result = await db.execute(reviewer_issues_stmt)
        reviewer_issues = reviewer_result.scalar_one_or_none() or 0

        # 同年度所有 review_comment 类型的问题总数
        all_issues_stmt = (
            select(func.count(IssueTicket.id))
            .where(IssueTicket.source == "review_comment")
            .where(extract("year", IssueTicket.created_at) == year)
        )
        all_result = await db.execute(all_issues_stmt)
        all_issues = all_result.scalar_one_or_none() or 0

        if all_issues == 0:
            return None

        return round(reviewer_issues / all_issues, 4)

    async def _compute_sampled_rework_rate(
        self, db: AsyncSession, reviewer_id: UUID, year: int
    ) -> float | None:
        """被质控抽查后发现漏审的比例。

        分子：QcInspectionItem.qc_verdict='fail' 且对应底稿的 reviewer == reviewer_id
        分母：QcInspectionItem 对应底稿的 reviewer == reviewer_id 的总数
        """
        from app.models.qc_inspection_models import QcInspectionItem, QcInspection

        # 该复核人负责的底稿被抽查的总数
        base_stmt = (
            select(func.count(QcInspectionItem.id))
            .join(WorkingPaper, WorkingPaper.id == QcInspectionItem.wp_id)
            .join(QcInspection, QcInspection.id == QcInspectionItem.inspection_id)
            .where(WorkingPaper.reviewer == reviewer_id)
            .where(extract("year", QcInspectionItem.created_at) == year)
            .where(QcInspectionItem.status == "completed")
        )
        total_result = await db.execute(base_stmt)
        total_sampled = total_result.scalar_one_or_none() or 0

        if total_sampled == 0:
            return None

        # 其中 verdict='fail' 的数量
        fail_stmt = (
            select(func.count(QcInspectionItem.id))
            .join(WorkingPaper, WorkingPaper.id == QcInspectionItem.wp_id)
            .join(QcInspection, QcInspection.id == QcInspectionItem.inspection_id)
            .where(WorkingPaper.reviewer == reviewer_id)
            .where(extract("year", QcInspectionItem.created_at) == year)
            .where(QcInspectionItem.status == "completed")
            .where(QcInspectionItem.qc_verdict == "fail")
        )
        fail_result = await db.execute(fail_stmt)
        fail_count = fail_result.scalar_one_or_none() or 0

        return round(fail_count / total_sampled, 4)


# 模块级单例
reviewer_metrics_service = ReviewerMetricsService()
