"""PBC 清单服务 — wp-evidence-collection spec

职责：
  1. PBC 清单 CRUD
  2. 状态流转（pending → received → reviewed）
  3. 关联底稿/审计循环
  4. 逾期检测 + 自动建 IssueTicket
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration_models import PBCChecklist, PbcStatus

logger = logging.getLogger(__name__)


class PbcService:
    """PBC 清单服务"""

    async def list_items(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        *,
        status: Optional[str] = None,
        cycle_code: Optional[str] = None,
        wp_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """获取项目 PBC 清单"""
        stmt = select(PBCChecklist).where(
            and_(
                PBCChecklist.project_id == project_id,
                PBCChecklist.is_deleted == False,  # noqa: E712
            )
        )
        if status:
            stmt = stmt.where(PBCChecklist.status == status)
        if cycle_code:
            stmt = stmt.where(PBCChecklist.cycle_code == cycle_code)
        if wp_id:
            stmt = stmt.where(PBCChecklist.wp_id == wp_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(PBCChecklist.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        items = result.scalars().all()

        return {
            "items": [self._to_dict(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def create_item(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        *,
        item_name: str,
        category: Optional[str] = None,
        wp_id: Optional[uuid.UUID] = None,
        cycle_code: Optional[str] = None,
        due_date: Optional[date] = None,
        requested_date: Optional[date] = None,
        requested_by: Optional[uuid.UUID] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """创建 PBC 项"""
        item = PBCChecklist(
            project_id=project_id,
            item_name=item_name,
            category=category,
            wp_id=wp_id,
            cycle_code=cycle_code,
            due_date=due_date,
            requested_date=requested_date or date.today(),
            requested_by=requested_by,
            notes=notes,
            status=PbcStatus.PENDING,
        )
        db.add(item)
        await db.flush()
        logger.info("PBC item created: project=%s name=%s", project_id, item_name)
        return self._to_dict(item)

    async def update_item(
        self,
        db: AsyncSession,
        item_id: uuid.UUID,
        **kwargs,
    ) -> dict | None:
        """更新 PBC 项"""
        stmt = select(PBCChecklist).where(
            and_(PBCChecklist.id == item_id, PBCChecklist.is_deleted == False)  # noqa: E712
        )
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(item, key):
                setattr(item, key, value)

        await db.flush()
        return self._to_dict(item)

    async def delete_item(
        self,
        db: AsyncSession,
        item_id: uuid.UUID,
    ) -> bool:
        """软删除 PBC 项"""
        stmt = select(PBCChecklist).where(
            and_(PBCChecklist.id == item_id, PBCChecklist.is_deleted == False)  # noqa: E712
        )
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return False

        item.is_deleted = True
        await db.flush()
        return True

    async def receive_item(
        self,
        db: AsyncSession,
        item_id: uuid.UUID,
        received_by: uuid.UUID,
    ) -> dict | None:
        """客户上传资料 → PBC 项状态 pending→received"""
        stmt = select(PBCChecklist).where(
            and_(PBCChecklist.id == item_id, PBCChecklist.is_deleted == False)  # noqa: E712
        )
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return None

        if item.status != PbcStatus.PENDING:
            return self._to_dict(item)

        item.status = PbcStatus.RECEIVED
        item.received_date = date.today()
        item.received_by = received_by
        await db.flush()
        logger.info("PBC item received: id=%s", item_id)
        return self._to_dict(item)

    async def get_items_by_workpaper(
        self,
        db: AsyncSession,
        wp_id: uuid.UUID,
    ) -> list[dict]:
        """获取底稿关联的 PBC 项（侧栏用）"""
        stmt = select(PBCChecklist).where(
            and_(
                PBCChecklist.wp_id == wp_id,
                PBCChecklist.is_deleted == False,  # noqa: E712
            )
        ).order_by(PBCChecklist.created_at.desc())
        result = await db.execute(stmt)
        items = result.scalars().all()
        return [self._to_dict(item) for item in items]

    async def check_overdue_items(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
    ) -> list[dict]:
        """检测逾期未收 PBC 项"""
        today = date.today()
        stmt = select(PBCChecklist).where(
            and_(
                PBCChecklist.project_id == project_id,
                PBCChecklist.status == PbcStatus.PENDING,
                PBCChecklist.due_date != None,  # noqa: E711
                PBCChecklist.due_date < today,
                PBCChecklist.is_deleted == False,  # noqa: E712
            )
        )
        result = await db.execute(stmt)
        items = result.scalars().all()
        return [self._to_dict(item) for item in items]

    async def create_overdue_tickets(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[dict]:
        """PBC 逾期 → 自动建 IssueTicket（source=pbc）+ 通知"""
        from app.models.phase15_models import IssueTicket
        from app.services.trace_event_service import generate_trace_id

        overdue_items = await self.check_overdue_items(db, project_id)
        tickets_created = []

        for item in overdue_items:
            # 检查是否已有对应 ticket（幂等）
            existing = await db.execute(
                select(IssueTicket).where(
                    and_(
                        IssueTicket.source == "pbc",
                        IssueTicket.source_ref_id == uuid.UUID(item["id"]),
                        IssueTicket.project_id == project_id,
                    )
                )
            )
            if existing.scalar_one_or_none():
                continue

            ticket = IssueTicket(
                project_id=project_id,
                source="pbc",
                source_ref_id=uuid.UUID(item["id"]),
                severity="major",
                category="evidence_missing",
                title=f"PBC 逾期未收: {item['item_name']}",
                description=f"PBC 项「{item['item_name']}」已逾期，请催收。",
                owner_id=owner_id,
                due_at=datetime.now(timezone.utc) + timedelta(hours=72),
                status="open",
                trace_id=generate_trace_id(),
            )
            db.add(ticket)
            await db.flush()
            tickets_created.append({
                "ticket_id": str(ticket.id),
                "pbc_item_id": item["id"],
                "pbc_item_name": item["item_name"],
            })

            # 通知机制接入（通知渠道待接入）
            await self._notify_overdue(db, project_id, owner_id, item, ticket)

        return tickets_created

    async def _notify_overdue(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        pbc_item: dict,
        ticket,
    ) -> None:
        """PBC 逾期通知（通知渠道待接入）

        当前仅写入系统通知表，后续可扩展钉钉/微信/邮件等渠道。
        """
        try:
            from app.services.notification_service import NotificationService
            notif_svc = NotificationService(db)
            await notif_svc.send_notification(
                user_id=owner_id,
                notification_type="pbc_overdue",
                title=f"PBC 逾期催收: {pbc_item['item_name']}",
                content=f"PBC 项「{pbc_item['item_name']}」已逾期未收，已自动创建问题单。",
                metadata={
                    "object_type": "issue_ticket",
                    "object_id": str(ticket.id),
                    "project_id": str(project_id),
                    "pbc_item_id": pbc_item["id"],
                },
            )
        except Exception as e:
            # 通知失败不阻断主流程
            logger.warning("[PBC_OVERDUE] notification failed (non-blocking): %s", e)

    def _to_dict(self, item: PBCChecklist) -> dict:
        return {
            "id": str(item.id),
            "project_id": str(item.project_id),
            "item_name": item.item_name,
            "item_description": item.item_description,
            "category": item.category,
            "wp_id": str(item.wp_id) if item.wp_id else None,
            "cycle_code": item.cycle_code,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "status": item.status.value if hasattr(item.status, 'value') else item.status,
            "requested_date": item.requested_date.isoformat() if item.requested_date else None,
            "received_date": item.received_date.isoformat() if item.received_date else None,
            "requested_by": str(item.requested_by) if item.requested_by else None,
            "received_by": str(item.received_by) if item.received_by else None,
            "notes": item.notes,
            "is_deleted": item.is_deleted,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }


pbc_service = PbcService()
