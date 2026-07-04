"""F2 特殊组 — F2-56 合同/发票 OCR."""

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

router = APIRouter(tags=["f2-spe-ai"])

CONTRACT_FIELDS_SCHEMA = {
    "contractNo": "合同/订单编号",
    "contractDate": "日期(YYYY-MM-DD)",
    "amount": "金额(数字)",
    "supplier": "供应商/甲方",
    "invoiceNo": "发票号",
    "projectName": "项目名称",
}

_EMPTY: dict = {k: (0 if k == "amount" else "") for k in CONTRACT_FIELDS_SCHEMA}


class F2SpeOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float


_LLM_SYSTEM = (
    "你是审计合同履约成本单据提取专家。从OCR文本提取关键字段。\n"
    f"严格JSON返回：\n{json.dumps(CONTRACT_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


@router.post("/api/workpapers/{wp_id}/f2-spe/contract-ocr")
async def f2_spe_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2SpeOcrResponse:
    allowed = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "contract-cost"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{attachment_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_result = await UnifiedOCRService().recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as e:
        logger.warning("F2 spe OCR failed: %s", e)
        return F2SpeOcrResponse(attachment_id=attachment_id, ocr_text="", extracted_fields=dict(_EMPTY), confidence=0)

    if not ocr_text.strip():
        return F2SpeOcrResponse(attachment_id=attachment_id, ocr_text="", extracted_fields=dict(_EMPTY), confidence=0)

    extracted = dict(_EMPTY)
    confidence = 0.0
    try:
        result = await chat_completion(
            messages=[
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": f"OCR文本：\n{ocr_text[:6000]}"},
            ],
            temperature=0.1,
            max_tokens=1200,
        )
        if isinstance(result, str):
            json_str = result.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for key in CONTRACT_FIELDS_SCHEMA:
                    if key in parsed and parsed[key] is not None:
                        extracted[key] = parsed[key]
                filled = sum(1 for k, v in extracted.items() if v and v != "" and v != 0)
                confidence = round(filled / len(CONTRACT_FIELDS_SCHEMA), 2)
    except Exception as e:
        logger.warning("F2 spe LLM extraction failed: %s", e)

    return F2SpeOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted,
        confidence=confidence,
    )
