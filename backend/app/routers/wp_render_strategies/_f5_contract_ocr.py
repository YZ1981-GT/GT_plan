"""F5 营业成本 — 出库单 OCR 识别端点（F5-6 数量核对）

POST /api/workpapers/{wp_id}/f5/contract-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)
Optional: attachment_id（已关联附件时回流 ocr_text/ocr_fields_cache）, force_reocr
识别出库单/发货单的数量字段，供 F5-6 销售数量核对填充。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.attachment_ocr_writeback import finalize_linked_ocr_writeback, parse_optional_uuid
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService
from app.services.workpaper_evidence_intake import (
    OcrIntakeOptions,
    intake_ocr_upload,
    ocr_intake_options,
    parse_workpaper_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f5-ai"])

OUTBOUND_FIELDS_SCHEMA = {
    "product": "品种/产品名称",
    "spec": "规格型号",
    "unit": "计量单位",
    "quantity": "出库数量(数字)",
    "voucherNo": "出库单号",
    "date": "出库日期(YYYY-MM-DD)",
}

_EMPTY_FIELDS: dict = {k: "" for k in OUTBOUND_FIELDS_SCHEMA}
_EMPTY_FIELDS["quantity"] = 0


class F5OcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float
    reused: bool = False
    written_back: bool = False
    governed: bool = False
    requires_human_confirmation: bool = True


_LLM_SYSTEM_PROMPT = (
    "你是审计出库单据信息提取专家。请从以下OCR文本中提取出库单/发货单的关键信息。\n"
    "严格按JSON格式返回以下字段（不确定的填空字符串，数量填0）：\n"
    f"{json.dumps(OUTBOUND_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


def _resp(
    attachment_id: str,
    ocr_text: str,
    extracted_fields: dict,
    confidence: float,
    *,
    reused: bool = False,
    written_back: bool = False,
) -> F5OcrResponse:
    return F5OcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
        reused=reused,
        written_back=written_back,
        governed=False,
        requires_human_confirmation=True,
    )


@router.post("/api/workpapers/{wp_id}/f5/contract-ocr")
async def f5_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    attachment_id: str | None = Form(None),
    force_reocr: bool = Form(False),
    options: OcrIntakeOptions = Depends(ocr_intake_options),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F5OcrResponse:
    """上传出库单附件，OCR识别并提取数量字段；可选回流已关联附件证据链。"""
    wp_uuid = parse_workpaper_id(wp_id)

    allowed_types = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if parse_optional_uuid(attachment_id) is None and suffix not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed_types}")

    src = await intake_ocr_upload(
        db, wp_id=wp_uuid, file=file, attachment_id=attachment_id, force_reocr=force_reocr,
        user=current_user, native_type="voucher", native_prefix="F5", options=options,
    )
    if src.reused is not None:
        fields = src.reused["extracted_fields"] or {}
        merged = dict(_EMPTY_FIELDS)
        merged.update({k: fields[k] for k in OUTBOUND_FIELDS_SCHEMA if k in fields})
        return _resp(
            str(src.attachment_id),
            src.reused["ocr_text"],
            merged,
            float(src.reused.get("confidence") or 0),
            reused=True,
            written_back=False,
        )

    linked_att_id = src.attachment_id
    temp_id = str(linked_att_id)
    file_path = src.path

    ocr_text = ""
    try:
        ocr_service = UnifiedOCRService()
        ocr_result = await ocr_service.recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as e:
        logger.warning("F5 outbound OCR failed for %s: %s", wp_id, e)
        _out, _written = await finalize_linked_ocr_writeback(
            db, wp_id=wp_uuid, linked_att_id=linked_att_id, temp_id=temp_id,
            ocr_text="", extracted_fields=dict(_EMPTY_FIELDS), confidence=0.0,
        )
        return _resp(_out, "", dict(_EMPTY_FIELDS), 0.0, written_back=_written)

    if not ocr_text.strip():
        _out, _written = await finalize_linked_ocr_writeback(
            db, wp_id=wp_uuid, linked_att_id=linked_att_id, temp_id=temp_id,
            ocr_text="", extracted_fields=dict(_EMPTY_FIELDS), confidence=0.0,
        )
        return _resp(_out, "", dict(_EMPTY_FIELDS), 0.0, written_back=_written)

    extracted_fields = dict(_EMPTY_FIELDS)
    confidence = 0.0
    try:
        messages = [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": f"OCR文本：\n{ocr_text[:6000]}"},
        ]
        llm_result = await chat_completion(messages=messages, temperature=0.1, max_tokens=1200)
        if isinstance(llm_result, str):
            json_str = llm_result.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for key in OUTBOUND_FIELDS_SCHEMA:
                    if key in parsed and parsed[key] is not None:
                        extracted_fields[key] = parsed[key]
                filled = sum(1 for v in extracted_fields.values() if v and v != "" and v != 0)
                confidence = round(filled / len(OUTBOUND_FIELDS_SCHEMA), 2)
    except Exception as e:
        logger.warning("F5 outbound LLM extraction failed for %s: %s", wp_id, e)
        _out, _written = await finalize_linked_ocr_writeback(
            db, wp_id=wp_uuid, linked_att_id=linked_att_id, temp_id=temp_id,
            ocr_text=ocr_text, extracted_fields=dict(_EMPTY_FIELDS), confidence=0.0,
        )
        return _resp(_out, ocr_text, dict(_EMPTY_FIELDS), 0.0, written_back=_written)

    out_id, written = await finalize_linked_ocr_writeback(
        db,
        wp_id=wp_uuid,
        linked_att_id=linked_att_id,
        temp_id=temp_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
    return _resp(out_id, ocr_text, extracted_fields, confidence, written_back=written)
