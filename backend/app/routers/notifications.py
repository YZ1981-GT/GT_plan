"""通知 API 路由 — /api/v1/notifications

接口：
  GET  /api/v1/notifications             — 通知列表（分页+筛选）
  PATCH /api/v1/notifications/{id}/read — 标记单条已读
  POST /api/v1/notifications/read-all   — 全部已读
  GET  /api/v1/notifications/unread-count — 未读数量（Redis缓存）

Validates: Requirements 6.5, 6.6
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.models.collaboration_schemas import NotificationFilter, NotificationResponse
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    count: int


class MarkReadResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    page: int = Query(1, ge=1, description="页码（从1开始）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    unread_only: bool = Query(False, description="仅返回未读"),
    type_filter: Optional[str] = Query(None, description="按通知类型筛选"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    获取当前用户的通知列表，支持分页和筛选。
    """
    notifications, total = NotificationService.get_notifications(
        db,
        user_id=str(user.id),
        page=page,
        page_size=page_size,
        unread_only=unread_only,
        type_filter=type_filter,
    )
    return NotificationListResponse(
        items=[
            NotificationResponse(
                id=str(n.id),
                notification_type=n.notification_type,
                title=n.title,
                content=n.content,
                related_object_type=n.related_object_type,
                related_object_id=str(n.related_object_id) if n.related_object_id else None,
                is_read=n.is_read,
                created_at=n.created_at,
            )
            for n in notifications
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{notification_id}/read", response_model=MarkReadResponse)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    标记指定通知为已读。
    仅允许标记属于当前用户的通知。
    """
    notif = NotificationService.mark_read(db, notification_id, str(user.id))
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    return MarkReadResponse(message="marked as read")


@router.post("/read-all", response_model=MarkReadResponse)
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    标记当前用户所有未读通知为已读。
    返回实际更新的通知数量。
    """
    count = NotificationService.mark_all_read(db, str(user.id))
    return MarkReadResponse(message=f"{count} notifications marked as read")


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    获取当前用户未读通知数量。
    结果使用 Redis 缓存（30秒TTL），以提升轮询性能。
    """
    count = NotificationService.get_unread_count(db, str(user.id))
    return UnreadCountResponse(count=count)


# ---------------------------------------------------------------------------
# Internal helper — 供其他服务快捷创建通知
# ---------------------------------------------------------------------------


def notify(
    db: Session,
    recipient_id: str,
    notif_type: str,
    title: str,
    content: Optional[str] = None,
    related_object_type: Optional[str] = None,
    related_object_id: Optional[str] = None,
) -> NotificationService:
    """快捷创建通知（内部使用）"""
    return NotificationService.create_notification(
        db,
        recipient_id=recipient_id,
        notification_type=notif_type,
        title=title,
        message=content,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
    )

