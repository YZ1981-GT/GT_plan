"""回函件识别前置（spec attachment-confirmation-evidence-loop 需求 2.1，ADR-ACE-02）。

函证附件抽屉「识别比对」原先只读附件已有的识别全文：回函件挂上后从不识别，``ocr_text`` 为空时比对恒为
「低置信度」并提示「请先完成 OCR 识别」，而页面上没有别的识别入口。这里在比对前补一步：没有全文就读原件识别
（平台 OCR 路由：本机优先、服务器兜底），写回附件后再交给比对；识别失败把附件标「识别失败」并抛
:class:`ReplyOcrFailed`，调用方据此报错，不产出比对结论。

只 flush 不 commit（路由统一提交；失败时路由先提交「识别失败」再返回错误）。
"""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment

logger = logging.getLogger(__name__)


class ReplyOcrFailed(Exception):
    """识别失败：``status_code`` 503 = 识别服务不可用，422 = 原件读不到 / 没识别到文字。"""

    def __init__(self, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _local_original(file_path: str | None) -> Path | None:
    """本地原件：记录的路径；读不到再按 ``storage/`` 相对路径找（与附件下载同口径）。"""
    if not file_path:
        return None
    for candidate in (Path(file_path), Path("storage") / file_path.lstrip("/")):
        if candidate.is_file():
            return candidate
    return None


async def _recognize_original(db: AsyncSession, att: Attachment) -> str:
    from app.services.attachment_service import AttachmentService
    from app.services.unified_ocr_service import OCRServiceUnavailableError, UnifiedOCRService

    if att.storage_type == "paperless":
        if att.paperless_document_id is None:
            raise ReplyOcrFailed("原件不在本地存储，也没有 Paperless 文档编号，无法识别")
        text = await AttachmentService(db).get_paperless_ocr(att.paperless_document_id)
        if text is None:
            raise ReplyOcrFailed("Paperless 未返回识别文本（服务未配置或不可达）", status_code=503)
        return text
    path = _local_original(att.file_path)
    if path is None:
        raise ReplyOcrFailed("原件文件不存在，无法识别")
    try:
        result = await UnifiedOCRService().recognize(str(path))
    except OCRServiceUnavailableError as exc:
        raise ReplyOcrFailed(f"识别服务不可用：{exc}", status_code=503) from exc
    except Exception as exc:  # noqa: BLE001 — 引擎内部异常一律按识别失败报给用户
        logger.warning("回函识别失败 attachment=%s: %s", att.id, exc)
        raise ReplyOcrFailed(f"识别失败：{exc}") from exc
    return str((result or {}).get("text") or "")


async def ensure_reply_text(db: AsyncSession, attachment_id: UUID) -> str:
    """附件已有识别全文直接返回；否则识别原件并写回。附件不存在 ⇒ ValueError；识别失败 ⇒ ReplyOcrFailed。"""
    att = (await db.execute(
        sa.select(Attachment).where(Attachment.id == attachment_id, Attachment.is_deleted == sa.false())
    )).scalar_one_or_none()
    if att is None:
        raise ValueError("附件不存在")
    if (att.ocr_text or "").strip():
        return att.ocr_text
    try:
        text = await _recognize_original(db, att)
        if not text.strip():
            raise ReplyOcrFailed("原件里没有识别到文字（请确认是否为清晰的扫描件或照片）")
    except ReplyOcrFailed:
        att.ocr_status = "failed"
        await db.flush()
        raise
    att.ocr_text = text
    att.ocr_status = "completed"
    await db.flush()
    return text
