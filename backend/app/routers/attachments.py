"""附件管理 API 路由

- POST   /api/projects/{id}/attachments          — 创建附件
- GET    /api/projects/{id}/attachments          — 附件列表
- GET    /api/attachments/{id}                   — 附件详情
- POST   /api/attachments/{id}/associate         — 关联到底稿
- GET    /api/attachments/search                 — 全文搜索
- GET    /api/working-papers/{wp_id}/attachments — 底稿关联附件

Validates: Requirements 14.2, 14.5, 14.8
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.attachment_service import AttachmentService

router = APIRouter(tags=["attachments"])


class AttachmentCreate(BaseModel):
    file_name: str
    file_path: str
    file_type: str = "unknown"
    file_size: int = 0
    paperless_document_id: int | None = None


class AssociateRequest(BaseModel):
    wp_id: UUID
    association_type: str = "evidence"
    notes: str | None = None


def _svc(db: AsyncSession) -> AttachmentService:
    return AttachmentService(db)


@router.post("/api/projects/{project_id}/attachments")
async def create_attachment(
    project_id: UUID, body: AttachmentCreate, db: AsyncSession = Depends(get_db),
):
    svc = _svc(db)
    result = await svc.create_attachment(project_id, body.model_dump())
    await db.commit()
    return result


@router.get("/api/projects/{project_id}/attachments")
async def list_attachments(
    project_id: UUID,
    file_type: str | None = None,
    ocr_status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    svc = _svc(db)
    return await svc.list_attachments(project_id, file_type, ocr_status)


@router.get("/api/attachments/search")
async def search_attachments(
    project_id: UUID = Query(...),
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    svc = _svc(db)
    return await svc.search(project_id, q)


@router.get("/api/attachments/{attachment_id}")
async def get_attachment(attachment_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = _svc(db)
    result = await svc.get_attachment(attachment_id)
    if not result:
        raise HTTPException(status_code=404, detail="附件不存在")
    return result


@router.post("/api/attachments/{attachment_id}/associate")
async def associate_with_wp(
    attachment_id: UUID, body: AssociateRequest, db: AsyncSession = Depends(get_db),
):
    svc = _svc(db)
    result = await svc.associate_with_wp(attachment_id, body.wp_id, body.association_type, body.notes)
    await db.commit()
    return result


@router.get("/api/working-papers/{wp_id}/attachments")
async def get_wp_attachments(wp_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = _svc(db)
    return await svc.get_wp_attachments(wp_id)


@router.post("/api/attachments/{attachment_id}/classify")
async def classify_document(attachment_id: UUID, db: AsyncSession = Depends(get_db)):
    """自动分类文档"""
    svc = _svc(db)
    try:
        return await svc.classify_document(attachment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/attachments/{attachment_id}/extract-confirmation")
async def extract_confirmation_reply(attachment_id: UUID, db: AsyncSession = Depends(get_db)):
    """函证回函 OCR 识别"""
    svc = _svc(db)
    try:
        return await svc.extract_confirmation_reply(attachment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
