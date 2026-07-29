"""F2 计价组 — 跌价测试单据 OCR（F2-47）

POST /api/workpapers/{wp_id}/f2-val/contract-ocr
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

router = APIRouter(tags=["f2-val-ai"])

IMPAIRMENT_FIELDS_SCHEMA = {
    "itemName": "品名/存货名称",
    "qty": "数量(数字)",
    "unitCost": "单位成本(数字)",
    "sellingPrice": "预计售价(数字)",
    "completionCost": "至完工估计成本(数字)",
    "sellingExpense": "销售费用(数字)",
    "tax": "相关税费(数字)",
}

_EMPTY_FIELDS: dict = {k: "" for k in IMPAIRMENT_FIELDS_SCHEMA}
for _num in ("qty", "unitCost", "sellingPrice", "completionCost", "sellingExpense", "tax"):
    _EMPTY_FIELDS[_num] = 0


class F2ImpairmentOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float
    reused: bool = False
    written_back: bool = False
    governed: bool = False
    requires_human_confirmation: bool = True


_LLM_SYSTEM_PROMPT = (
    "你是审计存货跌价测试单据信息提取专家。请从OCR文本中提取NRV测算关键信息。\n"
    "严格按JSON格式返回（不确定填空字符串，数值填0）：\n"
    f"{json.dumps(IMPAIRMENT_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


def _resp(
    attachment_id: str,
    ocr_text: str,
    extracted_fields: dict,
    confidence: float,
    *,
    reused: bool = False,
    written_back: bool = False,
) -> F2ImpairmentOcrResponse:
    return F2ImpairmentOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
        reused=reused,
        written_back=written_back,
        governed=False,
        requires_human_confirmation=True,
    )


@router.post("/api/workpapers/{wp_id}/f2-val/contract-ocr")
async def f2_valuation_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    attachment_id: str | None = Form(None),
    force_reocr: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2ImpairmentOcrResponse:
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
            merged = dict(_EMPTY_FIELDS)
            merged.update({k: fields[k] for k in IMPAIRMENT_FIELDS_SCHEMA if k in fields})
            return _resp(
                str(linked_att_id),
                reused["ocr_text"],
                merged,
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
    storage_dir = Path("storage/workpapers") / wp_id / "impairment"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{temp_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_service = UnifiedOCRService()
        ocr_result = await ocr_service.recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as e:
        logger.warning("F2 val impairment OCR failed for %s: %s", wp_id, e)
        return _resp(temp_id, "", dict(_EMPTY_FIELDS), 0.0)

    if not ocr_text.strip():
        return _resp(temp_id, "", dict(_EMPTY_FIELDS), 0.0)

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
                for key in IMPAIRMENT_FIELDS_SCHEMA:
                    if key in parsed and parsed[key] is not None:
                        extracted_fields[key] = parsed[key]
                filled = sum(
                    1 for k, v in extracted_fields.items()
                    if v and v != "" and v != 0
                )
                confidence = round(filled / len(IMPAIRMENT_FIELDS_SCHEMA), 2)
    except Exception as e:
        logger.warning("F2 val impairment LLM extraction failed: %s", e)

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
