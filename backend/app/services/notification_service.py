"""通知服务 — NotificationService

提供 send_notification 方法，写入 notifications 表。
被 issue_ticket_service / archive_orchestrator 等调用。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """系统通知服务

    支持两种使用方式：
    1. 无 db 实例化：NotificationService()，调用时传 db 参数
    2. 有 db 实例化：NotificationService(db)，调用时不传 db
    """

    def __init__(self, db: AsyncSession | None = None):
        self._db = db

    async def send_notification(
        self,
        user_id: uuid.UUID | str,
        notification_type: str,
        title: str,
        content: str = "",
        metadata: dict[str, Any] | None = None,
        db: AsyncSession | None = None,
    ) -> dict[str, Any] | None:
        """发送通知给指定用户。

        Args:
            user_id: 接收者 ID
            notification_type: 通知类型（对应 notification_types.py 常量）
            title: 通知标题
            content: 通知正文
            metadata: 附加元数据（如 project_id, job_id 等）
            db: 数据库会话（可选，优先使用实例化时传入的 db）

        Returns:
            通知字典，失败返回 None
        """
        session = db or self._db
        if session is None:
            logger.error("[NOTIFICATION] no db session available")
            return None

        try:
            if isinstance(user_id, str):
                user_id = uuid.UUID(user_id)

            notification = Notification(
                id=uuid.uuid4(),
                recipient_id=user_id,
                message_type=notification_type,
                title=title,
                content=content,
                related_object_type=metadata.get("object_type") if metadata else None,
                related_object_id=(
                    uuid.UUID(metadata["object_id"])
                    if metadata and "object_id" in metadata
                    else None
                ),
                is_read=False,
            )
            session.add(notification)
            await session.flush()

            logger.info(
                "[NOTIFICATION] sent: type=%s user=%s title=%s",
                notification_type,
                user_id,
                title,
            )
            return {
                "id": str(notification.id),
                "recipient_id": str(notification.recipient_id),
                "message_type": notification.message_type,
                "title": notification.title,
                "content": notification.content,
            }
        except Exception as exc:
            logger.warning(
                "[NOTIFICATION] send_notification failed (non-blocking): %s", exc
            )
            return None

    async def send_notification_to_many(
        self,
        user_ids: list[uuid.UUID | str],
        notification_type: str,
        title: str,
        content: str = "",
        metadata: dict[str, Any] | None = None,
        db: AsyncSession | None = None,
    ) -> int:
        """批量发送通知给多个用户。

        Returns:
            成功发送的通知数量
        """
        sent_count = 0
        for uid in user_ids:
            result = await self.send_notification(
                user_id=uid,
                notification_type=notification_type,
                title=title,
                content=content,
                metadata=metadata,
                db=db,
            )
            if result:
                sent_count += 1
        return sent_count
