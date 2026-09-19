"""复核批注服务 — 添加/回复/解决复核意见

状态机：open → replied → resolved
         open → resolved (经理直接解决)

Validates: Requirements 5.2, 5.3, 5.4

R1 需求 2 扩展：
  - 添加复核意见时（``add_comment``），若调用方标记为 ``is_reject=True``
    （复核人退回场景），则同步自动创建一张 ``IssueTicket``：
      * ``source='review_comment'``
      * ``source_ref_id=review_record.id`` （双向关联）
      * ``cell_ref=ReviewRecord.cell_reference``
  - 工单创建失败**不阻断**复核动作（退回写入仍成功），失败时：
      * 记 warning 日志
      * 发布 ``REVIEW_RECORD_CREATED`` 事件，供 ``event_handlers`` 订阅做补偿
        重建，防止漏单（需求 2.7 联动守卫）
  - 订阅端（``event_handlers.py``）以"是否已存在对应 IssueTicket"做幂等判定，
    已存在则跳过。

依据：``refinement-round1-review-closure/requirements.md`` 需求 2。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.phase15_enums import IssueCategory, IssueSource, IssueStatus
from app.models.phase15_models import IssueTicket
from app.models.workpaper_models import (
    ReviewCommentStatus,
    ReviewRecord,
    WorkingPaper,
)

logger = logging.getLogger(__name__)


# 退回/复核意见的默认 SLA（小时）— P1 级，与 issue_ticket_service.SLA_HOURS 一致
_REVIEW_COMMENT_SLA_HOURS = 24


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
        *,
        is_reject: bool = False,
        evidence_refs: list[dict] | None = None,
    ) -> dict:
        """添加复核意见。

        Validates: Requirements 5.2

        Parameters
        ----------
        is_reject : bool, default False
            当复核人退回底稿并附意见时（R1 需求 2），传 ``True`` 将同步创建
            关联 ``IssueTicket(source='review_comment')``。工单创建失败不
            阻断本方法（复核意见仍成功写入），由事件补偿兜底。
        evidence_refs : list[dict] | None
            P1-1: 关联的 EvidenceRef 列表（底稿单元格、附件、报告段落、附注表格）
        """
        record = ReviewRecord(
            working_paper_id=working_paper_id,
            cell_reference=cell_reference,
            comment_text=comment_text,
            commenter_id=commenter_id,
            status=ReviewCommentStatus.open,
            evidence_refs=evidence_refs or [],
        )
        db.add(record)
        await db.flush()

        if is_reject:
            # 尝试同步创建 IssueTicket；任何异常都不阻断复核动作。
            await self._create_issue_ticket_from_review(
                db,
                review_record=record,
                commenter_id=commenter_id,
            )

        return self._to_dict(record)

    async def _create_issue_ticket_from_review(
        self,
        db: AsyncSession,
        *,
        review_record: ReviewRecord,
        commenter_id: UUID,
    ) -> IssueTicket | None:
        """复核退回 → IssueTicket 同步创建（失败不阻断）。

        见本模块 docstring。失败时：
          1. 用 SAVEPOINT（``begin_nested``）隔离异常，保证外层 ReviewRecord
             事务不被污染回滚；
          2. 发 ``REVIEW_RECORD_CREATED`` 事件，供 ``event_handlers`` 订阅做
             补偿重建；
          3. 返回 ``None``，调用方继续正常流程。
        """
        ticket: IssueTicket | None = None
        ticket_create_failed = False
        try:
            # SAVEPOINT 隔离：IssueTicket 创建失败只回滚到此处，不影响外层
            # 已 flush 的 ReviewRecord。
            async with db.begin_nested():
                ticket = await _build_and_persist_issue_ticket(
                    db,
                    review_record=review_record,
                    commenter_id=commenter_id,
                )
        except Exception as exc:  # noqa: BLE001
            ticket_create_failed = True
            logger.warning(
                "[WP_REVIEW] IssueTicket create from review_record=%s failed: %s",
                review_record.id,
                exc,
            )

        # 无论成功失败都发 REVIEW_RECORD_CREATED 事件（幂等订阅），这样即使
        # 订阅端在真正补偿前又看到成功创建的工单也不会重复。
        try:
            wp = await db.get(WorkingPaper, review_record.working_paper_id)
            project_id = wp.project_id if wp is not None else None
            from app.services.event_bus import event_bus

            await event_bus.publish_immediate(
                EventPayload(
                    event_type=EventType.REVIEW_RECORD_CREATED,
                    project_id=project_id,
                    extra={
                        "review_record_id": str(review_record.id),
                        "working_paper_id": str(review_record.working_paper_id),
                        "commenter_id": str(commenter_id),
                        "ticket_created": not ticket_create_failed,
                    },
                )
            )
        except Exception as pub_exc:  # noqa: BLE001
            logger.warning(
                "[WP_REVIEW] REVIEW_RECORD_CREATED publish failed review=%s: %s",
                review_record.id,
                pub_exc,
            )

        return ticket

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
        *,
        close_reason: str | None = None,
        close_evidence_refs: list[dict] | None = None,
    ) -> dict:
        """标记为已解决 (open/replied → resolved)。

        Validates: Requirements 5.4
        P1-1.3: 重大复核意见（priority=must_fix）关闭必须填写关闭依据。
        """
        result = await db.execute(
            sa.select(ReviewRecord).where(ReviewRecord.id == review_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise ValueError("复核意见不存在")

        if record.status == ReviewCommentStatus.resolved:
            raise ValueError("复核意见已解决，不可重复操作")

        # P1-1.3: 重大复核意见关闭必须提供关闭依据
        if record.priority == "must_fix":
            if not close_reason and not close_evidence_refs:
                raise ValueError("重大复核意见（must_fix）关闭必须填写关闭依据或关联整改证据")

        record.status = ReviewCommentStatus.resolved
        record.resolved_by = resolved_by
        record.resolved_at = datetime.now(timezone.utc)
        record.updated_at = datetime.now(timezone.utc)
        if close_reason:
            record.close_reason = close_reason
        if close_evidence_refs:
            record.close_evidence_refs = close_evidence_refs
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
            "priority": record.priority if record.priority else "suggest",
            "reply_text": record.reply_text,
            "replier_id": str(record.replier_id) if record.replier_id else None,
            "replied_at": record.replied_at.isoformat() if record.replied_at else None,
            "resolved_by": str(record.resolved_by) if record.resolved_by else None,
            "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
            "evidence_refs": record.evidence_refs or [],
            "close_evidence_refs": record.close_evidence_refs or [],
            "close_reason": record.close_reason,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    async def get_review_stats(
        self,
        db: AsyncSession,
        project_id: UUID,
        *,
        sla_hours: int = _REVIEW_COMMENT_SLA_HOURS,
    ) -> dict:
        """P1-1.4: 统计 Aging、重复问题、逾期未回复。

        Returns
        -------
        dict with keys:
            - total_open: 未解决复核意见数
            - overdue_count: 超过 SLA 未回复的意见数
            - aging_buckets: {0-24h, 24-72h, >72h} 分桶统计
            - duplicate_count: 同一 working_paper + cell_reference 重复出现数
        """
        now = datetime.now(timezone.utc)
        sla_cutoff = now - timedelta(hours=sla_hours)

        # 查找项目下所有 open 状态复核意见（需 JOIN working_paper 取 project_id）
        from app.models.workpaper_models import WorkingPaper

        base_cond = [
            ReviewRecord.is_deleted == sa.false(),
            ReviewRecord.status == ReviewCommentStatus.open,
            WorkingPaper.project_id == project_id,
        ]

        # Total open
        total_stmt = (
            sa.select(sa.func.count())
            .select_from(ReviewRecord)
            .join(WorkingPaper, WorkingPaper.id == ReviewRecord.working_paper_id)
            .where(*base_cond)
        )
        total_result = await db.execute(total_stmt)
        total_open = total_result.scalar() or 0

        # Overdue (open + created > SLA hours ago)
        overdue_stmt = (
            sa.select(sa.func.count())
            .select_from(ReviewRecord)
            .join(WorkingPaper, WorkingPaper.id == ReviewRecord.working_paper_id)
            .where(*base_cond, ReviewRecord.created_at < sla_cutoff)
        )
        overdue_result = await db.execute(overdue_stmt)
        overdue_count = overdue_result.scalar() or 0

        # Aging buckets
        bucket_24h = now - timedelta(hours=24)
        bucket_72h = now - timedelta(hours=72)

        aging_0_24_stmt = (
            sa.select(sa.func.count())
            .select_from(ReviewRecord)
            .join(WorkingPaper, WorkingPaper.id == ReviewRecord.working_paper_id)
            .where(*base_cond, ReviewRecord.created_at >= bucket_24h)
        )
        aging_24_72_stmt = (
            sa.select(sa.func.count())
            .select_from(ReviewRecord)
            .join(WorkingPaper, WorkingPaper.id == ReviewRecord.working_paper_id)
            .where(
                *base_cond,
                ReviewRecord.created_at < bucket_24h,
                ReviewRecord.created_at >= bucket_72h,
            )
        )
        aging_gt72_stmt = (
            sa.select(sa.func.count())
            .select_from(ReviewRecord)
            .join(WorkingPaper, WorkingPaper.id == ReviewRecord.working_paper_id)
            .where(*base_cond, ReviewRecord.created_at < bucket_72h)
        )

        r1 = await db.execute(aging_0_24_stmt)
        r2 = await db.execute(aging_24_72_stmt)
        r3 = await db.execute(aging_gt72_stmt)

        aging_buckets = {
            "0_24h": r1.scalar() or 0,
            "24_72h": r2.scalar() or 0,
            "gt_72h": r3.scalar() or 0,
        }

        # Duplicate issues: same working_paper_id + cell_reference appears > 1 time
        dup_stmt = (
            sa.select(sa.func.count())
            .select_from(
                sa.select(
                    ReviewRecord.working_paper_id,
                    ReviewRecord.cell_reference,
                )
                .join(WorkingPaper, WorkingPaper.id == ReviewRecord.working_paper_id)
                .where(
                    ReviewRecord.is_deleted == sa.false(),
                    WorkingPaper.project_id == project_id,
                    ReviewRecord.cell_reference.isnot(None),
                )
                .group_by(ReviewRecord.working_paper_id, ReviewRecord.cell_reference)
                .having(sa.func.count() > 1)
                .subquery()
            )
        )
        dup_result = await db.execute(dup_stmt)
        duplicate_count = dup_result.scalar() or 0

        return {
            "total_open": total_open,
            "overdue_count": overdue_count,
            "aging_buckets": aging_buckets,
            "duplicate_count": duplicate_count,
        }


# ---------------------------------------------------------------------------
# 公共辅助：用于主流程 + 事件补偿复用同一套字段填充逻辑
# ---------------------------------------------------------------------------


async def _build_and_persist_issue_ticket(
    db: AsyncSession,
    *,
    review_record: ReviewRecord,
    commenter_id: UUID,
) -> IssueTicket:
    """按 R1 需求 2 的字段契约创建 IssueTicket 并 flush 到 DB。

    R6 需求 3 AC5：去重校验 — 若已存在 IssueTicket(source='review_comment',
    source_ref_id=record.id) 则直接返回已有工单，不重复创建。

    抛出的任何异常由调用方决定是否吞掉（主流程吞掉 + 发补偿事件，补偿
    handler 按幂等跳过即可）。
    """
    # R6: 去重校验
    import sqlalchemy as sa
    existing_stmt = sa.select(IssueTicket).where(
        IssueTicket.source == IssueSource.review_comment.value,
        IssueTicket.source_ref_id == review_record.id,
    )
    existing_result = await db.execute(existing_stmt)
    existing_ticket = existing_result.scalar_one_or_none()
    if existing_ticket is not None:
        logger.info(
            "[WP_REVIEW] IssueTicket already exists for ReviewRecord=%s ticket=%s (dedup)",
            review_record.id,
            existing_ticket.id,
        )
        return existing_ticket

    wp = await db.get(WorkingPaper, review_record.working_paper_id)
    if wp is None:
        raise ValueError(f"WorkingPaper {review_record.working_paper_id} not found")

    # owner_id：优先 assigned_to（编制人），其次 created_by，兜底 commenter_id
    owner_id = wp.assigned_to or wp.created_by or commenter_id

    # title：截取 comment 前 60 字
    comment_snippet = (review_record.comment_text or "").strip().splitlines()[0][:60]
    if comment_snippet:
        title = f"复核退回：{comment_snippet}"
    else:
        title = "复核退回意见"

    trace_id = _generate_trace_id()
    ticket = IssueTicket(
        project_id=wp.project_id,
        wp_id=wp.id,
        source=IssueSource.review_comment.value,
        source_ref_id=review_record.id,
        severity="major",
        category=IssueCategory.procedure_incomplete.value,
        title=title[:200],
        description=review_record.comment_text,
        owner_id=owner_id,
        due_at=datetime.now(timezone.utc) + timedelta(hours=_REVIEW_COMMENT_SLA_HOURS),
        status=IssueStatus.open.value,
        trace_id=trace_id,
        evidence_refs=[],
    )
    db.add(ticket)
    await db.flush()
    logger.info(
        "[WP_REVIEW] IssueTicket created from ReviewRecord=%s ticket=%s",
        review_record.id,
        ticket.id,
    )
    return ticket


def _generate_trace_id() -> str:
    """延迟导入 trace_event_service.generate_trace_id，避免循环依赖。"""
    try:
        from app.services.trace_event_service import generate_trace_id

        return generate_trace_id()
    except Exception:  # noqa: BLE001
        import uuid as _uuid

        return f"trc_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{_uuid.uuid4().hex[:12]}"
