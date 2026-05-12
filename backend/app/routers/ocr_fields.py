"""OCR 字段提取 API 路由 — Round 4 需求 12

- POST /api/attachments/{id}/ocr-fields  — 获取或触发 OCR 字段提取
- GET  /api/ocr-jobs/{job_id}            — 查询异步 OCR 任务状态

Validates: Requirements 12.1, 12.2, 12.5
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.ocr_fields_service import OcrFieldsService

router = APIRouter(tags=["OCR字段提取"])


@router.post("/api/attachments/{attachment_id}/ocr-fields")
async def extract_ocr_fields(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取或触发 OCR 字段提取。

    - 若 ocr_status='completed' 且有缓存，直接返回 200 + fields
    - 若未完成，触发异步 OCR，返回 202 + job_id
    - 同一附件多次调用复用缓存结果（幂等）
    """
    svc = OcrFieldsService(db)
    body, status_code = await svc.get_or_trigger_ocr_fields(attachment_id)

    if status_code == 404:
        raise HTTPException(status_code=404, detail=body.get("detail", "附件不存在"))

    if status_code == 202:
        await db.commit()
        return JSONResponse(content=body, status_code=202)

    # 200 — 缓存命中或即时提取完成
    await db.commit()
    return body


@router.get("/api/ocr-jobs/{job_id}")
async def get_ocr_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询异步 OCR 任务状态（前端轮询用）"""
    svc = OcrFieldsService(db)
    status = await svc.get_job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return status
