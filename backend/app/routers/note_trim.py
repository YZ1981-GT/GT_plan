"""附注章节裁剪 API

Phase 9 Task 9.27
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.note_trim_service import NoteTrimService

router = APIRouter(prefix="/api/disclosure-notes", tags=["note-trim"])


class NoteTrimItem(BaseModel):
    id: str
    status: str
    skip_reason: str | None = None


class NoteTrimRequest(BaseModel):
    items: list[NoteTrimItem]


@router.get("/{project_id}/sections")
async def get_sections(
    project_id: UUID,
    template_type: str = Query("soe"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteTrimService(db)
    return await svc.get_sections(project_id, template_type)


@router.put("/{project_id}/sections/trim")
async def save_trim(
    project_id: UUID,
    data: NoteTrimRequest,
    template_type: str = Query("soe"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteTrimService(db)
    count = await svc.save_trim(project_id, template_type, [i.model_dump() for i in data.items])
    await db.commit()
    return {"updated": count}


@router.get("/{project_id}/sections/trim-scheme")
async def get_trim_scheme(
    project_id: UUID,
    template_type: str = Query("soe"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteTrimService(db)
    return await svc.get_trim_scheme(project_id, template_type) or {}
