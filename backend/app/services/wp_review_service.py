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
    ) -> dict:
        """添加复核意见。

        Validates: Requirements 5.2

        Parameters
        ----------
        is_reject : bool, default False
            当复核人退回底稿并附意见时（R1 需求 2），传 ``True`` 将同步创建
            关联 ``IssueTicket(source='review_comment')``。工单创建失败不
            阻断本方法（复核意见仍成功写入），由事件补偿兜底。
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

    抛出的任何异常由调用方决定是否吞掉（主流程吞掉 + 发补偿事件，补偿
    handler 按幂等跳过即可）。
    """
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
