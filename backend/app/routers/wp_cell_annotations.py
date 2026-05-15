"""底稿单元格批注路由 — POST 创建 / PATCH 回复 / PATCH 解决 / GET 列表

Sprint 10 Task 10.2
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.wp_cell_annotation_service import CellAnnotationService

router = APIRouter(prefix="/api/workpapers/{wp_id}/annotations", tags=["cell-annotations"])


class AnnotationCreate(BaseModel):
    sheet_name: str
    row_idx: int
    col_idx: int
    content: str
    project_id: uuid.UUID


class AnnotationReply(BaseModel):
    reply_content: str


class AnnotationOut(BaseModel):
    id: uuid.UUID
    cell_ref: Optional[str] = None
    content: str
    status: str
    author_id: uuid.UUID
    mentioned_user_ids: Optional[dict] = None
    created_at: str

    model_config = {"from_attributes": True}


@router.post("", response_model=AnnotationOut, status_code=201)
async def create_annotation(
    wp_id: uuid.UUID,
    body: AnnotationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ann = await CellAnnotationService.create(
        db,
        wp_id=wp_id,
        sheet_name=body.sheet_name,
        row_idx=body.row_idx,
        col_idx=body.col_idx,
        content=body.content,
        author_id=current_user.id,
        project_id=body.project_id,
    )
    await db.commit()
    return _to_out(ann)


@router.patch("/{annotation_id}/reply", response_model=AnnotationOut)
async def reply_annotation(
    wp_id: uuid.UUID,
    annotation_id: uuid.UUID,
    body: AnnotationReply,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ann = await CellAnnotationService.reply(
        db, annotation_id=annotation_id, reply_content=body.reply_content, replied_by=current_user.id
    )
    if not ann:
        raise HTTPException(404, "Annotation not found")
    await db.commit()
    return _to_out(ann)


@router.patch("/{annotation_id}/resolve", response_model=AnnotationOut)
async def resolve_annotation(
    wp_id: uuid.UUID,
    annotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ann = await CellAnnotationService.resolve(db, annotation_id=annotation_id, resolved_by=current_user.id)
    if not ann:
        raise HTTPException(404, "Annotation not found")
    await db.commit()
    return _to_out(ann)


@router.get("", response_model=list[AnnotationOut])
async def list_annotations(
    wp_id: uuid.UUID,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = await CellAnnotationService.list_by_wp(db, wp_id=wp_id, status=status)
    return [_to_out(a) for a in items]


def _to_out(ann) -> AnnotationOut:
    return AnnotationOut(
        id=ann.id,
        cell_ref=ann.cell_ref,
        content=ann.content,
        status=ann.status,
        author_id=ann.author_id,
        mentioned_user_ids=ann.mentioned_user_ids,
        created_at=ann.created_at.isoformat() if ann.created_at else "",
    )
