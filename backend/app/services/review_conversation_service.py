"""复核对话系统服务 — Phase 10 Task 8.1-8.4

复核对话创建/消息/关闭/导出，LLM 底稿复核。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase10_models import ReviewConversation, ReviewMessage

logger = logging.getLogger(__name__)


class ReviewConversationService:
    """复核对话服务"""

    async def create_conversation(
        self,
        db: AsyncSession,
        project_id: UUID,
        initiator_id: UUID,
        target_id: UUID,
        related_object_type: str,
        related_object_id: UUID | None,
        cell_ref: str | None,
        title: str,
    ) -> dict[str, Any]:
        """创建复核对话"""
        conv = ReviewConversation(
            project_id=project_id,
            initiator_id=initiator_id,
            target_id=target_id,
            related_object_type=related_object_type,
            related_object_id=related_object_id,
            cell_ref=cell_ref,
            title=title,
            status="open",
        )
        db.add(conv)
        await db.flush()
        logger.info("create_conversation: %s → %s, title=%s", initiator_id, target_id, title)
        return self._conv_to_dict(conv)

    async def send_message(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        sender_id: UUID,
        content: str,
        message_type: str = "text",
        attachment_path: str | None = None,
        finding_id: UUID | None = None,
    ) -> dict[str, Any]:
        """发送消息"""
        msg = ReviewMessage(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            attachment_path=attachment_path,
            finding_id=finding_id,
        )
        db.add(msg)
        await db.flush()

        # 发布 SSE 事件
        try:
            from app.services.event_bus import event_bus
            conv = await db.get(ReviewConversation, conversation_id)
            if conv:
                await event_bus.publish({
                    "type": "REVIEW_MESSAGE",
                    "project_id": str(conv.project_id),
                    "conversation_id": str(conversation_id),
                    "sender_id": str(sender_id),
                    "preview": content[:100],
                })
        except Exception:
            pass

        return self._msg_to_dict(msg)

    async def close_conversation(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """关闭对话（仅发起人可关闭）

        R6 需求 3 AC2：关闭前校验是否有未解决的 ReviewRecord 绑定到此对话，
        有则拒绝并返回 CONVERSATION_HAS_OPEN_RECORDS。
        """
        conv = await db.get(ReviewConversation, conversation_id)
        if not conv:
            raise ValueError("对话不存在")
        if conv.initiator_id != user_id:
            raise PermissionError("仅发起人可关闭对话")

        # R6: 校验是否有未解决的 ReviewRecord 绑定到此对话
        from app.models.workpaper_models import ReviewCommentStatus, ReviewRecord

        open_count_stmt = (
            sa.select(sa.func.count())
            .select_from(ReviewRecord)
            .where(
                ReviewRecord.conversation_id == conversation_id,
                ReviewRecord.status != ReviewCommentStatus.resolved,
                ReviewRecord.is_deleted == sa.false(),
            )
        )
        open_count_result = await db.execute(open_count_stmt)
        open_count = open_count_result.scalar() or 0

        if open_count > 0:
            return {
                "error_code": "CONVERSATION_HAS_OPEN_RECORDS",
                "message": f"对话下有 {open_count} 条未解决的复核批注，无法关闭",
                "open_record_count": open_count,
            }

        conv.status = "closed"
        conv.closed_at = datetime.now(timezone.utc)
        await db.flush()
        return self._conv_to_dict(conv)

    async def list_conversations(
        self,
        db: AsyncSession,
        project_id: UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """列出项目的复核对话"""
        conditions = [
            ReviewConversation.project_id == project_id,
            ReviewConversation.is_deleted == sa.false(),
        ]
        if status:
            conditions.append(ReviewConversation.status == status)

        stmt = (
            sa.select(ReviewConversation)
            .where(*conditions)
            .order_by(ReviewConversation.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        convs = result.scalars().all()

        items = []
        for c in convs:
            d = self._conv_to_dict(c)
            # 统计消息数
            count_stmt = (
                sa.select(sa.func.count())
                .select_from(ReviewMessage)
                .where(ReviewMessage.conversation_id == c.id)
            )
            count_result = await db.execute(count_stmt)
            d["message_count"] = count_result.scalar() or 0
            items.append(d)
        return items

    async def get_messages(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """获取对话消息"""
        stmt = (
            sa.select(ReviewMessage)
            .where(ReviewMessage.conversation_id == conversation_id)
            .order_by(ReviewMessage.created_at.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        msgs = result.scalars().all()
        return [self._msg_to_dict(m) for m in msgs]

    async def export_conversation(
        self,
        db: AsyncSession,
        conversation_id: UUID,
    ) -> dict[str, Any]:
        """导出对话记录为结构化数据（供 Word 导出）"""
        conv = await db.get(ReviewConversation, conversation_id)
        if not conv:
            raise ValueError("对话不存在")
        messages = await self.get_messages(db, conversation_id, limit=1000)
        return {
            "title": conv.title,
            "status": conv.status,
            "initiator_id": str(conv.initiator_id),
            "target_id": str(conv.target_id),
            "related_object_type": conv.related_object_type,
            "cell_ref": conv.cell_ref,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "closed_at": conv.closed_at.isoformat() if conv.closed_at else None,
            "messages": messages,
        }

    def _conv_to_dict(self, c: ReviewConversation) -> dict[str, Any]:
        return {
            "id": str(c.id),
            "project_id": str(c.project_id),
            "initiator_id": str(c.initiator_id),
            "target_id": str(c.target_id),
            "related_object_type": c.related_object_type,
            "related_object_id": str(c.related_object_id) if c.related_object_id else None,
            "cell_ref": c.cell_ref,
            "status": c.status,
            "title": c.title,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "closed_at": c.closed_at.isoformat() if c.closed_at else None,
        }

    def _msg_to_dict(self, m: ReviewMessage) -> dict[str, Any]:
        return {
            "id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "sender_id": str(m.sender_id),
            "content": m.content,
            "message_type": m.message_type,
            "attachment_path": m.attachment_path,
            "finding_id": str(m.finding_id) if m.finding_id else None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
