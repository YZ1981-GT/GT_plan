"""AI 内容溯源 API — V3 收官增强 Req 6.5

提供轻量级 AI 内容生命周期端点供前端调用：

- GET  /api/projects/{pid}/ai-content/pending      列出待确认 AI 内容 + 计数
- POST /api/ai-content/{log_id}/confirm            确认 AI 内容
- POST /api/ai-content/{log_id}/revise             修订 AI 内容
- POST /api/ai-content/{log_id}/reject             拒绝 AI 内容

底层调用 ai_content_log_service（6.1 已就位）。
注意：与 process_record.py 中 /api/process-record/projects/{pid}/ai-content/pending 端点
（基于旧 AIContentTagService 的 v1 实现）不冲突，路径前缀不同。

Validates: Requirements 6.5
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services import ai_content_log_service

router = APIRouter(tags=["AI 内容溯源"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ReviseRequest(BaseModel):
    revised_content: str

    @field_validator("revised_content")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("修订内容不能为空")
        return v


def _serialize(log) -> dict:
    """将 AiContentLog ORM 对象序列化为 banner / badge 所需的字典。"""
    target_cell = log.target_cell or ""
    instance_type = target_cell.split(":", 1)[0] if target_cell else None
    return {
        "id": str(log.id),
        "ai_content_log_id": str(log.id),
        "instance_type": instance_type,
        "target_cell": log.target_cell,
        "model": log.model,
        "confidence": float(log.confidence) if log.confidence is not None else None,
        "generated_at": log.generated_at.isoformat() if log.generated_at else None,
        "content": log.generated_content,
        "confirm_action": log.confirm_action,
    }


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/ai-content/pending
# ---------------------------------------------------------------------------


@router.get("/api/projects/{project_id}/ai-content/pending")
async def list_pending_ai_content(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """返回项目下未确认的 AI 内容清单 + 总数（前端 banner / badge 用）。"""
    items = await ai_content_log_service.list_pending_by_project(
        db=db, project_id=project_id, limit=limit
    )
    count = await ai_content_log_service.count_pending_by_project(
        db=db, project_id=project_id
    )
    return {
        "count": count,
        "items": [_serialize(it) for it in items],
    }


# ---------------------------------------------------------------------------
# POST /api/ai-content/{log_id}/confirm
# ---------------------------------------------------------------------------


@router.post("/api/ai-content/{log_id}/confirm")
async def confirm_ai_content(
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """确认 AI 内容（confirm_action=confirmed）。"""
    try:
        log = await ai_content_log_service.confirm(
            db=db, log_id=log_id, user_id=user.id
        )
        await db.commit()
        return {"id": str(log.id), "confirm_action": log.confirm_action}
    except ai_content_log_service.AiContentLogNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/ai-content/{log_id}/revise
# ---------------------------------------------------------------------------


@router.post("/api/ai-content/{log_id}/revise")
async def revise_ai_content(
    log_id: UUID,
    payload: ReviseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """修订 AI 内容（confirm_action=revised + 写 revised_content）。"""
    try:
        log = await ai_content_log_service.revise(
            db=db,
            log_id=log_id,
            user_id=user.id,
            revised_content=payload.revised_content,
        )
        await db.commit()
        return {"id": str(log.id), "confirm_action": log.confirm_action}
    except ai_content_log_service.AiContentLogNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/ai-content/{log_id}/reject
# ---------------------------------------------------------------------------


@router.post("/api/ai-content/{log_id}/reject")
async def reject_ai_content(
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """拒绝 AI 内容（confirm_action=rejected）。"""
    try:
        log = await ai_content_log_service.reject(
            db=db, log_id=log_id, user_id=user.id
        )
        await db.commit()
        return {"id": str(log.id), "confirm_action": log.confirm_action}
    except ai_content_log_service.AiContentLogNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
