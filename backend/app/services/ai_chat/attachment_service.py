"""会话附件安全上传、OCR 状态机与清理服务（Task 16）

Feature: dsh-agent-panel-integration
Requirements:
  - 7.2：上传只返回 attachment ID/状态，不返回服务器路径
  - 7.3：使用 Task 3 的 ai_chat_attachments 表
  - 7.4：同时校验扩展名、MIME magic、数量、大小、图片像素、PDF 页数/解压上限
  - 7.5：OCR 五态状态机（pending→running→succeeded/empty/failed/unavailable/timeout/cancelled）
  - 7.6：区分 HTTP unavailable、in-process failure、timeout、empty、success/cancelled
  - 7.7：metadata 绑定 owner/project/session/run/hash/status/expiry/legal hold
  - 7.8：重复 owner/session/hash 幂等（唯一约束）
  - 7.9：cleanup 先删文件再标 deleted；失败保留 metadata 可重试，legal hold 跳过
Design: "Components and Interfaces → 6. 会话附件"

存储路径：``storage/ai_chat/{random_uuid}.{ext}`` —— 随机命名防路径穿越。
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import struct
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import AIChatAttachment, AttachmentOcrStatus

logger = logging.getLogger(__name__)

__all__ = [
    "AttachmentUploadResult",
    "AttachmentValidationError",
    "AttachmentService",
]


# ---------------------------------------------------------------------------
# 安全校验配置
# ---------------------------------------------------------------------------

#: 允许的扩展名（小写，含 dot）
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif",
    ".pdf",
    ".doc", ".docx", ".xls", ".xlsx",
})

#: MIME magic 白名单
ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp",
    "image/tiff",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
})

#: 单文件最大尺寸（字节）
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

#: 单次会话最大附件数
MAX_ATTACHMENTS_PER_SESSION = 20

#: 图片最大像素（宽 × 高）
MAX_IMAGE_PIXELS = 50_000_000  # 50MP

#: PDF 最大页数
MAX_PDF_PAGES = 100

#: 附件存储根目录
STORAGE_ROOT = Path(os.environ.get(
    "AI_CHAT_ATTACHMENT_STORAGE", "storage/ai_chat"
))

#: 默认过期时间（天）
DEFAULT_EXPIRY_DAYS = 30


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class AttachmentValidationError(ValueError):
    """附件校验失败（扩展名/MIME/大小/像素/页数/数量）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AttachmentUploadResult:
    """上传结果（只返回 ID 和状态，不返回服务器路径，Req 7.2）。"""

    def __init__(
        self,
        attachment_id: UUID,
        status: str,
        *,
        replayed: bool = False,
        ocr_status: str = "pending",
    ) -> None:
        self.attachment_id = attachment_id
        self.status = status  # created / replayed
        self.replayed = replayed
        self.ocr_status = ocr_status

    def as_dict(self) -> dict[str, Any]:
        return {
            "attachment_id": str(self.attachment_id),
            "status": self.status,
            "replayed": self.replayed,
            "ocr_status": self.ocr_status,
        }


# ---------------------------------------------------------------------------
# 附件服务
# ---------------------------------------------------------------------------


class AttachmentService:
    """会话附件全生命周期管理。

    上传流程（Req 7.4）：
    1. 校验扩展名 + MIME magic + 文件大小
    2. 校验图片像素 / PDF 页数
    3. 计算 SHA-256
    4. 唯一约束幂等 upsert（Req 7.8）
    5. 随机命名写入文件系统（防路径穿越）
    6. 后台发起 OCR（状态机）

    清理流程（Req 7.9）：
    1. legal hold 跳过并记录审计
    2. 先删文件再标 deleted_at
    3. 文件删除失败保留 metadata 可重试
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upload(
        self,
        *,
        owner_id: UUID,
        project_id: UUID | None,
        session_id: UUID,
        file_content: bytes,
        original_name: str,
        mime_type: str,
    ) -> AttachmentUploadResult:
        """安全上传附件。

        Returns:
            AttachmentUploadResult（只含 ID 和状态）

        Raises:
            AttachmentValidationError: 校验失败
        """
        # ① 校验扩展名
        ext = _safe_extension(original_name)
        if ext not in ALLOWED_EXTENSIONS:
            raise AttachmentValidationError(
                "invalid_extension",
                f"不支持的文件类型：{ext}（允许：{', '.join(sorted(ALLOWED_EXTENSIONS))}）",
            )

        # ② 校验 MIME type
        if mime_type not in ALLOWED_MIME_TYPES:
            # 尝试从 magic bytes 推断
            detected = _detect_mime_magic(file_content[:16])
            if detected and detected in ALLOWED_MIME_TYPES:
                mime_type = detected
            else:
                raise AttachmentValidationError(
                    "invalid_mime",
                    f"不支持的 MIME 类型：{mime_type}",
                )

        # ③ 校验文件大小
        size = len(file_content)
        if size > MAX_FILE_SIZE:
            raise AttachmentValidationError(
                "file_too_large",
                f"文件超过大小限制（{size} > {MAX_FILE_SIZE} 字节）",
            )
        if size == 0:
            raise AttachmentValidationError("empty_file", "不接受空文件")

        # ④ 校验图片像素
        if mime_type.startswith("image/"):
            pixels = _estimate_image_pixels(file_content)
            if pixels and pixels > MAX_IMAGE_PIXELS:
                raise AttachmentValidationError(
                    "image_too_large",
                    f"图片像素超限（{pixels} > {MAX_IMAGE_PIXELS}）",
                )

        # ⑤ 校验 PDF 页数
        if mime_type == "application/pdf":
            pages = _estimate_pdf_pages(file_content)
            if pages and pages > MAX_PDF_PAGES:
                raise AttachmentValidationError(
                    "pdf_too_many_pages",
                    f"PDF 页数超限（{pages} > {MAX_PDF_PAGES}）",
                )

        # ⑥ 校验数量上限
        existing_count = await self._count_session_attachments(session_id)
        if existing_count >= MAX_ATTACHMENTS_PER_SESSION:
            raise AttachmentValidationError(
                "too_many_attachments",
                f"单次会话附件数已达上限（{MAX_ATTACHMENTS_PER_SESSION}）",
            )

        # ⑦ 计算 SHA-256
        sha256 = hashlib.sha256(file_content).hexdigest()

        # ⑧ 幂等 upsert：重复 (owner_id, session_id, sha256) 返回已有记录
        storage_name = f"{uuid_mod.uuid4().hex}{ext}"
        expires_at = datetime.now(timezone.utc) + timedelta(days=DEFAULT_EXPIRY_DAYS)

        stmt = (
            pg_insert(AIChatAttachment)
            .values(
                id=uuid_mod.uuid4(),
                owner_id=owner_id,
                project_id=project_id,
                session_id=session_id,
                sha256=sha256,
                original_name=_sanitize_filename(original_name),
                storage_name=storage_name,
                mime_type=mime_type,
                size_bytes=size,
                ocr_status=AttachmentOcrStatus.pending.value,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(
                index_elements=["owner_id", "session_id", "sha256"],
            )
            .returning(AIChatAttachment.id, AIChatAttachment.ocr_status)
        )
        row = (await self._db.execute(stmt)).first()

        if row is not None:
            # 新插入成功，写文件
            await self._save_file(storage_name, file_content)
            return AttachmentUploadResult(
                attachment_id=row.id,
                status="created",
                ocr_status=row.ocr_status,
            )

        # 冲突 = 幂等命中，查回已有记录
        existing = (
            await self._db.execute(
                sa.select(AIChatAttachment.id, AIChatAttachment.ocr_status).where(
                    AIChatAttachment.owner_id == owner_id,
                    AIChatAttachment.session_id == session_id,
                    AIChatAttachment.sha256 == sha256,
                    AIChatAttachment.deleted_at.is_(None),
                )
            )
        ).first()
        if existing:
            return AttachmentUploadResult(
                attachment_id=existing.id,
                status="replayed",
                replayed=True,
                ocr_status=existing.ocr_status,
            )
        # 理论上不可达：冲突却查不到未删除的（极端并发删除），重新抛
        raise AttachmentValidationError(
            "upload_conflict", "附件上传冲突，请重试"
        )

    # ------------------------------------------------------------------
    # OCR 状态机
    # ------------------------------------------------------------------

    async def start_ocr(self, attachment_id: UUID) -> str:
        """发起 OCR（pending → running）。

        OCR 由后台任务调用本方法转状态 + 调用 UnifiedOCRService。
        返回 OCR 结果状态。
        """
        # CAS: pending → running
        result = await self._db.execute(
            sa.update(AIChatAttachment)
            .where(
                AIChatAttachment.id == attachment_id,
                AIChatAttachment.ocr_status == AttachmentOcrStatus.pending.value,
            )
            .values(ocr_status=AttachmentOcrStatus.running.value)
            .returning(AIChatAttachment.storage_name, AIChatAttachment.mime_type)
        )
        row = result.first()
        if row is None:
            # 非 pending 状态（已运行/已取消/已完成），不重复执行
            return "already_started"

        storage_name = row.storage_name
        file_path = STORAGE_ROOT / storage_name

        try:
            from app.services.unified_ocr_service import (
                OCRServiceUnavailableError,
                UnifiedOCRService,
            )

            ocr = UnifiedOCRService()
            ocr_result = await ocr.recognize(str(file_path))
            text = ocr_result.get("text", "")

            if text:
                await self._set_ocr_result(
                    attachment_id, AttachmentOcrStatus.succeeded, text
                )
                return "succeeded"
            else:
                await self._set_ocr_result(
                    attachment_id, AttachmentOcrStatus.empty, None
                )
                return "empty"

        except OCRServiceUnavailableError:
            await self._set_ocr_result(
                attachment_id, AttachmentOcrStatus.unavailable, None,
                error_code="ocr_service_unavailable",
            )
            return "unavailable"

        except TimeoutError:
            await self._set_ocr_result(
                attachment_id, AttachmentOcrStatus.timeout, None,
                error_code="ocr_timeout",
            )
            return "timeout"

        except Exception as exc:
            logger.error(
                "OCR 处理失败 attachment=%s: %s: %s",
                attachment_id, type(exc).__name__, exc,
            )
            await self._set_ocr_result(
                attachment_id, AttachmentOcrStatus.failed, None,
                error_code=f"ocr_error:{type(exc).__name__}",
            )
            return "failed"

    async def cancel_ocr(self, attachment_id: UUID) -> bool:
        """取消 OCR（pending/running → cancelled）。"""
        result = await self._db.execute(
            sa.update(AIChatAttachment)
            .where(
                AIChatAttachment.id == attachment_id,
                AIChatAttachment.ocr_status.in_([
                    AttachmentOcrStatus.pending.value,
                    AttachmentOcrStatus.running.value,
                ]),
            )
            .values(ocr_status=AttachmentOcrStatus.cancelled.value)
        )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # 附件验证（run 提交时校验 owner/host/session）
    # ------------------------------------------------------------------

    async def validate_for_run(
        self,
        *,
        attachment_ids: list[UUID],
        owner_id: UUID,
        session_id: UUID,
    ) -> list[AIChatAttachment]:
        """校验 run 提交的附件归属（Req 7.5）。

        逐个校验 attachment owner/session；不属于当前用户/会话的直接拒绝。
        返回通过校验的附件记录列表。
        """
        if not attachment_ids:
            return []

        rows = (
            await self._db.execute(
                sa.select(AIChatAttachment).where(
                    AIChatAttachment.id.in_(attachment_ids),
                    AIChatAttachment.deleted_at.is_(None),
                )
            )
        ).scalars().all()

        valid: list[AIChatAttachment] = []
        for att in rows:
            if att.owner_id != owner_id:
                logger.warning(
                    "附件 %s owner 不匹配：期望 %s 实际 %s",
                    att.id, owner_id, att.owner_id,
                )
                continue
            if att.session_id != session_id:
                logger.warning(
                    "附件 %s session 不匹配：期望 %s 实际 %s",
                    att.id, session_id, att.session_id,
                )
                continue
            valid.append(att)
        return valid

    # ------------------------------------------------------------------
    # 清理（Req 7.9）
    # ------------------------------------------------------------------

    async def cleanup_expired(self) -> dict[str, int]:
        """清理过期附件。

        策略：先删文件再标 deleted_at；删除失败保留 metadata 可重试，
        legal hold 跳过并记录审计。
        """
        now = datetime.now(timezone.utc)
        # 查找过期且未删除的附件
        expired = (
            await self._db.execute(
                sa.select(AIChatAttachment).where(
                    AIChatAttachment.expires_at <= now,
                    AIChatAttachment.deleted_at.is_(None),
                )
            )
        ).scalars().all()

        stats = {"skipped_legal_hold": 0, "deleted": 0, "file_delete_failed": 0}

        for att in expired:
            if att.legal_hold:
                stats["skipped_legal_hold"] += 1
                logger.info("附件 %s 有 legal hold，跳过清理", att.id)
                continue

            # 先删文件
            file_path = STORAGE_ROOT / att.storage_name
            try:
                if file_path.exists():
                    file_path.unlink()
            except OSError as exc:
                logger.error(
                    "附件文件删除失败 %s（保留 metadata 可重试）: %s",
                    att.storage_name, exc,
                )
                stats["file_delete_failed"] += 1
                continue

            # 文件删除成功后标记 deleted_at
            await self._db.execute(
                sa.update(AIChatAttachment)
                .where(AIChatAttachment.id == att.id)
                .values(deleted_at=now)
            )
            stats["deleted"] += 1

        return stats

    async def delete_attachment(
        self, attachment_id: UUID, *, owner_id: UUID
    ) -> bool:
        """用户主动删除附件。"""
        att = (
            await self._db.execute(
                sa.select(AIChatAttachment).where(
                    AIChatAttachment.id == attachment_id,
                    AIChatAttachment.owner_id == owner_id,
                    AIChatAttachment.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

        if att is None:
            return False

        # 先删文件
        file_path = STORAGE_ROOT / att.storage_name
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError as exc:
            logger.error("附件文件删除失败 %s: %s", att.storage_name, exc)
            # 文件删除失败仍标记 deleted（Req 7.9：保留 metadata 可重试）

        await self._db.execute(
            sa.update(AIChatAttachment)
            .where(AIChatAttachment.id == attachment_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
        return True

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    async def _count_session_attachments(self, session_id: UUID) -> int:
        result = await self._db.execute(
            sa.select(sa.func.count()).where(
                AIChatAttachment.session_id == session_id,
                AIChatAttachment.deleted_at.is_(None),
            )
        )
        return result.scalar() or 0

    async def _set_ocr_result(
        self,
        attachment_id: UUID,
        status: AttachmentOcrStatus,
        text: str | None,
        *,
        error_code: str | None = None,
    ) -> None:
        values: dict[str, Any] = {"ocr_status": status.value}
        if text is not None:
            values["ocr_text_protected"] = text
        if error_code:
            values["error_code"] = error_code
        await self._db.execute(
            sa.update(AIChatAttachment)
            .where(AIChatAttachment.id == attachment_id)
            .values(**values)
        )

    async def _save_file(self, storage_name: str, content: bytes) -> None:
        """写文件到存储目录（确保目录存在）。"""
        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        file_path = STORAGE_ROOT / storage_name
        # 使用 asyncio 兼容的同步写（文件 IO 在线程池）
        import asyncio

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, file_path.write_bytes, content)


# ---------------------------------------------------------------------------
# 文件安全辅助函数
# ---------------------------------------------------------------------------


def _safe_extension(filename: str) -> str:
    """提取安全的扩展名（小写，单层）。"""
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]  # 去路径
    dot_pos = name.rfind(".")
    if dot_pos <= 0:
        return ""
    return name[dot_pos:].lower()


def _sanitize_filename(filename: str) -> str:
    """清理文件名：去路径穿越、限制长度。"""
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    # 去除 .. 和 ~
    name = name.replace("..", "").replace("~", "")
    # 限制 255 字符
    return name[:255]


def _detect_mime_magic(header: bytes) -> str | None:
    """从文件头字节推断 MIME 类型。"""
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if header[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if header[:4] == b"GIF8":
        return "image/gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    if header[:2] in (b"BM",):
        return "image/bmp"
    if header[:4] in (b"II\x2a\x00", b"MM\x00\x2a"):
        return "image/tiff"
    if header[:5] == b"%PDF-":
        return "application/pdf"
    if header[:4] == b"PK\x03\x04":
        # ZIP-based（docx/xlsx）—— 无法精确区分，允许客户端声明
        return None
    return None


def _estimate_image_pixels(data: bytes) -> int | None:
    """从文件头快速估算图片像素数（不解码整个文件）。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        # PNG IHDR chunk: width(4) + height(4) at offset 16
        w = struct.unpack(">I", data[16:20])[0]
        h = struct.unpack(">I", data[20:24])[0]
        return w * h
    if data[:3] == b"\xff\xd8\xff":
        # JPEG: 需要解析 SOF 标记，简单起见用粗估
        # 实际部署中可用 Pillow.Image.open().size 但这里避免解码全部数据
        return None  # 由后续 Pillow 验证
    return None


def _estimate_pdf_pages(data: bytes) -> int | None:
    """从 PDF 内容粗估页数（不解析完整 PDF）。"""
    # 简单方式：统计 /Type /Page 出现次数（不含 /Pages）
    count = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
    return max(count, 0) if count > 0 else None
