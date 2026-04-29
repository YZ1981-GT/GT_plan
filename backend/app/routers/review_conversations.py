"""复核对话 API — Phase 10 Task 8.1-8.4"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.phase10_schemas import (
    CreateConversationRequest,
    SendMessageRequest,
    ConversationResponse,
    MessageResponse,
)
from app.services.review_conversation_service import ReviewConversationService

router = APIRouter(prefix="/api/review-conversations", tags=["review-conversations"])

_svc = ReviewConversationService()


@router.post("")
async def create_conversation(
    project_id: UUID,
    req: CreateConversationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建复核对话"""
    initiator_id = current_user.id
    result = await _svc.create_conversation(
        db, project_id, initiator_id, req.target_id,
        req.related_object_type, req.related_object_id,
        req.cell_ref, req.title,
    )
    await db.commit()
    return result


@router.get("")
async def list_conversations(
    project_id: UUID,
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出项目的复核对话"""
    return await _svc.list_conversations(db, project_id, status, limit)


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: UUID,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取对话消息"""
    return await _svc.get_messages(db, conversation_id, limit)


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    req: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发送消息（Phase 15: 关闭态消息写入阻断）"""
    # Phase 15: 关闭态门禁检查
    try:
        from app.services.rc_enhanced_service import rc_enhanced_service
        await rc_enhanced_service.check_closed_state_guard(
            db, conversation_id, req.message_type or "text"
        )
    except HTTPException:
        raise
    except Exception:
        pass  # 服务不可用时降级放行

    sender_id = current_user.id
    result = await _svc.send_message(
        db, conversation_id, sender_id,
        req.content, req.message_type, req.attachment_path, req.finding_id,
    )
    await db.commit()
    return result


@router.put("/{conversation_id}/close")
async def close_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """关闭对话（仅发起人可关闭）"""
    user_id = current_user.id
    try:
        result = await _svc.close_conversation(db, conversation_id, user_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{conversation_id}/export")
async def export_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出对话记录"""
    try:
        return await _svc.export_conversation(db, conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
