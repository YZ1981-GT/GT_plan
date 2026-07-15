"""E1 货币资金 — 企业信用报告 OCR 识别端点

POST /api/workpapers/{wp_id}/e1/credit-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)

上传征信报告打印件，OCR 识别文本后由 LLM 提取 E1-18 查询记录字段，
供前端确认后回填表单。
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

router = APIRouter(tags=["e1-ocr"])

CREDIT_FIELDS_SCHEMA = {
    "borrowerName": "借款人/企业名称",
    "creditCode": "征信人代码",
    "loanCardCode": "贷款卡编码",
    "reportDate": "报告日期/打印日期(YYYY-MM-DD)",
    "inquireDate": "查询日期(YYYY-MM-DD，若可知)",
    "hasOverview": "是否含征信人概况(Y/N)",
    "hasFinance": "是否含财务信息(Y/N)",
    "hasCreditInfo": "是否含信贷信息(Y/N)",
    "outstandingNote": "未结清信贷信息与账面核对情况的概括说明",
    "queryResult": "信用状况/查询结果概括结论",
    "attachmentIndex": "建议附件索引号",
}

_EMPTY_FIELDS = {k: "" for k in CREDIT_FIELDS_SCHEMA}

_LLM_SYSTEM_PROMPT = (
    "你是注册会计师审计助手，专长于解读中国人民银行企业信用报告（贷款卡信息）。\n"
    "请从以下OCR文本中提取企业信用报告关键字段。\n"
    "严格按JSON格式返回以下字段（不确定的填空字符串；Y/N 字段仅填 Y 或 N 或空）：\n"
    f"{json.dumps(CREDIT_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}\n"
    "规则：\n"
    "1. outstandingNote：根据未结清保函/承兑/贴现等信息概括；若未见异常可写核对一致类表述。\n"
    "2. queryResult：概括信贷信息是否正常、有无关注事项。\n"
    "3. 日期统一为 YYYY-MM-DD；无法判断则留空。"
)


class E1CreditOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float


def _parse_llm_json(raw: str) -> dict:
    json_str = (raw or "").strip()
    if "```json" in json_str:
        json_str = json_str.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in json_str:
        json_str = json_str.split("```", 1)[1].split("```", 1)[0].strip()
    parsed = json.loads(json_str)
    return parsed if isinstance(parsed, dict) else {}


@router.post("/api/workpapers/{wp_id}/e1/credit-ocr", response_model=E1CreditOcrResponse)
async def e1_credit_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> E1CreditOcrResponse:
    """上传企业信用报告打印件，OCR + AI 提取 E1-18 表单字段。"""
    _ = db  # 鉴权依赖用；本端点仅落盘+识别

    allowed = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
    filename = file.filename or "credit-report.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "credit-reports"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{attachment_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_result = await UnifiedOCRService().recognize(str(file_path))
        ocr_text = ocr_result.get("text", "") or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 credit OCR failed for %s: %s", wp_id, e)
        return E1CreditOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    if not ocr_text.strip():
        return E1CreditOcrResponse(
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
            {"role": "user", "content": f"OCR文本：\n{ocr_text[:8000]}"},
        ]
        llm_result = await chat_completion(messages=messages, temperature=0.1, max_tokens=2000)
        raw = llm_result if isinstance(llm_result, str) else str(llm_result)
        parsed = _parse_llm_json(raw)
        for key in CREDIT_FIELDS_SCHEMA:
            if key in parsed and parsed[key] is not None:
                extracted_fields[key] = str(parsed[key]).strip()
        filled = sum(1 for v in extracted_fields.values() if v and v != "")
        confidence = round(filled / max(len(CREDIT_FIELDS_SCHEMA), 1), 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 credit LLM extraction failed for %s: %s", wp_id, e)
        return E1CreditOcrResponse(
            attachment_id=attachment_id,
            ocr_text=ocr_text,
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    return E1CreditOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
