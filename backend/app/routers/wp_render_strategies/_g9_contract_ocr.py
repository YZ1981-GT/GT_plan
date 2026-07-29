"""G9 其他非流动金融资产 — 凭证附件 OCR.

POST /api/workpapers/{wp_id}/g9/contract-ocr
Optional: attachment_id（已关联附件时回流 ocr_text/ocr_fields_cache）, force_reocr
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.attachment_ocr_writeback import (
    finalize_linked_ocr_writeback,
    load_reusable_ocr,
    parse_optional_uuid,
)
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["g9-ocr"])

_VOUCHER_FIELDS = {
    "voucherDate": "凭证日期",
    "voucherNo": "凭证编号",
    "businessContent": "业务内容/摘要",
    "counterAccount": "对方科目",
    "debitAmount": "借方金额(数字)",
    "creditAmount": "贷方金额(数字)",
    "summary": "识别摘要(用于填入业务内容)",
}

_EMPTY = {k: (0 if k in ("debitAmount", "creditAmount") else "") for k in _VOUCHER_FIELDS}


class G9VoucherOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    summary: str
    confidence: float
    reused: bool = False
    written_back: bool = False
    governed: bool = False
    requires_human_confirmation: bool = True


def _resp(
    attachment_id: str,
    ocr_text: str,
    extracted_fields: dict,
    summary: str,
    confidence: float,
    *,
    reused: bool = False,
    written_back: bool = False,
) -> G9VoucherOcrResponse:
    return G9VoucherOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        summary=summary,
        confidence=confidence,
        reused=reused,
        written_back=written_back,
        governed=False,
        requires_human_confirmation=True,
    )


@router.post("/api/workpapers/{wp_id}/g9/contract-ocr", response_model=G9VoucherOcrResponse)
async def g9_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    attachment_id: str | None = Form(None),
    force_reocr: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G9VoucherOcrResponse:
    linked_att_id = parse_optional_uuid(attachment_id)
    try:
        wp_uuid = UUID(wp_id)
    except ValueError:
        if linked_att_id is not None:
            raise HTTPException(400, "无效的 wp_id")
        wp_uuid = UUID(int=0)

    if linked_att_id is not None and not force_reocr:
        reused = await load_reusable_ocr(db, linked_att_id)
        if reused is not None:
            fields = reused["extracted_fields"] or {}
            merged = dict(_EMPTY)
            merged.update({k: fields[k] for k in _VOUCHER_FIELDS if k in fields})
            summary = str(
                merged.get("summary")
                or merged.get("businessContent")
                or (reused["ocr_text"] or "")[:200].replace("\n", " ")
            )
            return _resp(
                str(linked_att_id),
                reused["ocr_text"],
                merged,
                summary,
                float(reused.get("confidence") or 0),
                reused=True,
                written_back=False,
            )

    allowed = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    temp_id = str(linked_att_id) if linked_att_id else str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "vouchers"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{temp_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_result = await UnifiedOCRService().recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as e:  # noqa: BLE001
        logger.warning("G9 voucher OCR failed: %s", e)
        return _resp(temp_id, "", dict(_EMPTY), "", 0.0)

    if not ocr_text.strip():
        return _resp(temp_id, "", dict(_EMPTY), "", 0.0)

    extracted = dict(_EMPTY)
    summary = ocr_text[:200].replace("\n", " ")
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是审计凭证识别专家。从OCR文本提取其他非流动金融资产相关凭证字段，"
                    f"严格返回JSON：{json.dumps(_VOUCHER_FIELDS, ensure_ascii=False)}"
                ),
            },
            {"role": "user", "content": f"OCR文本：\n{ocr_text[:5000]}"},
        ]
        llm_result = await chat_completion(messages=messages, temperature=0.1, max_tokens=800)
        if isinstance(llm_result, str):
            json_str = llm_result.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for key in _VOUCHER_FIELDS:
                    if key in parsed and parsed[key] is not None:
                        extracted[key] = parsed[key]
                summary = str(
                    extracted.get("summary")
                    or extracted.get("businessContent")
                    or summary
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("G9 voucher LLM extract failed: %s", e)

    filled = sum(1 for k, v in extracted.items() if v and v != "" and v != 0)
    confidence = round(filled / max(len(_VOUCHER_FIELDS), 1), 2)

    out_id, written = await finalize_linked_ocr_writeback(
        db,
        wp_id=wp_uuid,
        linked_att_id=linked_att_id,
        temp_id=temp_id,
        ocr_text=ocr_text,
        extracted_fields=extracted,
        confidence=confidence,
    )
    return _resp(out_id, ocr_text, extracted, summary, confidence, written_back=written)
