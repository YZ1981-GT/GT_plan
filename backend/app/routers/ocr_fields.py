"""OCR 字段提取 API 路由 — Round 4 需求 12

- POST /api/attachments/{id}/ocr-fields  — 获取或触发 OCR 字段提取
- GET  /api/ocr-jobs/{job_id}            — 查询异步 OCR 任务状态

Validates: Requirements 12.1, 12.2, 12.5
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user
from app.models.attachment_models import Attachment
from app.models.core import User
from app.services.attachment_access import load_attachment
from app.services.ocr_fields_service import OcrFieldsService
from app.services.wp_visibility.entry_integration import (
    enforce_attachment_wp_visibility,
)

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

    权限（spec attachment-security-baseline 需求 2.3）：按附件所属项目判 —— 只读缓存要求 readonly，
    会写库（补提取字段 / 触发识别）要求 edit。原先只校验登录与底稿可见性，未关联底稿的附件任何登录用户都能触发识别。
    """
    att = await load_attachment(db, attachment_id)
    cached = att.ocr_status == "completed" and bool(att.ocr_fields_cache)
    await assert_project_permission(db, current_user, att.project_id, "readonly" if cached else "edit")
    # Wp_Bound_Gate 附件可见性隔离（Task 4 / R3 leak_risk → gated，additive）：
    # 附件绑定底稿时要求当前用户对至少一个关联底稿可见，全部不可见 → 404；未绑定 → 放行。
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )
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
    """查询异步 OCR 任务状态（前端轮询用）；要求任务所属附件的项目 readonly（结果里有识别出的字段）。"""
    svc = OcrFieldsService(db)
    status = await svc.get_job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        attachment_id = UUID(str(status.get("attachment_id")))
    except ValueError:
        raise HTTPException(status_code=404, detail="任务不存在")
    project_id = (await db.execute(
        sa.select(Attachment.project_id).where(Attachment.id == attachment_id)
    )).scalar_one_or_none()
    if project_id is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    await assert_project_permission(db, current_user, project_id, "readonly")
    return status
