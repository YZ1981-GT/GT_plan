"""H3 投资性房地产 — 租赁合同 OCR 识别端点

POST /api/workpapers/{wp_id}/h3/contract-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)

上传租赁合同扫描件，OCR 后提取租赁要素，供 H3-13 关联交易检查 / H3-14 租金收入测算逐行预填。
兼容 D4 合同 OCR 的通用返回键（amount/date/counterparty），并附加租赁专有字段。
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

router = APIRouter(tags=["h3-ai"])

LEASE_FIELDS_SCHEMA = {
    "contractNo": "合同编号",
    "counterparty": "承租方/交易对方名称",
    "lessor": "出租方名称",
    "assetName": "租赁标的物名称/坐落",
    "signDate": "合同签订日期(YYYY-MM-DD)",
    "leaseStart": "租赁起始日期(YYYY-MM-DD)",
    "leaseEnd": "租赁到期日期(YYYY-MM-DD)",
    "monthlyRent": "月租金(数字)",
    "annualRent": "年租金(数字)",
    "contractAmount": "合同总金额/租金总额(数字)",
    "area": "租赁面积(数字,平方米)",
    "paymentTerms": "租金支付方式/结算周期",
    "isRelatedParty": "是否关联方交易(Y/N/NA)",
    "pricingBasis": "定价依据/是否公允(市场价参照)",
    "breachClause": "违约/退租条款",
}

_EMPTY_FIELDS: dict = {k: "" for k in LEASE_FIELDS_SCHEMA}
for _numeric in ("monthlyRent", "annualRent", "contractAmount", "area"):
    _EMPTY_FIELDS[_numeric] = 0

_LLM_SYSTEM_PROMPT = (
    "你是审计租赁合同信息提取专家。请从以下OCR文本中提取房地产租赁合同的关键信息。\n"
    "严格按JSON格式返回以下字段（不确定的填空字符串，金额/面积填0）：\n"
    f"{json.dumps(LEASE_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


class H3ContractOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float
    # 兼容 D4 通用键，便于前端统一读取
    amount: float
    date: str
    counterparty: str


def _build_extraction_prompt(ocr_text: str) -> str:
    return f"OCR文本：\n{ocr_text[:6000]}"


def _empty_response(attachment_id: str, ocr_text: str = "") -> "H3ContractOcrResponse":
    return H3ContractOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=dict(_EMPTY_FIELDS),
        confidence=0,
        amount=0,
        date="",
        counterparty="",
    )


@router.post("/api/workpapers/{wp_id}/h3/contract-ocr")
async def h3_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H3ContractOcrResponse:
    """上传租赁合同附件，OCR识别并提取租赁要素供 H3-13/H3-14 预填"""
    _ = db, current_user

    allowed_types = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed_types}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "h3-lease-contracts"
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
        logger.warning("H3 lease contract OCR failed for %s: %s", wp_id, e)
        return _empty_response(attachment_id)

    if not ocr_text.strip():
        return _empty_response(attachment_id)

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
            max_tokens=2000,
        )

        if isinstance(llm_result, str):
            json_str = llm_result.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for key in LEASE_FIELDS_SCHEMA:
                    if key in parsed and parsed[key] is not None:
                        extracted_fields[key] = parsed[key]

                filled = sum(
                    1 for _k, v in extracted_fields.items()
                    if v not in ("", None, 0)
                )
                confidence = round(filled / len(LEASE_FIELDS_SCHEMA), 2)

    except Exception as e:
        logger.warning("H3 lease contract LLM extraction failed for %s: %s", wp_id, e)
        return _empty_response(attachment_id, ocr_text)

    def _to_num(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    return H3ContractOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
        amount=_to_num(extracted_fields.get("contractAmount"))
        or _to_num(extracted_fields.get("annualRent"))
        or _to_num(extracted_fields.get("monthlyRent")),
        date=str(extracted_fields.get("signDate") or extracted_fields.get("leaseStart") or ""),
        counterparty=str(extracted_fields.get("counterparty") or ""),
    )
