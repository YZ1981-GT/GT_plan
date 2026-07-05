"""F5 营业成本 — 出库单 OCR 识别端点（F5-6 数量核对）

POST /api/workpapers/{wp_id}/f5/contract-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)
识别出库单/发货单的数量字段，供 F5-6 销售数量核对填充。
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


_LLM_SYSTEM_PROMPT = (
    "你是审计出库单据信息提取专家。请从以下OCR文本中提取出库单/发货单的关键信息。\n"
    "严格按JSON格式返回以下字段（不确定的填空字符串，数量填0）：\n"
    f"{json.dumps(OUTBOUND_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


@router.post("/api/workpapers/{wp_id}/f5/contract-ocr")
async def f5_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F5OcrResponse:
    """上传出库单附件，OCR识别并提取数量字段"""

    allowed_types = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed_types}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "outbound"
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
        logger.warning("F5 outbound OCR failed for %s: %s", wp_id, e)
        return F5OcrResponse(attachment_id=attachment_id, ocr_text="", extracted_fields=dict(_EMPTY_FIELDS), confidence=0)

    if not ocr_text.strip():
        return F5OcrResponse(attachment_id=attachment_id, ocr_text="", extracted_fields=dict(_EMPTY_FIELDS), confidence=0)

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
        return F5OcrResponse(attachment_id=attachment_id, ocr_text=ocr_text, extracted_fields=dict(_EMPTY_FIELDS), confidence=0)

    return F5OcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
