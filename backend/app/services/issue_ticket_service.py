"""Phase 15: 统一问题单服务

对齐 v2 4.5.15A: L2/L3/Q 问题统一管理 + SLA 升级
"""
import uuid
import logging
from datetime import datetime, timedelta
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


class IssueTicketService:

    async def create_from_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        operator_id: uuid.UUID,
        sla_level: str,
        task_node_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """从复核对话创建问题单"""
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
        due_at = datetime.utcnow() + timedelta(hours=hours)
        trace_id = generate_trace_id()

        ticket = IssueTicket(
            project_id=project_id,
            wp_id=wp_id,
            task_node_id=task_node_id,
            conversation_id=conversation_id,
            source=source,
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
            ticket.closed_at = datetime.utcnow()
        await db.flush()

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
            .where(IssueTicket.due_at < datetime.utcnow())
        )
        result = await db.execute(stmt)
        tickets = result.scalars().all()

        escalated = []
        for ticket in tickets:
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
