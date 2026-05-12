"""Phase 15: 统一问题单服务

对齐 v2 4.5.15A: L2/L3/Q 问题统一管理 + SLA 升级

R1 需求 2（refinement-round1-review-closure）扩展：工单状态变更时
**反向同步**到关联 ``ReviewRecord`` 与底稿 ``review_status``：

- 目标状态 ``pending_recheck`` + ``source='review_comment'``
  + ``source_ref_id`` 非空 → ``ReviewRecord.reply_text`` 追加
  ``[系统] 已整改，请复验``（首次填写时则直接写 ``已整改，请复验``），
  ``replied_by/replied_at`` 同步记录。
- 目标状态 ``closed`` + 同条件 → ``ReviewRecord.status = resolved``，
  ``resolved_by/resolved_at`` 记录；并回退关联底稿 ``review_status``：
  ``level1_rejected → pending_level1`` / ``level2_rejected → pending_level2``，
  其余 review_status 不动（避免打乱流程）。

事务边界：与 ``update_status`` 同一 session 提交；任一步骤失败整体回滚。
幂等性：重复写入通过"令牌探测 + 状态探测"保证不重复追加 reply_text /
不重复切 resolved / 不重复回退 review_status。
"""
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase15_models import IssueTicket
from app.models.phase15_enums import IssueStatus, IssueSource
from app.services.trace_event_service import trace_event_service, generate_trace_id

logger = logging.getLogger(__name__)

# SLA 时限（小时）
SLA_HOURS = {"P0": 4, "P1": 24, "P2": 72}

# R3 需求 5：Q 整改单专属 SLA（小时）
Q_SLA_RESPONSE_HOURS = 48   # 48h 内必须响应（open → in_fix）
Q_SLA_COMPLETE_HOURS = 168  # 7d 内必须完成（in_fix → closed）

# 合法状态迁移
VALID_TRANSITIONS = {
    (IssueStatus.open, IssueStatus.in_fix),
    (IssueStatus.in_fix, IssueStatus.pending_recheck),
    (IssueStatus.pending_recheck, IssueStatus.closed),
    (IssueStatus.pending_recheck, IssueStatus.rejected),
    (IssueStatus.rejected, IssueStatus.in_fix),
}

# 升级链路
ESCALATION_ORDER = [IssueSource.L2, IssueSource.L3, IssueSource.Q]

# R1 需求 2：反向同步 reply_text 常量
_RECHECK_REPLY_TOKEN = "[系统] 已整改，请复验"
_RECHECK_REPLY_FIRST = "已整改，请复验"


class IssueTicketService:

    async def create_from_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        operator_id: uuid.UUID,
        sla_level: str,
        task_node_id: Optional[uuid.UUID] = None,
        source_ref_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """从复核对话创建问题单

        R6 需求 3 AC5：去重校验 — 若已存在 IssueTicket(source='review_comment',
        source_ref_id=record.id) 则直接返回已有工单，不重复创建。
        """
        # R6: 去重校验 — 按 source_ref_id 或 conversation_id 查重
        if source_ref_id is not None:
            existing_stmt = select(IssueTicket).where(
                IssueTicket.source == IssueSource.review_comment.value,
                IssueTicket.source_ref_id == source_ref_id,
            )
            existing_result = await db.execute(existing_stmt)
            existing_ticket = existing_result.scalar_one_or_none()
            if existing_ticket is not None:
                result_dict = self._to_dict(existing_ticket)
                result_dict["deduplicated"] = True
                return result_dict

        # 从 review_conversations 提取上下文
        from sqlalchemy import text as sa_text
        stmt = sa_text("""
            SELECT project_id, wp_id, title FROM review_conversations
            WHERE id = :cid LIMIT 1
        """)
        result = await db.execute(stmt, {"cid": str(conversation_id)})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="CONVERSATION_NOT_FOUND")

        project_id, wp_id, title = row

        # 推断 source
        source = IssueSource.L2  # 默认

        hours = SLA_HOURS.get(sla_level, 72)
        due_at = datetime.now(timezone.utc) + timedelta(hours=hours)
        trace_id = generate_trace_id()

        ticket = IssueTicket(
            project_id=project_id,
            wp_id=wp_id,
            task_node_id=task_node_id,
            conversation_id=conversation_id,
            source=source,
            source_ref_id=source_ref_id,
            severity="major",
            category="data_mismatch",
            title=title or "从对话创建的问题单",
            owner_id=operator_id,
            due_at=due_at,
            status=IssueStatus.open,
            trace_id=trace_id,
        )
        db.add(ticket)
        await db.flush()

        await trace_event_service.write(
            db=db,
            project_id=project_id,
            event_type="issue_created",
            object_type="issue_ticket",
            object_id=ticket.id,
            actor_id=operator_id,
            action=f"create_from_conversation:{conversation_id}",
            trace_id=trace_id,
        )

        return self._to_dict(ticket)

    async def update_status(
        self,
        db: AsyncSession,
        issue_id: uuid.UUID,
        status: str,
        operator_id: uuid.UUID,
        reason_code: str,
        evidence_refs: Optional[list] = None,
    ) -> dict:
        stmt = select(IssueTicket).where(IssueTicket.id == issue_id)
        result = await db.execute(stmt)
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise HTTPException(status_code=404, detail="ISSUE_NOT_FOUND")

        transition = (ticket.status, status)
        if transition not in VALID_TRANSITIONS:
            raise HTTPException(status_code=409, detail={
                "error_code": "ISSUE_STATUS_INVALID_TRANSITION",
                "message": f"不允许从 {ticket.status} 迁移到 {status}",
            })

        old_status = ticket.status
        ticket.status = status
        ticket.reason_code = reason_code
        if evidence_refs:
            ticket.evidence_refs = evidence_refs
        if status in (IssueStatus.closed, IssueStatus.rejected):
            ticket.closed_at = datetime.now(timezone.utc)
        await db.flush()

        # R1 需求 2：反向同步到关联 ReviewRecord + WorkingPaper.review_status
        # 仅处理 source='review_comment' 且 source_ref_id 指向 ReviewRecord 的工单；
        # 与工单状态变更共享同一事务，任一环节抛异常由外层回滚保持一致性。
        try:
            await self._sync_review_record_on_status_change(
                db,
                ticket=ticket,
                new_status=status,
                operator_id=operator_id,
            )
        except Exception:
            # 反向同步失败必须整体回滚（需求 2.4 / 2.5 强一致语义），
            # 先在这里记一次告警日志便于排查再抛出。
            logger.exception(
                "[ISSUE_REVERSE_SYNC] failed issue=%s new_status=%s", ticket.id, status
            )
            raise

        trace_id = generate_trace_id()
        await trace_event_service.write(
            db=db,
            project_id=ticket.project_id,
            event_type="issue_status_changed",
            object_type="issue_ticket",
            object_id=ticket.id,
            actor_id=operator_id,
            action=f"status:{old_status}->{status}",
            from_status=old_status,
            to_status=status,
            reason_code=reason_code,
            trace_id=trace_id,
        )

        return self._to_dict(ticket)

    async def escalate(
        self,
        db: AsyncSession,
        issue_id: uuid.UUID,
        from_level: str,
        to_level: str,
        reason_code: str,
    ) -> dict:
        stmt = select(IssueTicket).where(IssueTicket.id == issue_id)
        result = await db.execute(stmt)
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise HTTPException(status_code=404, detail="ISSUE_NOT_FOUND")

        # 校验升级方向
        from_idx = ESCALATION_ORDER.index(from_level) if from_level in [e.value for e in ESCALATION_ORDER] else -1
        to_idx = ESCALATION_ORDER.index(to_level) if to_level in [e.value for e in ESCALATION_ORDER] else -1
        if from_idx >= to_idx:
            raise HTTPException(status_code=409, detail={
                "error_code": "ISSUE_ESCALATION_INVALID",
                "message": f"不允许从 {from_level} 降级到 {to_level}",
            })

        ticket.source = to_level
        await db.flush()

        trace_id = generate_trace_id()
        await trace_event_service.write(
            db=db,
            project_id=ticket.project_id,
            event_type="issue_escalated",
            object_type="issue_ticket",
            object_id=ticket.id,
            actor_id=ticket.owner_id,
            action=f"escalate:{from_level}->{to_level}",
            reason_code=reason_code,
            trace_id=trace_id,
        )

        # Phase 15: 升级通知
        try:
            from app.services.notification_service import NotificationService
            notif_svc = NotificationService()
            await notif_svc.send_notification(
                user_id=ticket.owner_id,
                notification_type="issue_sla_escalated",
                title=f"问题单已升级: {ticket.title}",
                content=f"问题单从 {from_level} 升级到 {to_level}，原因: {reason_code}",
                metadata={
                    "issue_id": str(ticket.id),
                    "from_level": from_level,
                    "to_level": to_level,
                    "project_id": str(ticket.project_id),
                },
            )
        except Exception as _notif_err:
            logger.warning(f"[ISSUE_ESCALATE] notification failed (non-blocking): {_notif_err}")

        return self._to_dict(ticket)

    async def check_sla_timeout(self, db: AsyncSession) -> list:
        """检查 SLA 超时的问题单并自动升级"""
        stmt = (
            select(IssueTicket)
            .where(IssueTicket.status.in_([IssueStatus.open, IssueStatus.in_fix]))
            .where(IssueTicket.due_at < datetime.now(timezone.utc))
        )
        result = await db.execute(stmt)
        tickets = result.scalars().all()

        escalated = []
        for ticket in tickets:
            # R3 需求 5：Q 整改单专属 SLA 处理
            if ticket.source == IssueSource.Q.value:
                await self._handle_q_sla_timeout(db, ticket)
                escalated.append(self._to_dict(ticket))
                continue

            current_idx = -1
            for i, level in enumerate(ESCALATION_ORDER):
                if ticket.source == level.value:
                    current_idx = i
                    break
            if current_idx < len(ESCALATION_ORDER) - 1:
                next_level = ESCALATION_ORDER[current_idx + 1].value
                try:
                    result = await self.escalate(
                        db, ticket.id, ticket.source, next_level, "SLA_TIMEOUT"
                    )
                    escalated.append(result)
                except Exception as e:
                    logger.error(f"[SLA_TIMEOUT] escalate failed: issue={ticket.id} error={e}")

        return escalated

    async def _handle_q_sla_timeout(self, db: AsyncSession, ticket: IssueTicket) -> None:
        """R3 需求 5：Q 整改单专属 SLA 处理

        - 48h 响应 SLA：open 状态超 48h 未转 in_fix → 升级通知到签字合伙人
        - 7d 完成 SLA：in_fix 状态超 7d 未关闭 → 升级通知到签字合伙人
        - 使用 reason_code 标记逾期状态（'Q_SLA_BREACHED'）
        """
        now = datetime.now(timezone.utc)
        hours_overdue = (now - ticket.due_at).total_seconds() / 3600 if ticket.due_at else 0

        # 标记逾期（用 reason_code 字段，避免新增列）
        if ticket.reason_code != "Q_SLA_BREACHED":
            ticket.reason_code = "Q_SLA_BREACHED"

        # 发送升级通知到签字合伙人
        try:
            from app.models.core import Project
            from app.services.notification_service import notification_service

            project = (await db.execute(
                select(Project).where(Project.id == ticket.project_id)
            )).scalar_one_or_none()

            if project and project.created_by:
                await notification_service.create_notification(
                    db,
                    user_id=project.created_by,
                    notification_type="qc_sla_breach",
                    title=f"质控整改单逾期：{ticket.title[:50]}",
                    content=f"工单已逾期 {int(hours_overdue)} 小时，请督促整改",
                    related_object_type="issue_ticket",
                    related_object_id=str(ticket.id),
                )
        except Exception as e:
            logger.warning("[Q-SLA] notification failed: %s", e)

        await db.flush()

    async def list_issues(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        source: Optional[str] = None,
        owner_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        stmt = select(IssueTicket).where(IssueTicket.project_id == project_id)
        if status:
            stmt = stmt.where(IssueTicket.status == status)
        if severity:
            stmt = stmt.where(IssueTicket.severity == severity)
        if source:
            stmt = stmt.where(IssueTicket.source == source)
        if owner_id:
            stmt = stmt.where(IssueTicket.owner_id == owner_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(IssueTicket.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        tickets = result.scalars().all()

        return {
            "items": [self._to_dict(t) for t in tickets],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ------------------------------------------------------------------
    # R1 需求 2：反向同步 工单 → ReviewRecord / WorkingPaper.review_status
    # ------------------------------------------------------------------
    async def _sync_review_record_on_status_change(
        self,
        db: AsyncSession,
        *,
        ticket: IssueTicket,
        new_status: str,
        operator_id: uuid.UUID,
    ) -> None:
        """工单状态流转时反向刷新关联复核批注与底稿复核状态。

        仅对"来源为复核意见（``source='review_comment'``）"且 ``source_ref_id``
        非空的工单生效；其他来源（L2/L3/Q 等）直接 no-op。

        目标状态:
          - ``pending_recheck`` → ReviewRecord.reply_text 追加 "已整改，请复验"
          - ``closed``          → ReviewRecord.status=resolved +
                                  底稿 review_status 回退 (level1_rejected →
                                  pending_level1 / level2_rejected →
                                  pending_level2；其他 review_status 不动)

        幂等:
          - reply_text 已含令牌串则不重复追加；
          - ReviewRecord 已 resolved 则不重复切；
          - 底稿 review_status 已非 rejected 则不回退。
        """
        if new_status not in (
            IssueStatus.pending_recheck,
            IssueStatus.closed,
        ):
            return
        if ticket.source != IssueSource.review_comment.value:
            return
        if ticket.source_ref_id is None:
            return

        # 延迟导入避免循环依赖
        from app.models.workpaper_models import (
            ReviewCommentStatus,
            ReviewRecord,
            WorkingPaper,
            WpReviewStatus,
        )

        review = await db.get(ReviewRecord, ticket.source_ref_id)
        if review is None:
            # 关联 ReviewRecord 已被软删除或 ID 失效：不阻断工单状态变更，
            # 仅记 warning 便于排查。
            logger.warning(
                "[ISSUE_REVERSE_SYNC] ReviewRecord not found: ticket=%s source_ref_id=%s",
                ticket.id,
                ticket.source_ref_id,
            )
            return

        now = datetime.now(timezone.utc)

        if new_status == IssueStatus.pending_recheck:
            existing_reply = (review.reply_text or "").strip()
            if _RECHECK_REPLY_TOKEN in existing_reply or (
                existing_reply == _RECHECK_REPLY_FIRST
            ):
                # 幂等：已追加过则不再重复写
                logger.debug(
                    "[ISSUE_REVERSE_SYNC] reply_text already contains recheck token "
                    "(ticket=%s review=%s)",
                    ticket.id,
                    review.id,
                )
            else:
                if existing_reply:
                    review.reply_text = f"{existing_reply}\n{_RECHECK_REPLY_TOKEN}"
                else:
                    review.reply_text = _RECHECK_REPLY_FIRST
                # 编制人的回复动作：替换 replier_id/replied_at 为当前操作者
                review.replier_id = operator_id
                review.replied_at = now
                # open → replied 状态切换（resolved 时不回退）
                if review.status == ReviewCommentStatus.open:
                    review.status = ReviewCommentStatus.replied
                review.updated_at = now
                await db.flush()

                # 审计日志：记录反向同步动作
                try:
                    from app.services.audit_logger_enhanced import audit_logger

                    await audit_logger.log_action(
                        user_id=operator_id,
                        action="review_record.replied_by_ticket",
                        object_type="review_record",
                        object_id=review.id,
                        project_id=ticket.project_id,
                        details={
                            "ticket_id": str(ticket.id),
                            "wp_id": str(ticket.wp_id) if ticket.wp_id else None,
                            "trigger": "issue.pending_recheck",
                        },
                    )
                except Exception as log_err:  # noqa: BLE001
                    # 审计日志失败仅 warning，不阻断业务（审计记录非强一致）
                    logger.warning(
                        "[ISSUE_REVERSE_SYNC] audit log failed (non-blocking): %s",
                        log_err,
                    )

        elif new_status == IssueStatus.closed:
            # 1) ReviewRecord resolved（幂等：已 resolved 跳过）
            if review.status != ReviewCommentStatus.resolved:
                review.status = ReviewCommentStatus.resolved
                review.resolved_by = operator_id
                review.resolved_at = now
                review.updated_at = now
                await db.flush()

                try:
                    from app.services.audit_logger_enhanced import audit_logger

                    await audit_logger.log_action(
                        user_id=operator_id,
                        action="review_record.resolved_by_ticket",
                        object_type="review_record",
                        object_id=review.id,
                        project_id=ticket.project_id,
                        details={
                            "ticket_id": str(ticket.id),
                            "wp_id": str(ticket.wp_id) if ticket.wp_id else None,
                            "trigger": "issue.closed",
                        },
                    )
                except Exception as log_err:  # noqa: BLE001
                    logger.warning(
                        "[ISSUE_REVERSE_SYNC] audit log failed (non-blocking): %s",
                        log_err,
                    )

            # 2) 底稿 review_status 回退（仅 rejected 两态）
            wp_id = ticket.wp_id or review.working_paper_id
            if wp_id is None:
                return
            wp = await db.get(WorkingPaper, wp_id)
            if wp is None:
                logger.warning(
                    "[ISSUE_REVERSE_SYNC] WorkingPaper not found: ticket=%s wp_id=%s",
                    ticket.id,
                    wp_id,
                )
                return

            current_rv = wp.review_status.value if wp.review_status else None
            revert_map = {
                WpReviewStatus.level1_rejected.value: WpReviewStatus.pending_level1,
                WpReviewStatus.level2_rejected.value: WpReviewStatus.pending_level2,
            }
            next_rv = revert_map.get(current_rv)
            if next_rv is not None:
                wp.review_status = next_rv
                wp.updated_at = now
                await db.flush()
                logger.info(
                    "[ISSUE_REVERSE_SYNC] wp=%s review_status %s → %s (by ticket=%s)",
                    wp.id,
                    current_rv,
                    next_rv.value,
                    ticket.id,
                )
            else:
                logger.debug(
                    "[ISSUE_REVERSE_SYNC] wp=%s review_status=%s not a rejected state, skip revert",
                    wp.id,
                    current_rv,
                )

    def _to_dict(self, ticket: IssueTicket) -> dict:
        return {
            "id": str(ticket.id),
            "project_id": str(ticket.project_id),
            "wp_id": str(ticket.wp_id) if ticket.wp_id else None,
            "task_node_id": str(ticket.task_node_id) if ticket.task_node_id else None,
            "conversation_id": str(ticket.conversation_id) if ticket.conversation_id else None,
            "source": ticket.source,
            "severity": ticket.severity,
            "category": ticket.category,
            "title": ticket.title,
            "owner_id": str(ticket.owner_id),
            "due_at": ticket.due_at.isoformat() if ticket.due_at else None,
            "status": ticket.status,
            "reason_code": ticket.reason_code,
            "trace_id": ticket.trace_id,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
        }


issue_ticket_service = IssueTicketService()
