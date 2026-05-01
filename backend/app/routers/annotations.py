"""单元格批注 API — Phase 10 Task 15.1"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.phase10_schemas import (
    CreateAnnotationRequest,
    UpdateAnnotationRequest,
)
from app.services.annotation_service import AnnotationService

router = APIRouter(prefix="/api/projects", tags=["annotations"])

_svc = AnnotationService()


@router.post("/{project_id}/annotations")
async def create_annotation(
    project_id: UUID,
    req: CreateAnnotationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    author_id = current_user.id
    result = await _svc.create_annotation(
        db, project_id, author_id,
        req.object_type, req.object_id, req.content,
        req.cell_ref, req.priority, req.mentioned_user_ids,
    )
    await db.commit()

    # 发布SSE通知（质控意见/复核意见创建）
    try:
        from app.services.event_bus import event_bus
        await event_bus.publish({
            "type": "ANNOTATION_CREATED",
            "project_id": str(project_id),
            "annotation_id": str(result.get("id", "")),
            "object_type": req.object_type,
            "object_id": str(req.object_id) if req.object_id else None,
            "author_id": str(author_id),
            "priority": req.priority,
            "preview": req.content[:80] if req.content else "",
        })
    except Exception:
        pass

    return result


@router.get("/{project_id}/annotations")
async def list_annotations(
    project_id: UUID,
    object_type: str | None = None,
    object_id: UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
current_user: User = Depends(get_current_user),
):
    return await _svc.list_annotations(
        db, project_id, object_type, object_id, status, priority, limit,
    )


@router.put("/annotations/{annotation_id}")
async def update_annotation(
    annotation_id: UUID,
    req: UpdateAnnotationRequest,
    db: AsyncSession = Depends(get_db),
current_user: User = Depends(get_current_user),
):
    try:
        result = await _svc.update_annotation(db, annotation_id, req.status, req.content)
        await db.commit()

        # 发布SSE通知（意见回复/解决）
        try:
            from app.services.event_bus import event_bus
            await event_bus.publish({
                "type": "ANNOTATION_UPDATED",
                "annotation_id": str(annotation_id),
                "new_status": req.status,
                "reply_content": req.content[:80] if req.content else None,
            })
        except Exception:
            pass

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/annotations/{annotation_id}/link-conversation")
async def link_to_conversation(
    annotation_id: UUID,
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
current_user: User = Depends(get_current_user),
):
    try:
        result = await _svc.link_to_conversation(db, annotation_id, conversation_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
