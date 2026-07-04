"""F3 应付票据 — 票据OCR识别端点

POST /api/workpapers/{wp_id}/f3/contract-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f3-ai"])

NOTE_FIELDS_SCHEMA = {
    "noteNo": "票据号码",
    "drawer": "出票人",
    "acceptor": "承兑人",
    "faceValue": "票面金额(数字)",
    "interestRate": "票面利率%(数字,无则0)",
    "issueDate": "出票日期(YYYY-MM-DD)",
    "dueDate": "到期日期(YYYY-MM-DD)",
    "interestStart": "计息起始日(YYYY-MM-DD,无则空)",
    "interestEnd": "计息截止日(YYYY-MM-DD,无则空)",
}

_EMPTY_FIELDS = {k: "" for k in NOTE_FIELDS_SCHEMA}
_EMPTY_FIELDS["faceValue"] = 0
_EMPTY_FIELDS["interestRate"] = 0


class F3NoteOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float


_LLM_SYSTEM_PROMPT = (
    "你是审计票据信息提取专家。请从以下OCR文本中提取应付票据/承兑汇票的关键信息。\n"
    "严格按JSON格式返回以下字段（不确定的填空字符串，金额/利率填0）：\n"
    f"{json.dumps(NOTE_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


def _build_extraction_prompt(ocr_text: str) -> str:
    return f"OCR文本：\n{ocr_text[:6000]}"


@router.post("/api/workpapers/{wp_id}/f3/contract-ocr")
async def f3_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F3NoteOcrResponse:
    """上传票据附件，OCR识别并提取关键字段"""

    allowed_types = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed_types}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "notes"
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
        logger.warning("F3 note OCR failed for %s: %s", wp_id, e)
        return F3NoteOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    if not ocr_text.strip():
        return F3NoteOcrResponse(
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
            {"role": "user", "content": _build_extraction_prompt(ocr_text)},
        ]
        llm_result = await chat_completion(
            messages=messages,
            temperature=0.1,
            max_tokens=1500,
        )

        if isinstance(llm_result, str):
            json_str = llm_result.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for key in NOTE_FIELDS_SCHEMA:
                    if key in parsed and parsed[key] is not None:
                        extracted_fields[key] = parsed[key]

                filled = sum(
                    1 for k, v in extracted_fields.items()
                    if v and v != "" and v != 0
                )
                confidence = round(filled / len(NOTE_FIELDS_SCHEMA), 2)

    except Exception as e:
        logger.warning("F3 note LLM extraction failed for %s: %s", wp_id, e)
        return F3NoteOcrResponse(
            attachment_id=attachment_id,
            ocr_text=ocr_text,
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    return F3NoteOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
