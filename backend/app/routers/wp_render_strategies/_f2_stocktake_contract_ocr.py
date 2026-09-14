"""F2 存货监盘 — 单据/盘点表 OCR（F2-24/25/26 行级填充）.

Optional: attachment_id（已关联附件时回流 ocr_text/ocr_fields_cache）, force_reocr
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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
    "H1-10": {
        "itemName": "固定资产名称",
        "itemCode": "资产编号",
        "spec": "规格型号",
        "unit": "单位",
        "unitPrice": "单价(数字)",
        "bookQty": "账面数量(数字)",
        "bookAmount": "账面金额/原值(数字)",
        "clientCountQty": "企业盘点数量(数字)",
        "sampleQty": "审计抽盘数量(数字)",
        "qualityStatus": "品质状况(正常/闲置/毁损/待报废)",
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
    reused: bool = False
    written_back: bool = False
    governed: bool = False
    requires_human_confirmation: bool = True


def _empty_fields(sheet: str) -> dict:
    schema = _SHEET_SCHEMAS[sheet]
    out: dict = {}
    for k in schema:
        out[k] = 0 if k in _NUM_KEYS else ""
    return out


def _resp(
    attachment_id: str,
    ocr_text: str,
    extracted_fields: dict,
    confidence: float,
    sheet: str,
    *,
    reused: bool = False,
    written_back: bool = False,
) -> F2StocktakeOcrResponse:
    return F2StocktakeOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
        sheet=sheet,
        reused=reused,
        written_back=written_back,
        governed=False,
        requires_human_confirmation=True,
    )


@router.post("/api/workpapers/{wp_id}/f2-st/contract-ocr")
async def f2_stocktake_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    sheet: str = Query(..., description="F2-24|F2-25|F2-26|H1-10"),
    attachment_id: str | None = Form(None),
    force_reocr: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2StocktakeOcrResponse:
    if sheet not in _SHEET_SCHEMAS:
        raise HTTPException(400, f"不支持的 sheet: {sheet}")

    linked_att_id = parse_optional_uuid(attachment_id)
    try:
        wp_uuid = UUID(wp_id)
    except ValueError:
        if linked_att_id is not None:
            raise HTTPException(400, "无效的 wp_id")
        wp_uuid = UUID(int=0)
    schema = _SHEET_SCHEMAS[sheet]
    empty = _empty_fields(sheet)

    if linked_att_id is not None and not force_reocr:
        reused = await load_reusable_ocr(db, linked_att_id)
        if reused is not None:
            fields = reused["extracted_fields"] or {}
            merged = dict(empty)
            merged.update({k: fields[k] for k in schema if k in fields})
            return _resp(
                str(linked_att_id),
                reused["ocr_text"],
                merged,
                float(reused.get("confidence") or 0),
                sheet,
                reused=True,
                written_back=False,
            )

    allowed = (".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    temp_id = str(linked_att_id) if linked_att_id else str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "stocktake"
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
        logger.warning("F2 stocktake OCR failed for %s/%s: %s", wp_id, sheet, e)
        return _resp(temp_id, "", empty, 0.0, sheet)

    if not ocr_text.strip():
        return _resp(temp_id, "", empty, 0.0, sheet)

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

    out_id, written = await finalize_linked_ocr_writeback(
        db,
        wp_id=wp_uuid,
        linked_att_id=linked_att_id,
        temp_id=temp_id,
        ocr_text=ocr_text,
        extracted_fields=extracted,
        confidence=confidence,
    )
    return _resp(out_id, ocr_text, extracted, confidence, sheet, written_back=written)
