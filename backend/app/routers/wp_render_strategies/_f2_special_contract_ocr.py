"""F2 特殊组 — F2-56 合同/发票 OCR."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f2-spe-ai"])

DOCUMENT_FIELDS_SCHEMAS: dict[str, dict[str, str]] = {
    "voucher": {
        "voucherNo": "记账凭证号",
        "businessContent": "业务内容/摘要",
        "offsetAccount": "对方科目",
        "offsetProject": "对方项目",
        "amount": "凭证金额(数字)",
        "projectName": "项目名称",
        "accountDetail": "合同履约成本科目/明细",
    },
    "contract": {
        "contractNo": "合同/协议编号",
        "contractDate": "合同日期(YYYY-MM-DD)",
        "contractTerms": "与履约成本确认、结算、验收有关的主要条款",
        "projectName": "项目名称",
    },
    "receipt": {
        "receiptProductName": "到货/验收产品名称",
        "receiptAmount": "到货/验收金额(数字)",
    },
    "logistics": {
        "logisticsQty": "物流/运输数量(数字)",
        "logisticsDateNo": "物流/运输日期及单据编号",
        "logisticsProductName": "物流/运输产品名称",
        "logisticsProvider": "物流商/运输单位",
    },
    "allocation": {
        "allocQty": "费用分配数量(数字)",
        "allocMonth": "费用归属月份",
        "allocAmount": "费用分配金额(数字)",
        "allocBasis": "费用分配依据/计算方法",
    },
    "inquiry-letter": {
        "relatedParty": "关联方名称",
        "productName": "采购产品名称",
        "month": "所属月份(1-12整数)",
        "productSpec": "产品规格/型号",
        "relatedPrice": "关联方采购价格(数字)",
        "supplier1": "可比询价单位1名称",
        "price1": "可比询价单位1报价(数字)",
        "supplier2": "可比询价单位2名称",
        "price2": "可比询价单位2报价(数字)",
        "supplier3": "可比询价单位3名称",
        "price3": "可比询价单位3报价(数字)",
        "supplier4": "可比询价单位4名称",
        "price4": "可比询价单位4报价(数字)",
        "judgment": "采购价格是否合理(合理/基本合理/不合理/待核实)",
        "remark": "备注或差异原因说明",
    },
    "market-quote": {
        "relatedParty": "关联方名称",
        "productName": "采购产品名称",
        "month": "所属月份(1-12整数)",
        "purchaseAvgPrice": "关联方采购均价(数字)",
        "marketPriceStart": "市场挂牌价月初均价(数字)",
        "marketPriceEnd": "市场挂牌价月末均价(数字)",
        "judgment": "是否处于市场价区间(是/否)",
        "remark": "取价来源或差异原因",
    },
}

_NUMERIC_FIELDS = {
    "amount", "receiptAmount", "logisticsQty", "allocQty", "allocAmount",
    "month", "relatedPrice", "price1", "price2", "price3", "price4",
    "purchaseAvgPrice", "marketPriceStart", "marketPriceEnd",
}


class F2SpeOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float


@router.post("/api/workpapers/{wp_id}/f2-spe/contract-ocr")
async def f2_spe_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    document_type: str = Form("contract"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2SpeOcrResponse:
    if document_type not in DOCUMENT_FIELDS_SCHEMAS:
        raise HTTPException(400, f"不支持的单据类型: {document_type}")
    field_schema = DOCUMENT_FIELDS_SCHEMAS[document_type]
    empty = {key: (0 if key in _NUMERIC_FIELDS else "") for key in field_schema}
    allowed = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "contract-cost" / document_type
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
        return F2SpeOcrResponse(attachment_id=attachment_id, ocr_text="", extracted_fields=dict(empty), confidence=0)

    if not ocr_text.strip():
        return F2SpeOcrResponse(attachment_id=attachment_id, ocr_text="", extracted_fields=dict(empty), confidence=0)

    extracted = dict(empty)
    confidence = 0.0
    expert = (
        "关联方采购询价函/回函提取专家"
        if document_type == "inquiry-letter"
        else "关联方采购市场价/挂牌价行情提取专家"
        if document_type == "market-quote"
        else "审计合同履约成本单据提取专家"
    )
    try:
        result = await chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"你是{expert}。"
                        f"当前单据类型为 {document_type}，只从OCR文本提取该类单据字段；"
                        "没有证据的字段保持空值，不得推测。严格返回JSON：\n"
                        f"{json.dumps(field_schema, ensure_ascii=False, indent=2)}"
                    ),
                },
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
                for key in field_schema:
                    if key in parsed and parsed[key] is not None:
                        extracted[key] = parsed[key]
                filled = sum(1 for k, v in extracted.items() if v and v != "" and v != 0)
                confidence = round(filled / len(field_schema), 2)
    except Exception as e:
        logger.warning("F2 spe LLM extraction failed: %s", e)

    return F2SpeOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted,
        confidence=confidence,
    )
