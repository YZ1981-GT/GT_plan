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

import logging
import sqlalchemy as sa
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import PERMISSION_HIERARCHY, get_current_user, require_project_access
from app.models.core import ProjectUser, User
from app.services.attachment_service import AttachmentService
from app.services.wp_visibility.entry_integration import (
    enforce_attachment_wp_visibility,
    gate_attachment_associate,
    gate_wp,
)

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


async def _ensure_project_access(
    db: AsyncSession,
    current_user: User,
    project_id: UUID,
    min_permission: str = "readonly",
):
    if current_user.role.value == "admin":
        return

    result = await db.execute(
        sa.select(ProjectUser).where(
            ProjectUser.project_id == project_id,
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == sa.false(),
        )
    )
    project_user = result.scalar_one_or_none()
    if project_user is None:
        raise HTTPException(status_code=403, detail="权限不足")

    user_level = PERMISSION_HIERARCHY.get(project_user.permission_level.value, 0)
    required_level = PERMISSION_HIERARCHY.get(min_permission, 0)
    if user_level < required_level:
        raise HTTPException(status_code=403, detail="权限不足")


def _paperless_document_id_from_path(file_path: str) -> str:
    doc_id = file_path.replace("paperless://", "", 1).lstrip("/")
    if doc_id.startswith("documents/"):
        doc_id = doc_id[len("documents/"):]
    return doc_id


@router.post("/api/projects/{project_id}/attachments")
async def create_attachment(
    project_id: UUID, body: AttachmentCreate, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
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
    current_user: User = Depends(require_project_access("edit")),
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

    # SSE 广播附件上传事件，供其他打开的页面实时同步
    try:
        from app.services.event_bus import event_bus
        event_bus.broadcast_raw(
            event_type="attachment.uploaded",
            extra={"project_id": str(project_id), "attachment_id": str(result.get("id", ""))},
        )
    except Exception:
        pass  # SSE 失败不阻断主流程

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
    current_user: User = Depends(require_project_access("readonly")),
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
    await _ensure_project_access(db, current_user, project_id, "readonly")
    svc = _svc(db)
    return await svc.search(project_id, q)


@router.get("/api/attachments/{attachment_id}")
async def get_attachment(attachment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = _svc(db)
    result = await svc.get_attachment(attachment_id)
    if not result:
        raise HTTPException(status_code=404, detail="附件不存在")
    await _ensure_project_access(db, current_user, UUID(result["project_id"]), "readonly")
    # Task 10 · wp-link 隔离层（Req 8.7/9.3）
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )
    return result


@router.post("/api/attachments/{attachment_id}/associate")
async def associate_with_wp(
    attachment_id: UUID, body: AssociateRequest, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = _svc(db)
    # Task 10 · 多资源 gate（Req 8.7/8.13/9.1-9.3）：附件项目 + 目标底稿同项目 + 源附件权限
    # + 目标 sheet 写权限，全部通过或整请求失败（副作用前）；不可见统一 404。
    await gate_attachment_associate(
        db,
        current_user,
        attachment_id=attachment_id,
        target_wp_id=body.wp_id,
    )
    result = await svc.associate_with_wp(
        attachment_id, body.wp_id, body.association_type, body.notes,
        created_by=current_user.id,
    )
    await db.commit()
    return result


@router.get("/api/working-papers/{wp_id}/attachments")
async def get_wp_attachments(wp_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = _svc(db)
    # Task 10 · 底稿绑定入口（Req 8.7）：列出底稿关联附件 = 读该底稿，走统一门；不可见统一 404。
    await gate_wp(
        db, current_user,
        entrypoint="attachment.read", action="attach_read", method="GET",
        wp_id=wp_id, entry_family="attachment",
    )
    return await svc.get_wp_attachments(wp_id)


class OCRStatusUpdate(BaseModel):
    status: str  # pending / processing / completed / failed
    ocr_text: str | None = None


@router.put("/api/attachments/{attachment_id}/ocr-status")
async def update_ocr_status(
    attachment_id: UUID, body: OCRStatusUpdate, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = _svc(db)
    att = await svc.get_attachment(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")
    await _ensure_project_access(db, current_user, UUID(att["project_id"]), "edit")
    # Task 10 · wp-link 隔离层（OCR 写；Req 8.7）：以可见性探针校验关联底稿可见。
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )
    result = await svc.update_ocr_status(attachment_id, body.status, body.ocr_text)
    if not result:
        raise HTTPException(status_code=404, detail="附件不存在")
    await db.commit()

    # OCR 确认完成后自动触发账务匹配
    if body.status == "completed" and body.ocr_text:
        try:
            matches = await _match_ocr_to_ledger(db, UUID(att["project_id"]), body.ocr_text, attachment_id)
            if matches:
                result["ledger_matches"] = matches
        except Exception as e:
            logger.warning(f"OCR 账务匹配失败: {e}")

    return result


async def _match_ocr_to_ledger(
    db: AsyncSession, project_id: UUID, ocr_text: str, attachment_id: UUID
) -> list[dict]:
    """OCR 识别结果与序时账自动核对 — 按金额+日期匹配"""
    from app.services.ocr_rule_engine import extract_fields_by_rules, classify_by_rules

    # 先用规则提取字段
    classification = classify_by_rules(ocr_text)
    doc_type = classification["type"] if classification else "other"
    fields = extract_fields_by_rules(ocr_text, doc_type)

    # 取 amount/total 字段作为匹配金额
    match_amount = None
    for f in fields:
        if f["field_name"] in ("total", "amount") and f["field_value"]:
            try:
                match_amount = float(f["field_value"].replace(",", ""))
                break
            except (ValueError, TypeError):
                pass

    if not match_amount:
        return []

    # 在序时账中按金额模糊匹配（容差 0.01 元）
    from app.models.dataset_models import LedgerDataset, DatasetStatus
    from app.models.audit_platform_models import TbLedger
    import sqlalchemy as sa

    # 获取活跃数据集
    ds_stmt = sa.select(LedgerDataset.id).where(
        LedgerDataset.project_id == project_id,
        LedgerDataset.status == DatasetStatus.active,
    )
    ds_result = await db.execute(ds_stmt)
    dataset_id = ds_result.scalar_one_or_none()
    if not dataset_id:
        return []

    # 查序时账匹配
    tolerance = 0.01
    stmt = sa.select(
        TbLedger.id,
        TbLedger.voucher_date,
        TbLedger.summary,
        TbLedger.debit_amount,
        TbLedger.credit_amount,
        TbLedger.account_code,
    ).where(
        TbLedger.dataset_id == dataset_id,
        sa.or_(
            sa.func.abs(TbLedger.debit_amount - match_amount) <= tolerance,
            sa.func.abs(TbLedger.credit_amount - match_amount) <= tolerance,
        ),
    ).limit(5)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "ledger_id": str(r.id),
            "date": r.voucher_date.isoformat() if r.voucher_date else None,
            "summary": (r.summary or "")[:50],
            "debit": float(r.debit_amount) if r.debit_amount else None,
            "credit": float(r.credit_amount) if r.credit_amount else None,
            "account_code": r.account_code,
            "match_amount": match_amount,
        }
        for r in rows
    ]


@router.post("/api/attachments/{attachment_id}/classify")
async def classify_document(attachment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = _svc(db)
    att = await svc.get_attachment(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")
    await _ensure_project_access(db, current_user, UUID(att["project_id"]), "readonly")
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )
    try:
        return await svc.classify_document(attachment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/attachments/{attachment_id}/extract-confirmation")
async def extract_confirmation_reply(attachment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = _svc(db)
    att = await svc.get_attachment(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")
    await _ensure_project_access(db, current_user, UUID(att["project_id"]), "readonly")
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )
    try:
        return await svc.extract_confirmation_reply(attachment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 统一预览/下载代理（屏蔽 paperless:// 和本地路径差异）──

@router.get("/api/attachments/{attachment_id}/download")
async def download_attachment(attachment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from fastapi.responses import StreamingResponse, Response
    from pathlib import Path
    import httpx
    import logging

    logger = logging.getLogger(__name__)

    svc = _svc(db)
    att = await svc.get_attachment(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")
    await _ensure_project_access(db, current_user, UUID(att["project_id"]), "readonly")
    # Task 10 · wp-link 隔离层（Req 8.7/9.3）：附件若关联底稿，要求至少一关联底稿可见。
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_download", method="GET", entrypoint="attachment.download",
    )

    # C3：att["file_path"] 已投影为 opaque locator，内部字节读取须取真实路径。
    raw = await svc.get_raw_storage(attachment_id)
    if not raw:
        raise HTTPException(status_code=404, detail="附件不存在")
    file_path = raw.get("file_path", "")
    file_name = att.get("file_name", "attachment")
    # 中文文件名需 RFC5987 编码（HTTP 头按 latin-1，直接放中文会 UnicodeEncodeError）
    from urllib.parse import quote as _quote
    _ascii_name = file_name.encode("ascii", "ignore").decode() or "attachment"
    _disposition = f"attachment; filename=\"{_ascii_name}\"; filename*=UTF-8''{_quote(file_name, safe='')}"

    # 审计日志：记录敏感下载操作
    logger.info(
        "attachment_download: user=%s attachment_id=%s file_name=%s",
        str(current_user.id), str(attachment_id), file_name,
    )

    # Paperless 存储：通过 Paperless API 代理下载
    if file_path.startswith("paperless://"):
        doc_id = _paperless_document_id_from_path(file_path)
        import os
        paperless_url = os.environ.get("PAPERLESS_URL", "http://localhost:8010")
        paperless_token = os.environ.get("PAPERLESS_TOKEN", "")
        try:
            async with httpx.AsyncClient(timeout=30, mounts={}, trust_env=False) as client:
                resp = await client.get(
                    f"{paperless_url}/api/documents/{doc_id}/download/",
                    headers={"Authorization": f"Token {paperless_token}"} if paperless_token else {},
                )
                if resp.status_code == 200:
                    return Response(
                        content=resp.content,
                        media_type=resp.headers.get("content-type", "application/octet-stream"),
                        headers={"Content-Disposition": _disposition},
                    )
        except httpx.RequestError:
            pass

    # 本地存储
    local_path = Path(file_path)
    if not local_path.exists():
        local_path = Path("storage") / file_path.lstrip("/")
    if local_path.exists():
        return StreamingResponse(
            open(local_path, "rb"),
            media_type="application/octet-stream",
            headers={"Content-Disposition": _disposition},
        )

    raise HTTPException(status_code=404, detail="文件不存在")


@router.get("/api/attachments/{attachment_id}/preview")
async def preview_attachment(attachment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from fastapi.responses import StreamingResponse, Response
    from pathlib import Path
    import httpx

    svc = _svc(db)
    att = await svc.get_attachment(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")
    await _ensure_project_access(db, current_user, UUID(att["project_id"]), "readonly")
    # Task 10 · wp-link 隔离层（Req 8.7/9.3）
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )

    # C3：att["file_path"] 已投影为 opaque locator，内部预览读取须取真实路径。
    raw = await svc.get_raw_storage(attachment_id)
    if not raw:
        raise HTTPException(status_code=404, detail="附件不存在")
    file_path = raw.get("file_path", "")
    file_name = att.get("file_name", "")
    file_type = att.get("file_type", "")

    # 判断是否可直接预览
    previewable_types = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".csv"}
    ext = Path(file_name).suffix.lower() if file_name else ""
    can_preview = ext in previewable_types

    if not can_preview:
        return {
            "previewable": False,
            "file_name": file_name,
            "file_type": file_type,
            "ocr_text": att.get("ocr_text", ""),
            "download_url": f"/api/attachments/{attachment_id}/download",
        }

    # Paperless 存储
    if file_path.startswith("paperless://"):
        doc_id = _paperless_document_id_from_path(file_path)
        import os
        paperless_url = os.environ.get("PAPERLESS_URL", "http://localhost:8010")
        paperless_token = os.environ.get("PAPERLESS_TOKEN", "")
        endpoint = "download" if ext in {".doc", ".docx", ".xls", ".xlsx", ".csv"} else "preview"
        try:
            async with httpx.AsyncClient(timeout=30, mounts={}, trust_env=False) as client:
                resp = await client.get(
                    f"{paperless_url}/api/documents/{doc_id}/{endpoint}/",
                    headers={"Authorization": f"Token {paperless_token}"} if paperless_token else {},
                )
                if resp.status_code == 200:
                    return Response(
                        content=resp.content,
                        media_type=resp.headers.get("content-type", "application/octet-stream"),
                    )
        except httpx.RequestError:
            pass

    # 本地存储
    local_path = Path(file_path)
    if not local_path.exists():
        local_path = Path("storage") / file_path.lstrip("/")
    if local_path.exists():
        mime_map = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml",
                    ".doc": "application/msword", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ".xls": "application/vnd.ms-excel", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ".csv": "text/csv"}
        mime = mime_map.get(ext, "application/octet-stream")
        return StreamingResponse(open(local_path, "rb"), media_type=mime)

    return {"previewable": False, "file_name": file_name, "ocr_text": att.get("ocr_text", ""), "download_url": f"/api/attachments/{attachment_id}/download", "message": "文件暂不可预览，请下载查看"}


# ── Paperless 健康检查 ──

@router.get("/api/attachments/paperless-health")
async def check_paperless_health(current_user: User = Depends(get_current_user)):
    """检查 Paperless-ngx 服务是否可用"""
    import os
    import httpx

    paperless_url = os.environ.get("PAPERLESS_URL", "http://localhost:8010")
    paperless_token = os.environ.get("PAPERLESS_TOKEN", "")

    try:
        async with httpx.AsyncClient(timeout=5, mounts={}, trust_env=False) as client:
            resp = await client.get(
                f"{paperless_url}/api/",
                headers={"Authorization": f"Token {paperless_token}"} if paperless_token else {},
            )
            if resp.status_code == 200:
                return {"available": True, "url": paperless_url, "message": "Paperless 服务正常"}
            return {"available": False, "url": paperless_url, "status": resp.status_code, "message": f"Paperless 返回 {resp.status_code}"}
    except httpx.ConnectError:
        return {"available": False, "url": paperless_url, "message": "Paperless 服务不可达"}
    except Exception as e:
        return {"available": False, "url": paperless_url, "message": str(e)}


# ── 附件重试 OCR ──

@router.post("/api/attachments/{attachment_id}/retry-ocr")
async def retry_ocr(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重试 OCR 处理（将状态重置为 pending，触发重新处理）"""
    svc = _svc(db)
    att = await svc.get_attachment(attachment_id)
    if not att:
        raise HTTPException(404, "附件不存在")
    # Task 10 · 补齐项目级授权 + wp-link 隔离层（原实现缺项目授权，Req 8.7）。
    await _ensure_project_access(db, current_user, UUID(att["project_id"]), "edit")
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )

    # 更新 OCR 状态为 pending
    from app.models.phase10_models import Attachment as AttachmentModel
    result = await db.execute(
        sa.select(AttachmentModel).where(AttachmentModel.id == attachment_id)
    )
    att_obj = result.scalar_one_or_none()
    if att_obj:
        att_obj.ocr_status = "pending"
        await db.flush()
        await db.commit()

    # 创建 OCR 重试任务
    try:
        from app.services.task_center import create_task, TaskType
        task_id = create_task(TaskType.ocr_upload, project_id=att.get("project_id", ""), object_id=str(attachment_id))
        return {"message": "OCR 重试任务已创建", "task_id": task_id}
    except Exception:
        return {"message": "OCR 状态已重置为 pending"}
