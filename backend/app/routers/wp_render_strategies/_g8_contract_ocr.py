"""G8 其他权益工具投资 — 凭证附件 OCR.

POST /api/workpapers/{wp_id}/g8/contract-ocr
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

router = APIRouter(tags=["g8-ocr"])

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


class G8VoucherOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    summary: str
    confidence: float


@router.post("/api/workpapers/{wp_id}/g8/contract-ocr", response_model=G8VoucherOcrResponse)
async def g8_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G8VoucherOcrResponse:
    allowed = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "vouchers"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{attachment_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_result = await UnifiedOCRService().recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as e:  # noqa: BLE001
        logger.warning("G8 voucher OCR failed: %s", e)
        return G8VoucherOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY),
            summary="",
            confidence=0,
        )

    if not ocr_text.strip():
        return G8VoucherOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY),
            summary="",
            confidence=0,
        )

    extracted = dict(_EMPTY)
    summary = ocr_text[:200].replace("\n", " ")
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是审计凭证识别专家。从OCR文本提取其他权益工具投资相关凭证字段，"
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
        logger.warning("G8 voucher LLM extract failed: %s", e)

    filled = sum(1 for k, v in extracted.items() if v and v != "" and v != 0)
    confidence = round(filled / max(len(_VOUCHER_FIELDS), 1), 2)

    return G8VoucherOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted,
        summary=summary,
        confidence=confidence,
    )
