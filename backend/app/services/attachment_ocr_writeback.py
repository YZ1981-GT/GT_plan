"""底稿页 OCR → 附件证据链回流（Req5 / Wave 6）。

spec: attachment-workpaper-linkage-convergence Task 7.1

试点路径：``/d4/contract-ocr``、``/f2/contract-ocr``。
- 仅当附件已关联到底稿时写入 ``ocr_text`` / ``ocr_fields_cache``
- 恒 ``governed=False`` / ``requires_human_confirmation=True``（不落业务数据）
- 已有 OCR 可复用；``force=True`` 时重新识别覆盖
- fail-open：写入失败不阻断 OCR 主响应
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment, AttachmentWorkingPaper

logger = logging.getLogger(__name__)


async def is_attachment_linked_to_wp(
    db: AsyncSession,
    attachment_id: UUID,
    wp_id: UUID,
) -> bool:
    """整稿关联、本底稿证据链接（行级证据，spec attachment-evidence-intake 需求 3.7）或 reference 任一命中即视为已关联。"""
    from app.models.wp_optimization_models import EvidenceLink

    for model in (AttachmentWorkingPaper, EvidenceLink):
        link_cnt = (
            await db.execute(
                sa.select(sa.func.count())
                .select_from(model)
                .where(model.attachment_id == attachment_id, model.wp_id == wp_id)
            )
        ).scalar()
        if int(link_cnt or 0) > 0:
            return True

    ref = (
        await db.execute(
            sa.select(Attachment.id).where(
                Attachment.id == attachment_id,
                Attachment.reference_type == "working_paper",
                Attachment.reference_id == wp_id,
                Attachment.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()
    return ref is not None


async def load_reusable_ocr(
    db: AsyncSession,
    attachment_id: UUID,
) -> dict[str, Any] | None:
    """若附件已有 OCR 文本，返回可复用载荷；否则 None。"""
    att = (
        await db.execute(
            sa.select(Attachment).where(
                Attachment.id == attachment_id,
                Attachment.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()
    if att is None:
        return None
    text = (att.ocr_text or "").strip()
    if not text:
        return None
    cache = att.ocr_fields_cache if isinstance(att.ocr_fields_cache, dict) else {}
    fields = cache.get("extracted_fields") if isinstance(cache.get("extracted_fields"), dict) else dict(cache)
    # 去掉治理标记，避免污染 extracted_fields 视图
    fields = {
        k: v
        for k, v in (fields or {}).items()
        if k not in ("governed", "requires_human_confirmation", "extracted_fields", "ocr_text", "confidence")
    }
    confidence = cache.get("confidence", 0.0)
    try:
        confidence = float(confidence or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "ocr_text": att.ocr_text or "",
        "extracted_fields": fields,
        "confidence": confidence,
        "reused": True,
        "written_back": False,
        "governed": False,
        "requires_human_confirmation": True,
    }


async def writeback_ocr_to_linked_attachment(
    db: AsyncSession,
    *,
    attachment_id: UUID,
    wp_id: UUID,
    ocr_text: str,
    extracted_fields: dict[str, Any] | None = None,
    confidence: float = 0.0,
) -> bool:
    """回流 OCR 到已关联附件。未关联 / 失败 → False（fail-open）。"""
    try:
        if not await is_attachment_linked_to_wp(db, attachment_id, wp_id):
            return False

        att = (
            await db.execute(
                sa.select(Attachment).where(
                    Attachment.id == attachment_id,
                    Attachment.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()
        if att is None:
            return False

        fields = dict(extracted_fields or {})
        # 人工确认闸门标记写入 cache（不落业务表）
        cache_payload = {
            **fields,
            "extracted_fields": fields,
            "confidence": confidence,
            "governed": False,
            "requires_human_confirmation": True,
        }
        att.ocr_text = ocr_text or ""
        att.ocr_fields_cache = cache_payload
        att.ocr_status = "completed" if (ocr_text or "").strip() else "failed"
        await db.flush()
        return True
    except Exception:
        logger.warning(
            "event=awp_ocr_writeback_fail_open attachment_id=%s wp_id=%s",
            attachment_id,
            wp_id,
            exc_info=True,
        )
        return False


async def finalize_linked_ocr_writeback(
    db: AsyncSession,
    *,
    wp_id: UUID,
    linked_att_id: UUID | None,
    temp_id: str,
    ocr_text: str,
    extracted_fields: dict[str, Any] | None,
    confidence: float,
) -> tuple[str, bool]:
    """统一 OCR 回流收尾：返回 ``(out_attachment_id, written_back)``。

    ``linked_att_id`` 为空时不写库，``out_id`` 用临时 id（现状兼容）。
    """
    if linked_att_id is None:
        return temp_id, False
    written = await writeback_ocr_to_linked_attachment(
        db,
        attachment_id=linked_att_id,
        wp_id=wp_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
    if written:
        try:
            await db.commit()
        except Exception:
            logger.warning(
                "event=awp_ocr_writeback_commit_fail_open attachment_id=%s wp_id=%s",
                linked_att_id,
                wp_id,
                exc_info=True,
            )
            written = False
    return str(linked_att_id), written


def parse_optional_uuid(value: str | None) -> UUID | None:
    if not value or not str(value).strip():
        return None
    try:
        return UUID(str(value).strip())
    except (ValueError, TypeError):
        return None


# 识别前建附件的写法统一在 services/workpaper_evidence_intake.py（spec attachment-evidence-intake ADR-AEI-01）：
# 原 provision_wp_linked_attachment 建附件失败时退回临时 id 继续识别，行里存下的 id 在附件表不存在，已删除。
