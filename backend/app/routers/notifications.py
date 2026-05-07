"""通知 API — 用户通知的 CRUD 端点

GET  /api/notifications              — 获取当前用户通知列表
GET  /api/notifications/unread-count — 获取未读数量
POST /api/notifications/{id}/read    — 标记单条已读
POST /api/notifications/read-all     — 全部标为已读
DELETE /api/notifications/{id}       — 删除单条通知
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Notification, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的通知列表"""
    stmt = (
        select(Notification)
        .where(Notification.recipient_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)  # noqa: E712

    result = await db.execute(stmt)
    notifications = result.scalars().all()

    items = [
        {
            "id": str(n.id),
            "notification_type": n.message_type,
            "title": n.title,
            "content": n.content,
            "related_object_type": n.related_object_type,
            "related_object_id": str(n.related_object_id) if n.related_object_id else None,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]
    return {"items": items, "total": len(items)}


@router.get("/unread-count")
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户未读通知数量"""
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.recipient_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    result = await db.execute(stmt)
    count = result.scalar() or 0
    return {"count": count}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记单条通知为已读"""
    stmt = (
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.recipient_id == current_user.id,
        )
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    await db.execute(stmt)
    await db.commit()
    return {"success": True}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将当前用户所有未读通知标为已读"""
    stmt = (
        update(Notification)
        .where(
            Notification.recipient_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    await db.execute(stmt)
    await db.commit()
    return {"success": True}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除单条通知"""
    from sqlalchemy import delete as sql_delete

    stmt = sql_delete(Notification).where(
        Notification.id == notification_id,
        Notification.recipient_id == current_user.id,
    )
    await db.execute(stmt)
    await db.commit()
    return {"success": True}
