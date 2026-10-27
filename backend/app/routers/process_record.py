"""过程记录与人机协同标注 API — Phase 10 Task 4.1-4.3"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
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


# ── 底稿编辑记录 ──────────────────────────────────────────

@router.get("/projects/{project_id}/workpapers/{wp_id}/edit-history")
async def get_edit_history(
    project_id: UUID,
    wp_id: UUID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
):
    """记录底稿编辑"""
    svc = ProcessRecordService()
    user_id = current_user.id
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
current_user: User = Depends(get_current_user),
):
    """获取底稿关联的附件"""
    svc = AttachmentLinkService()
    return await svc.get_workpaper_attachments(db, project_id, wp_id)


@router.get("/attachments/{attachment_id}/workpapers")
async def get_attachment_workpapers(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
current_user: User = Depends(get_current_user),
):
    """获取附件出现的底稿（侧栏「关联底稿数」悬停时取）。

    先按附件真实所属项目判 readonly（原先只要登录，未绑定底稿的附件对任何登录用户放行，
    spec attachment-evidence-intake 需求 4.3）；再过附件 wp-link 可见性隔离（全部关联底稿都不可见 → 404）；
    清单只列当前用户看得到的底稿（编码 / 名称不向不可见的人泄露，与底稿搜索同口径）。
    """
    from app.services.attachment_access import require_attachment_permission
    from app.services.wp_visibility.entry_integration import (
        enforce_attachment_wp_visibility,
        try_gate_wp,
    )

    await require_attachment_permission(db, current_user, attachment_id, "readonly")
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )
    svc = AttachmentLinkService()
    visible = []
    for wp in await svc.get_attachment_workpapers(db, attachment_id):
        ctx = await try_gate_wp(
            db, current_user, entrypoint="attachment.read", action="attach_read", method="GET",
            wp_id=UUID(wp["wp_id"]), entry_family="attachment",
        )
        if ctx is not None:
            visible.append(wp)
    return visible


# POST /link-attachment 已删除（spec attachment-evidence-intake 需求 4.4）：只要登录就能把任意附件挂到任意底稿
# （不校项目、不过统一门），前端零调用方。关联已有附件走 POST /api/attachments/{id}/associate，上传新证据走
# POST /api/projects/{pid}/workpapers/{wp_id}/evidence/upload。


# ── AI 内容人机协同标注 ───────────────────────────────────

@router.get("/projects/{project_id}/ai-content/pending")
async def get_pending_ai_content(
    project_id: UUID,
    workpaper_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
current_user: User = Depends(get_current_user),
):
    """获取待确认的 AI 内容"""
    svc = AIContentTagService()
    return await svc.get_pending_ai_content(db, project_id, workpaper_id)


@router.put("/ai-content/{content_id}/confirm")
async def confirm_ai_content(
    content_id: UUID,
    req: ConfirmAIContentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """确认/拒绝 AI 内容"""
    svc = AIContentTagService()
    user_id = current_user.id
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
current_user: User = Depends(get_current_user),
):
    """检查底稿是否有未确认的 AI 内容（提交复核前检查）"""
    svc = AIContentTagService()
    return await svc.check_unconfirmed(db, project_id, wp_id)
