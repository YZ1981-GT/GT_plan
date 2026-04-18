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

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.attachment_service import AttachmentService

router = APIRouter(tags=["attachments"])


class AttachmentCreate(BaseModel):
    file_name: str
    file_path: str
    file_type: str = "unknown"
    file_size: int = 0
    paperless_document_id: int | None = None
    attachment_type: str = "general"
    reference_id: UUID | None = None
    reference_type: str | None = None
    storage_type: str | None = None


class AssociateRequest(BaseModel):
    wp_id: UUID
    association_type: str = "evidence"
    notes: str | None = None


def _svc(db: AsyncSession) -> AttachmentService:
    return AttachmentService(db)


@router.post("/api/projects/{project_id}/attachments")
async def create_attachment(
    project_id: UUID, body: AttachmentCreate, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = _svc(db)
    result = await svc.create_attachment(project_id, body.model_dump())
    await db.commit()
    return result


@router.post("/api/projects/{project_id}/attachments/upload")
async def upload_attachment(
    project_id: UUID,
    file: UploadFile = File(...),
    attachment_type: str = Form("general"),
    reference_id: UUID | None = Form(None),
    reference_type: str | None = Form(None),
    file_type: str | None = Form(None),
    title: str | None = Form(None),
    correspondent: str | None = Form(None),
    document_type: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = _svc(db)
    content = await file.read()
    result = await svc.upload_attachment_file(
        project_id=project_id,
        file_name=file.filename or "attachment.bin",
        content=content,
        metadata={
            "attachment_type": attachment_type,
            "reference_id": reference_id,
            "reference_type": reference_type,
            "file_type": file_type,
            "title": title,
            "correspondent": correspondent,
            "document_type": document_type,
        },
    )
    await db.commit()
    return result


@router.get("/api/projects/{project_id}/attachments")
async def list_attachments(
    project_id: UUID,
    file_type: str | None = None,
    ocr_status: str | None = None,
    attachment_type: str | None = None,
    reference_type: str | None = None,
    reference_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = _svc(db)
    return await svc.list_attachments(
        project_id,
        file_type,
        ocr_status,
        attachment_type,
        reference_type,
        reference_id,
    )


@router.get("/api/attachments/search")
async def search_attachments(
    project_id: UUID = Query(...),
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = _svc(db)
    return await svc.search(project_id, q)


@router.get("/api/attachments/{attachment_id}")
async def get_attachment(attachment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = _svc(db)
    result = await svc.get_attachment(attachment_id)
    if not result:
        raise HTTPException(status_code=404, detail="附件不存在")
    return result


@router.post("/api/attachments/{attachment_id}/associate")
async def associate_with_wp(
    attachment_id: UUID, body: AssociateRequest, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = _svc(db)
    result = await svc.associate_with_wp(attachment_id, body.wp_id, body.association_type, body.notes)
    await db.commit()
    return result


@router.get("/api/working-papers/{wp_id}/attachments")
async def get_wp_attachments(wp_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = _svc(db)
    return await svc.get_wp_attachments(wp_id)


class OCRStatusUpdate(BaseModel):
    status: str  # pending / processing / completed / failed
    ocr_text: str | None = None


@router.put("/api/attachments/{attachment_id}/ocr-status")
async def update_ocr_status(
    attachment_id: UUID, body: OCRStatusUpdate, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新附件 OCR 状态和文本（由 OCR 服务回调）"""
    svc = _svc(db)
    result = await svc.update_ocr_status(attachment_id, body.status, body.ocr_text)
    if not result:
        raise HTTPException(status_code=404, detail="附件不存在")
    await db.commit()
    return result


@router.post("/api/attachments/{attachment_id}/classify")
async def classify_document(attachment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """自动分类文档"""
    svc = _svc(db)
    try:
        return await svc.classify_document(attachment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/attachments/{attachment_id}/extract-confirmation")
async def extract_confirmation_reply(attachment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """函证回函 OCR 识别"""
    svc = _svc(db)
    try:
        return await svc.extract_confirmation_reply(attachment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 统一预览/下载代理（屏蔽 paperless:// 和本地路径差异）──

@router.get("/api/attachments/{attachment_id}/download")
async def download_attachment(attachment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """统一下载代理 — 屏蔽底层存储差异，记录下载审计日志"""
    from fastapi.responses import StreamingResponse, Response
    from pathlib import Path
    import httpx
    import logging

    logger = logging.getLogger(__name__)

    svc = _svc(db)
    att = await svc.get_attachment(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")

    file_path = att.get("file_path", "")
    file_name = att.get("file_name", "attachment")

    # 审计日志：记录敏感下载操作
    logger.info(
        "attachment_download: user=%s attachment_id=%s file_name=%s",
        str(current_user.id), str(attachment_id), file_name,
    )

    # Paperless 存储：通过 Paperless API 代理下载
    if file_path.startswith("paperless://"):
        doc_id = file_path.replace("paperless://", "")
        import os
        paperless_url = os.environ.get("PAPERLESS_URL", "http://localhost:8010")
        paperless_token = os.environ.get("PAPERLESS_TOKEN", "")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{paperless_url}/api/documents/{doc_id}/download/",
                    headers={"Authorization": f"Token {paperless_token}"} if paperless_token else {},
                )
                if resp.status_code == 200:
                    return Response(
                        content=resp.content,
                        media_type=resp.headers.get("content-type", "application/octet-stream"),
                        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
                    )
                raise HTTPException(status_code=resp.status_code, detail="Paperless 下载失败")
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Paperless 连接失败: {e}")

    # 本地存储：直接读取文件
    local_path = Path(file_path)
    if not local_path.exists():
        # 尝试在 storage 目录下查找
        from pathlib import Path as P
        storage_path = P("storage") / file_path.lstrip("/")
        if storage_path.exists():
            local_path = storage_path
        else:
            raise HTTPException(status_code=404, detail="文件不存在")

    return StreamingResponse(
        open(local_path, "rb"),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/api/attachments/{attachment_id}/preview")
async def preview_attachment(attachment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """统一预览代理 — 返回可预览的内容（PDF/图片直接返回，其他返回元数据）"""
    from fastapi.responses import StreamingResponse, Response
    from pathlib import Path
    import httpx

    svc = _svc(db)
    att = await svc.get_attachment(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")

    file_path = att.get("file_path", "")
    file_name = att.get("file_name", "")
    file_type = att.get("file_type", "")

    # 判断是否可直接预览
    previewable_types = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
    ext = Path(file_name).suffix.lower() if file_name else ""
    can_preview = ext in previewable_types

    if not can_preview:
        # 不可预览的文件返回元数据 + OCR 文本
        return {
            "previewable": False,
            "file_name": file_name,
            "file_type": file_type,
            "ocr_text": att.get("ocr_text", ""),
            "download_url": f"/api/attachments/{attachment_id}/download",
        }

    # Paperless 存储
    if file_path.startswith("paperless://"):
        doc_id = file_path.replace("paperless://", "")
        import os
        paperless_url = os.environ.get("PAPERLESS_URL", "http://localhost:8010")
        paperless_token = os.environ.get("PAPERLESS_TOKEN", "")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{paperless_url}/api/documents/{doc_id}/preview/",
                    headers={"Authorization": f"Token {paperless_token}"} if paperless_token else {},
                )
                if resp.status_code == 200:
                    return Response(
                        content=resp.content,
                        media_type=resp.headers.get("content-type", "application/pdf"),
                    )
        except httpx.RequestError:
            pass

    # 本地存储
    local_path = Path(file_path)
    if not local_path.exists():
        local_path = Path("storage") / file_path.lstrip("/")
    if local_path.exists():
        mime_map = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml"}
        mime = mime_map.get(ext, "application/octet-stream")
        return StreamingResponse(open(local_path, "rb"), media_type=mime)

    return {"previewable": False, "file_name": file_name, "ocr_text": att.get("ocr_text", ""), "download_url": f"/api/attachments/{attachment_id}/download", "message": "文件暂不可预览，请下载查看"}
