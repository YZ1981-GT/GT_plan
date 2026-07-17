"""F2 存货监盘 — 单据/盘点表 OCR（F2-24/25/26 行级填充）."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f2-st-ai"])

_SHEET_SCHEMAS: dict[str, dict[str, str]] = {
    "F2-24": {
        "itemName": "品名",
        "spec": "规格型号",
        "bookQty": "账面数量(数字)",
        "bookAmount": "账面金额(数字)",
        "erpQty": "ERP/仓储台账数量(数字)",
        "erpAmount": "ERP/仓储台账金额(数字)",
    },
    "F2-25": {
        "itemName": "品名",
        "itemCode": "存货编码",
        "spec": "规格",
        "unit": "单位",
        "unitPrice": "单价(数字)",
        "bookQty": "账面数量(数字)",
        "bookAmount": "账面金额(数字)",
        "clientCountQty": "企业盘点数量(数字)",
        "sampleQty": "抽盘/实盘数量(数字)",
        "qualityStatus": "品质状况(正常/毁损/呆滞/过期等)",
        "varianceReason": "差异原因",
    },
    "F2-26": {
        "category": "存货类别",
        "itemCode": "存货编码",
        "itemName": "品名",
        "spec": "规格",
        "unit": "单位",
        "unitPrice": "单价(数字)",
        "warehouse": "仓库",
        "countDayQty": "盘点日实存数量(数字)",
        "inboundQty": "期间入库数量(数字)",
        "outboundQty": "期间发出数量(数字)",
        "bookQty": "资产负债表日账面数量(数字)",
        "varianceReason": "差异原因",
        "needAdjust": "是否调整(是/否)",
    },
}

_NUM_KEYS = {
    "bookQty", "bookAmount", "erpQty", "erpAmount", "sampleQty", "unitPrice",
    "countDayQty", "inboundQty", "outboundQty", "clientCountQty",
}


class F2StocktakeOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float
    sheet: str


def _empty_fields(sheet: str) -> dict:
    schema = _SHEET_SCHEMAS[sheet]
    out: dict = {}
    for k in schema:
        out[k] = 0 if k in _NUM_KEYS else ""
    return out


@router.post("/api/workpapers/{wp_id}/f2-st/contract-ocr")
async def f2_stocktake_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    sheet: str = Query(..., description="F2-24|F2-25|F2-26"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2StocktakeOcrResponse:
    if sheet not in _SHEET_SCHEMAS:
        raise HTTPException(400, f"不支持的 sheet: {sheet}")

    allowed = (".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "stocktake"
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
        logger.warning("F2 stocktake OCR failed for %s/%s: %s", wp_id, sheet, e)
        return F2StocktakeOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=_empty_fields(sheet),
            confidence=0,
            sheet=sheet,
        )

    if not ocr_text.strip():
        return F2StocktakeOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=_empty_fields(sheet),
            confidence=0,
            sheet=sheet,
        )

    schema = _SHEET_SCHEMAS[sheet]
    system = (
        "你是审计存货监盘底稿信息提取专家。从 OCR 文本提取监盘/盘点表字段。\n"
        "严格返回 JSON（不确定填空字符串，数值填0）：\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
    )
    extracted = _empty_fields(sheet)
    confidence = 0.0
    try:
        llm_result = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"OCR文本：\n{ocr_text[:6000]}"},
            ],
            temperature=0.1,
            max_tokens=1200,
        )
        if isinstance(llm_result, str):
            json_str = llm_result.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for key in schema:
                    if key in parsed and parsed[key] is not None:
                        extracted[key] = parsed[key]
                filled = sum(
                    1 for k, v in extracted.items()
                    if v not in ("", 0, None)
                )
                confidence = round(filled / len(schema), 2)
    except Exception as e:
        logger.warning("F2 stocktake LLM extraction failed: %s", e)

    return F2StocktakeOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted,
        confidence=confidence,
        sheet=sheet,
    )
