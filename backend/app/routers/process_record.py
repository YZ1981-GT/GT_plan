"""过程记录与人机协同标注 API — Phase 10 Task 4.1-4.3"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.process_record_service import (
    AttachmentLinkService,
    AIContentTagService,
    ProcessRecordService,
)

router = APIRouter(prefix="/api/process-record", tags=["process-record"])


# ── Schemas ───────────────────────────────────────────────

class RecordEditRequest(BaseModel):
    wp_id: str
    file_version: int
    change_summary: str | None = None


class ConfirmAIContentRequest(BaseModel):
    status: str  # accepted / modified / rejected


class LinkAttachmentRequest(BaseModel):
    attachment_id: str
    wp_id: str


# ── 底稿编辑记录 ──────────────────────────────────────────

@router.get("/projects/{project_id}/workpapers/{wp_id}/edit-history")
async def get_edit_history(
    project_id: UUID,
    wp_id: UUID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """获取底稿编辑历史"""
    svc = ProcessRecordService()
    return await svc.get_edit_history(db, project_id, wp_id, limit)


@router.post("/projects/{project_id}/workpapers/{wp_id}/record-edit")
async def record_edit(
    project_id: UUID,
    wp_id: UUID,
    req: RecordEditRequest,
    db: AsyncSession = Depends(get_db),
):
    """记录底稿编辑"""
    svc = ProcessRecordService()
    # 使用一个占位 user_id（实际应从 JWT 获取）
    user_id = UUID("00000000-0000-0000-0000-000000000000")
    result = await svc.record_workpaper_edit(
        db, project_id, wp_id, user_id, req.file_version, req.change_summary
    )
    await db.commit()
    return result


# ── 附件双向关联 ──────────────────────────────────────────

@router.get("/projects/{project_id}/workpapers/{wp_id}/attachments")
async def get_workpaper_attachments(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取底稿关联的附件"""
    svc = AttachmentLinkService()
    return await svc.get_workpaper_attachments(db, project_id, wp_id)


@router.get("/attachments/{attachment_id}/workpapers")
async def get_attachment_workpapers(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取附件关联的底稿"""
    svc = AttachmentLinkService()
    return await svc.get_attachment_workpapers(db, attachment_id)


@router.post("/link-attachment")
async def link_attachment(
    req: LinkAttachmentRequest,
    db: AsyncSession = Depends(get_db),
):
    """将附件关联到底稿"""
    svc = AttachmentLinkService()
    await svc.link_attachment_to_workpaper(
        db, UUID(req.attachment_id), UUID(req.wp_id)
    )
    await db.commit()
    return {"linked": True}


# ── AI 内容人机协同标注 ───────────────────────────────────

@router.get("/projects/{project_id}/ai-content/pending")
async def get_pending_ai_content(
    project_id: UUID,
    workpaper_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取待确认的 AI 内容"""
    svc = AIContentTagService()
    return await svc.get_pending_ai_content(db, project_id, workpaper_id)


@router.put("/ai-content/{content_id}/confirm")
async def confirm_ai_content(
    content_id: UUID,
    req: ConfirmAIContentRequest,
    db: AsyncSession = Depends(get_db),
):
    """确认/拒绝 AI 内容"""
    svc = AIContentTagService()
    user_id = UUID("00000000-0000-0000-0000-000000000000")
    try:
        result = await svc.confirm_ai_content(db, content_id, req.status, user_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/workpapers/{wp_id}/ai-check")
async def check_unconfirmed_ai(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """检查底稿是否有未确认的 AI 内容（提交复核前检查）"""
    svc = AIContentTagService()
    return await svc.check_unconfirmed(db, project_id, wp_id)
