"""附件识别文本的完整性与确认留痕（spec attachment-security-baseline 需求 3，ADR-ASB-04）。

改造前：附件列表 / 详情返回的 ``ocr_text`` 是截断的 200 字预览，确认弹窗拿它当初值，确认时整体写回
``PUT ocr-status`` ⇒ 确认一次全文就被截成 200 字；确认状态也没有落库，页面「待确认」刷新后又出现。

现在：
- 全文只经 ``GET /api/attachments/{id}/ocr-text`` 取，同时给出 sha256；
- 确认经 ``POST /api/attachments/{id}/ocr-confirm``，带打开核对时全文的 sha256（``base_sha256``），
  与当前全文一致才写，否则 409 且库内不变；
- 确认有效 = 确认时全文 sha256 等于当前全文 sha256。任何写入方改写文本后自动失效，不依赖写入方记得清标记。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.models.attachment_models import Attachment

#: 列表 / 详情里 ``ocr_text`` 的预览长度（兼容旧消费者；全文走 ocr-text 接口）
OCR_PREVIEW_CHARS = 200

OCR_TEXT_CHANGED = "OCR_TEXT_CHANGED"
OCR_TEXT_CHANGED_MESSAGE = "识别文本已更新，请重新打开核对后再确认"


class OcrTextConflict(Exception):
    """调用方核对的不是当前全文（base 缺失或与当前全文不一致）。"""

    def as_detail(self) -> dict[str, str]:
        return {"error_code": OCR_TEXT_CHANGED, "message": OCR_TEXT_CHANGED_MESSAGE}


def text_sha256(text: str | None) -> str:
    """全文 sha256（十六进制小写）；无文本按空串计。"""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def is_confirmed(att: Attachment) -> bool:
    confirmed = getattr(att, "ocr_confirmed_sha256", None)
    return bool(confirmed) and confirmed == text_sha256(att.ocr_text)


def ocr_summary(att: Attachment) -> dict[str, Any]:
    """列表 / 详情 / 底稿反查追加的识别文本字段（``ocr_text`` 本身仍是预览）。"""
    text = att.ocr_text or ""
    confirmed_at = getattr(att, "ocr_confirmed_at", None)
    confirmed_by = getattr(att, "ocr_confirmed_by", None)
    return {
        "ocr_text_length": len(text),
        "ocr_text_truncated": len(text) > OCR_PREVIEW_CHARS,
        "ocr_confirmed": is_confirmed(att),
        "ocr_confirmed_at": confirmed_at.isoformat() if confirmed_at else None,
        "ocr_confirmed_by": str(confirmed_by) if confirmed_by else None,
    }


def full_text_payload(att: Attachment) -> dict[str, Any]:
    """``GET ocr-text`` 的响应：全文、sha256、长度与确认状态。"""
    text = att.ocr_text or ""
    return {
        "attachment_id": str(att.id),
        "ocr_status": att.ocr_status,
        "ocr_text": text,
        "sha256": text_sha256(text),
        "length": len(text),
        "ocr_confirmed_edited": getattr(att, "ocr_confirmed_edited", None),
        **{k: v for k, v in ocr_summary(att).items() if k.startswith("ocr_confirmed")},
    }


def assert_base_matches(att: Attachment, base_sha256: str | None) -> None:
    """``base_sha256`` 必须等于当前全文 sha256（大小写不敏感）。"""
    if not base_sha256 or base_sha256.strip().lower() != text_sha256(att.ocr_text):
        raise OcrTextConflict()


def confirm_ocr_text(
    att: Attachment, *, base_sha256: str | None, ocr_text: str | None, actor_id: UUID | None,
) -> dict[str, Any]:
    """核对后确认：base 与当前全文一致才写（不一致抛 :class:`OcrTextConflict`，不改任何字段）。

    带 ``ocr_text`` 且与当前全文不同 ⇒ 写入修订文本并记为「修订后确认」。只改对象、不 flush。
    """
    assert_base_matches(att, base_sha256)
    edited = ocr_text is not None and ocr_text != (att.ocr_text or "")
    if edited:
        att.ocr_text = ocr_text
    now = datetime.now(timezone.utc)
    att.ocr_status = "completed"
    att.ocr_confirmed_sha256 = text_sha256(att.ocr_text)
    att.ocr_confirmed_by = actor_id
    att.ocr_confirmed_at = now
    att.ocr_confirmed_edited = edited
    att.updated_at = now.replace(tzinfo=None)  # 与同表其他写入方同口径（naive UTC）
    return full_text_payload(att)
