"""F2 存货 — 采购单据 OCR 识别

POST /api/workpapers/{wp_id}/f2/contract-ocr
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f2-ai"])

PURCHASE_FIELDS_SCHEMA = {
    "purchaseOrderNo": "采购订单号",
    "orderDate": "日期(YYYY-MM-DD)",
    "amount": "金额(数字)",
    "supplier": "供应商",
    "invoiceNo": "发票号",
    "itemName": "品名",
}

_EMPTY_FIELDS: dict = {k: "" for k in PURCHASE_FIELDS_SCHEMA}
_EMPTY_FIELDS["amount"] = 0


class F2PurchaseOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float


_LLM_SYSTEM_PROMPT = (
    "你是审计采购单据信息提取专家。请从OCR文本中提取采购入库关键信息。\n"
    "严格按JSON格式返回（不确定填空字符串，金额填0）：\n"
    f"{json.dumps(PURCHASE_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


@router.post("/api/workpapers/{wp_id}/f2/contract-ocr")
async def f2_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2PurchaseOcrResponse:
    allowed = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "purchase"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{attachment_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_service = UnifiedOCRService()
        ocr_result = await ocr_service.recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as e:
        logger.warning("F2 purchase OCR failed for %s: %s", wp_id, e)
        return F2PurchaseOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    if not ocr_text.strip():
        return F2PurchaseOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

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
                for key in PURCHASE_FIELDS_SCHEMA:
                    if key in parsed and parsed[key] is not None:
                        extracted_fields[key] = parsed[key]
                filled = sum(1 for k, v in extracted_fields.items() if v and v != "" and v != 0)
                confidence = round(filled / len(PURCHASE_FIELDS_SCHEMA), 2)
    except Exception as e:
        logger.warning("F2 purchase LLM extraction failed: %s", e)

    return F2PurchaseOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
