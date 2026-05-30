"""原始凭证 LLM 识别路由 — wp-evidence-collection spec Task 3

端点：
  POST /projects/{project_id}/document-recognize  批量识别
  GET  /projects/{project_id}/document-recognize/types  获取支持类型
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.wp_document_recognizer import wp_document_recognizer

router = APIRouter(
    prefix="/projects/{project_id}/document-recognize",
    tags=["原始凭证识别"],
)


class AttachmentItem(BaseModel):
    attachment_id: str
    doc_type: str = "voucher"


class RecognizeRequest(BaseModel):
    attachments: list[AttachmentItem]


@router.post("")
async def recognize_documents(
    project_id: str,
    body: RecognizeRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """批量识别原始凭证（LLM 结构化提取）"""
    result = await wp_document_recognizer.recognize_batch(
        db,
        attachments=[a.model_dump() for a in body.attachments],
        project_id=uuid.UUID(project_id),
        user_id=user.id,
    )
    await db.commit()
    return result


@router.get("/types")
async def get_doc_types(
    project_id: str,
    user=Depends(get_current_user),
):
    """获取支持的凭证类型列表"""
    return wp_document_recognizer.get_supported_doc_types()
