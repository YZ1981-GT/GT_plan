"""Office 文件在线预览 — LibreOffice headless 转 PDF + 缓存

API：
  GET /api/attachments/{attachment_id}/preview-pdf
    把 Office 附件（doc/docx/xls/xlsx/ppt/pptx）转 PDF 流式返回。
    转换结果按 (attachment_id, file_path 哈希) 缓存到 storage/preview_cache/。
    LibreOffice 不可用时返回 503 + 友好错误体（前端据此显示"在线预览不可用"）。

降级策略：
  - LibreOffice 不在 PATH（shutil.which 返回 None）→ 503，detail 含 message + reason="libreoffice_unavailable"
  - 转换失败/超时 → 500
  - 文件不存在 → 404
  - 非 Office 类型 → 400

Validates: requirements.md §三 · AT-2 Office 文件在线预览
注册到 router_registry.system 域 §118。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user, PERMISSION_HIERARCHY
from app.models.core import ProjectUser, User
from app.services.attachment_service import AttachmentService
from app.services.libreoffice_pool import (
    find_soffice_path,
    get_or_create_preview_pdf,
    get_queue_depth_header,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["office-preview"])

# Office 类型扩展名（含点号）
OFFICE_EXTENSIONS: frozenset[str] = frozenset({
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".rtf",
})

LIBREOFFICE_TIMEOUT_SECONDS = 90

# 缓存目录：storage/preview_cache/
def _resolve_cache_dir() -> Path:
    """缓存目录解析。

    优先环境变量 OFFICE_PREVIEW_CACHE_DIR，
    否则 settings.STORAGE_ROOT / preview_cache。
    """
    storage_root = Path(settings.STORAGE_ROOT)
    env_dir = os.environ.get("OFFICE_PREVIEW_CACHE_DIR")
    if env_dir:
        return Path(env_dir)
    return storage_root / "preview_cache"


def _find_libreoffice() -> str | None:
    """兼容旧调用名，实际统一使用 LibreOffice 池的探测结果。"""
    return find_soffice_path()


def _cache_key(
    attachment_id: UUID,
    file_path: str,
    file_size: int,
    modified_ns: int,
) -> str:
    """缓存 key 纳入真实文件大小和纳秒 mtime，避免同尺寸替换命中旧 PDF。"""
    raw = f"{attachment_id}|{file_path}|{file_size}|{modified_ns}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


async def _ensure_project_access(
    db: AsyncSession,
    current_user: User,
    project_id: UUID,
    min_permission: str = "readonly",
) -> None:
    """与 attachments 路由相同的项目权限校验语义。"""
    import sqlalchemy as sa
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


@router.get("/api/attachments/{attachment_id:uuid}/preview-pdf")
async def preview_office_as_pdf(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Office 文件在线预览 — 转 PDF 流式返回。

    返回：
      - 200 + application/pdf：PDF 字节流
      - 400：附件非 Office 类型
      - 403：项目权限不足
      - 404：附件不存在 / 本地文件不存在
      - 500：LibreOffice 转换失败
      - 503：LibreOffice 不可用（detail.reason="libreoffice_unavailable"）
    """
    svc = AttachmentService(db)
    att = await svc.get_attachment(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")

    await _ensure_project_access(db, current_user, UUID(att["project_id"]), "readonly")
    # Wp_Bound_Gate 附件可见性隔离（Task 4 / R3 leak_risk → gated，additive；项目级授权之上再收紧）：
    # 附件绑定底稿时要求当前用户对至少一个关联底稿可见，全部不可见 → 404；未绑定 → 放行。
    from app.services.wp_visibility.entry_integration import (
        enforce_attachment_wp_visibility,
    )

    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )

    # C3：att["file_path"] 已投影为 opaque locator，转 PDF 预览的本地读取须取真实路径。
    raw = await svc.get_raw_storage(attachment_id)
    if not raw:
        raise HTTPException(status_code=404, detail="附件不存在")
    file_name = att.get("file_name") or ""
    file_path = raw.get("file_path") or ""
    ext = Path(file_name).suffix.lower()

    if ext not in OFFICE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"附件类型 {ext or '未知'} 非 Office 文件，无法转 PDF 预览",
        )

    # 1. LibreOffice 可用性检查（不可用 → 503 友好降级）
    soffice = _find_libreoffice()
    if soffice is None:
        logger.info(
            "[OFFICE_PREVIEW] libreoffice unavailable for attachment %s",
            attachment_id,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "reason": "libreoffice_unavailable",
                "message": "在线预览不可用：服务器未安装 LibreOffice，请下载查看",
            },
        )

    # 2. 先读已授权附件当前版本的不可变 blob；无 blob 才走 legacy 项目路径。
    from app.services.asset_blob_service import AssetBlobReadRejected, AssetBlobService
    from app.services.attachment_storage_resolver import plan_project_attachment

    try:
        blob = await AssetBlobService(db).read_current_attachment_blob(
            attachment_id,
            project_id=UUID(raw["project_id"]),
        )
    except AssetBlobReadRejected as exc:
        from app.services.attachment_asset_projection import asset_blob_read_authoritative

        logger.warning(
            "office preview blob rejected: attachment=%s reason=%s",
            attachment_id,
            exc.reason,
        )
        if raw.get("storage_type") == "asset_blob" or asset_blob_read_authoritative():
            raise HTTPException(status_code=404, detail="附件源文件不存在") from exc
        blob = None

    if blob is not None:
        src_path = blob.canonical_path
        file_path = f"blob:{blob.content_hash}"
    else:
        plan = plan_project_attachment(
            raw["project_id"], raw.get("storage_type"), file_path,
        )
        src_path = plan.canonical_path if plan.kind == "local" else None
    if src_path is None:
        raise HTTPException(
            status_code=404,
            detail="附件源文件不存在或为 Paperless 远程存储（暂不支持远程转 PDF 预览）",
        )

    # 3. 缓存命中检查。完成鉴权与路径解析后立即释放 DB，排队/转换不占连接。
    cache_dir = _resolve_cache_dir()
    source_stat = await asyncio.to_thread(src_path.stat)
    file_size = source_stat.st_size
    key = _cache_key(
        attachment_id,
        file_path,
        file_size,
        source_stat.st_mtime_ns,
    )
    cache_path = cache_dir / f"{key}.pdf"
    await db.close()

    logger.info(
        "[OFFICE_PREVIEW] preview %s (size=%d) via bounded LibreOffice pool",
        file_name,
        file_size,
    )
    pdf_bytes, cache_status = await get_or_create_preview_pdf(
        src_path,
        cache_path,
        timeout=LIBREOFFICE_TIMEOUT_SECONDS,
        soffice_path=soffice,
    )

    # 中文文件名需 RFC5987 编码（HTTP 头按 latin-1，直接放中文会 UnicodeEncodeError）
    from urllib.parse import quote as _quote
    _stem = f"{src_path.stem}.pdf"
    _ascii_stem = _stem.encode("ascii", "ignore").decode() or "preview.pdf"
    _disposition = f"inline; filename=\"{_ascii_stem}\"; filename*=UTF-8''{_quote(_stem, safe='')}"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": _disposition,
            "X-Preview-Cache": cache_status,
            **get_queue_depth_header(),
        },
    )


@router.get("/api/office-preview/health")
async def office_preview_health(
    current_user: User = Depends(get_current_user),
):
    """检测 LibreOffice 是否可用（前端在加载时调用以决定是否展示 iframe）。

    返回：
      - {"available": true, "soffice_path": "/usr/bin/libreoffice"}：可用
      - {"available": false, "reason": "libreoffice_unavailable", "message": "..."}：不可用
    """
    soffice = _find_libreoffice()
    if soffice is None:
        return {
            "available": False,
            "reason": "libreoffice_unavailable",
            "message": "服务器未安装 LibreOffice，Office 在线预览不可用",
        }
    return {"available": True, "soffice_path": soffice}
