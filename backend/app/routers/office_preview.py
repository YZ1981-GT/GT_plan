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

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
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
    """检测 LibreOffice 可执行文件路径。

    搜索顺序：
    1. PATH 中的 ``libreoffice`` / ``soffice``（Linux/Docker 标准位置）
    2. 环境变量 ``LIBREOFFICE_PATH`` 显式指定（运维覆盖）
    3. Windows 默认安装目录（winget / 官方 installer 默认）
    4. macOS 默认安装目录（Homebrew Cask）
    """
    for cmd in ("libreoffice", "soffice"):
        path = shutil.which(cmd)
        if path:
            return path

    env_path = os.environ.get("LIBREOFFICE_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    # Windows / macOS 默认安装目录 fallback
    fallback_paths = (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/lib/libreoffice/program/soffice",  # 部分 Linux 发行版未挂 PATH
    )
    for fb in fallback_paths:
        if Path(fb).exists():
            return fb

    return None


def _cache_key(attachment_id: UUID, file_path: str, file_size: int) -> str:
    """缓存 key：attachment_id + file_path + file_size 的 SHA-256（前 16 位）。

    file_size 作为 file_version 简化版（Attachment 表无 version 字段，
    file_size 变更通常意味着文件被替换）。
    """
    raw = f"{attachment_id}|{file_path}|{file_size}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _convert_office_to_pdf(soffice: str, src_path: Path) -> bytes:
    """调用 LibreOffice headless 转 PDF，返回 PDF bytes。

    成功返回 bytes；失败抛 HTTPException(500)。
    """
    with tempfile.TemporaryDirectory(prefix="office_preview_") as tmpdir:
        try:
            proc = subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf",
                 "--outdir", tmpdir, str(src_path)],
                capture_output=True,
                timeout=LIBREOFFICE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            logger.warning("[OFFICE_PREVIEW] LibreOffice timed out for %s", src_path.name)
            raise HTTPException(
                status_code=500,
                detail=f"PDF 转换超时（{LIBREOFFICE_TIMEOUT_SECONDS}s）",
            )

        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="ignore")[:500] if proc.stderr else ""
            logger.warning(
                "[OFFICE_PREVIEW] LibreOffice conversion failed (rc=%d): %s",
                proc.returncode, err,
            )
            raise HTTPException(
                status_code=500,
                detail=f"PDF 转换失败: {err}" if err else "PDF 转换失败",
            )

        pdf_path = Path(tmpdir) / f"{src_path.stem}.pdf"
        if not pdf_path.exists():
            raise HTTPException(status_code=500, detail="LibreOffice 未生成 PDF 文件")

        return pdf_path.read_bytes()


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


def _resolve_local_path(file_path: str) -> Path | None:
    """解析附件本地路径（兼容 storage/ 前缀和绝对路径）。

    paperless:// 前缀返回 None（暂不支持 paperless 直转）。
    """
    if not file_path or file_path.startswith("paperless://"):
        return None
    candidate = Path(file_path)
    if candidate.exists():
        return candidate
    fallback = Path("storage") / file_path.lstrip("/")
    if fallback.exists():
        return fallback
    return None


@router.get("/api/attachments/{attachment_id}/preview-pdf")
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

    file_name = att.get("file_name") or ""
    file_path = att.get("file_path") or ""
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

    # 2. 解析本地源文件
    src_path = _resolve_local_path(file_path)
    if src_path is None:
        raise HTTPException(
            status_code=404,
            detail="附件源文件不存在或为 Paperless 远程存储（暂不支持远程转 PDF 预览）",
        )

    # 3. 缓存命中检查
    cache_dir = _resolve_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_size = att.get("file_size") or src_path.stat().st_size
    key = _cache_key(attachment_id, file_path, file_size)
    cache_path = cache_dir / f"{key}.pdf"

    if cache_path.exists():
        logger.debug("[OFFICE_PREVIEW] cache hit for %s", attachment_id)
        pdf_bytes = cache_path.read_bytes()
    else:
        logger.info(
            "[OFFICE_PREVIEW] converting %s (size=%d) via LibreOffice",
            file_name, file_size,
        )
        pdf_bytes = _convert_office_to_pdf(soffice, src_path)
        # 写缓存（写失败不阻断响应）
        try:
            cache_path.write_bytes(pdf_bytes)
        except OSError as e:
            logger.warning("[OFFICE_PREVIEW] cache write failed: %s", e)

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
            "X-Preview-Cache": "hit" if cache_path.exists() else "miss",
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
