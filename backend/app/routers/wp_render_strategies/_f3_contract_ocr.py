"""F3 应付票据 — 票据OCR识别端点

POST /api/workpapers/{wp_id}/f3/contract-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)
Optional: attachment_id（已关联附件时回流 ocr_text/ocr_fields_cache）, force_reocr
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
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

router = APIRouter(tags=["f3-ai"])

NOTE_FIELDS_SCHEMA = {
    "noteType": "票据类别（银行承兑汇票/商业承兑汇票/供应链票据/其他）",
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

OVERDUE_FIELDS_SCHEMA = {
    "noteType": "票据类别（银行承兑汇票/商业承兑汇票/供应链票据/其他）",
    "noteNo": "票据号码",
    "drawer": "出票人",
    "acceptor": "承兑人",
    "payee": "收款人",
    "issueDate": "出票日期(YYYY-MM-DD)",
    "dueDate": "到期日期(YYYY-MM-DD)",
    "interestRate": "票面利率%(数字,无则0)",
    "faceValue": "票面金额(数字)",
    "postPaymentAmount": "期后支付金额(数字,无则0)",
    "loanConditions": "借款/票据条件、违约或罚息条款",
    "isAdjusted": "是否已作会计调整（是/否/不适用）",
    "collateralName": "抵押或担保物品名称",
    "collateralAmount": "抵押或担保金额(数字,无则0)",
}

# F3-7 应付票据检查表 — 弹窗逐单据核对（参照F2-56模式）
VOUCHER_FIELDS_SCHEMA = {
    "voucherDate": "凭证日期(YYYY-MM-DD)",
    "voucherNo": "凭证编号",
    "businessContent": "业务内容/摘要",
    "counterAccount": "对方科目",
    "detailAccount": "明细科目",
    "amount": "凭证金额(数字)",
    "noteType": "票据类别（银行承兑汇票/商业承兑汇票/供应链票据/其他，无则空）",
}

APPROVAL_FIELDS_SCHEMA = {
    "approvalDateNo": "付款审批单日期/编号",
    "approvalProper": "是否经过恰当审批（是/否，根据审批签字/流程判断，不确定填空）",
}

BANK_RECEIPT_FIELDS_SCHEMA = {
    "bankReceiptDate": "银行回单日期(YYYY-MM-DD)",
    "bankPayee": "收款方名称",
    "bankAmount": "回单金额(数字)",
}

GOODS_RECEIPT_FIELDS_SCHEMA = {
    "receiptDateNo": "入库单/验收单日期/编号",
    "receiptProduct": "品名",
    "receiptUnit": "计量单位",
    "receiptQty": "数量(数字)",
}

INVOICE_FIELDS_SCHEMA = {
    "invoiceDateNo": "发票日期/号码",
    "invoiceCounterparty": "对手方（销售方）名称",
    "invoiceAmount": "发票金额(数字)",
}

_DOCUMENT_SCHEMAS: dict[str, dict[str, str]] = {
    "note": NOTE_FIELDS_SCHEMA,
    "overdue-note": OVERDUE_FIELDS_SCHEMA,
    "voucher": VOUCHER_FIELDS_SCHEMA,
    "approval": APPROVAL_FIELDS_SCHEMA,
    "bank-receipt": BANK_RECEIPT_FIELDS_SCHEMA,
    "goods-receipt": GOODS_RECEIPT_FIELDS_SCHEMA,
    "invoice": INVOICE_FIELDS_SCHEMA,
}

_DOCUMENT_CONTEXTS: dict[str, str] = {
    "note": "应付票据或承兑汇票",
    "overdue-note": "逾期未付票据、期后付款凭证、借款合同、诉讼文书或抵押担保文件",
    "voucher": "记账凭证",
    "approval": "付款审批单/付款申请单",
    "bank-receipt": "银行回单/电子回单",
    "goods-receipt": "入库单/验收单/到货单",
    "invoice": "增值税发票/采购发票",
}

_NUMERIC_FIELDS = {
    "faceValue", "interestRate", "postPaymentAmount", "collateralAmount",
    "amount", "bankAmount", "receiptQty", "invoiceAmount",
}


def _empty_fields(schema: dict[str, str]) -> dict:
    return {key: 0 if key in _NUMERIC_FIELDS else "" for key in schema}


class F3NoteOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float
    reused: bool = False
    written_back: bool = False
    governed: bool = False
    requires_human_confirmation: bool = True


def _system_prompt(schema: dict[str, str], document_type: str) -> str:
    context = _DOCUMENT_CONTEXTS.get(document_type, "应付票据或承兑汇票")
    return (
        f"你是审计票据信息提取专家。请从以下OCR文本中提取{context}的关键信息。\n"
        "只能提取文本中明确存在的内容，不得推测。严格按JSON格式返回以下字段"
        "（不确定的填空字符串，金额/利率填0）：\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
    )


def _build_extraction_prompt(ocr_text: str) -> str:
    return f"OCR文本：\n{ocr_text[:6000]}"


def _resp(
    attachment_id: str,
    ocr_text: str,
    extracted_fields: dict,
    confidence: float,
    *,
    reused: bool = False,
    written_back: bool = False,
) -> F3NoteOcrResponse:
    return F3NoteOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
        reused=reused,
        written_back=written_back,
        governed=False,
        requires_human_confirmation=True,
    )


@router.post("/api/workpapers/{wp_id}/f3/contract-ocr")
async def f3_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    document_type: str = Form("note"),
    attachment_id: str | None = Form(None),
    force_reocr: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F3NoteOcrResponse:
    """上传票据附件，OCR识别并提取相关字段；可选回流已关联附件证据链。"""
    linked_att_id = parse_optional_uuid(attachment_id)
    try:
        wp_uuid = UUID(wp_id)
    except ValueError:
        if linked_att_id is not None:
            raise HTTPException(400, "无效的 wp_id")
        wp_uuid = UUID(int=0)
    schema = _DOCUMENT_SCHEMAS.get(document_type, NOTE_FIELDS_SCHEMA)
    empty_fields = _empty_fields(schema)

    if linked_att_id is not None and not force_reocr:
        reused = await load_reusable_ocr(db, linked_att_id)
        if reused is not None:
            fields = reused["extracted_fields"] or {}
            merged = dict(empty_fields)
            merged.update({k: fields[k] for k in schema if k in fields})
            return _resp(
                str(linked_att_id),
                reused["ocr_text"],
                merged,
                float(reused.get("confidence") or 0),
                reused=True,
                written_back=False,
            )

    allowed_types = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed_types}")

    temp_id = str(linked_att_id) if linked_att_id else str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "notes"
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
        logger.warning("F3 note OCR failed for %s: %s", wp_id, e)
        return _resp(temp_id, "", dict(empty_fields), 0.0)

    if not ocr_text.strip():
        return _resp(temp_id, "", dict(empty_fields), 0.0)

    extracted_fields = dict(empty_fields)
    confidence = 0.0

    try:
        messages = [
            {"role": "system", "content": _system_prompt(schema, document_type)},
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
                for key in schema:
                    if key in parsed and parsed[key] is not None:
                        extracted_fields[key] = parsed[key]

                filled = sum(
                    1 for k, v in extracted_fields.items()
                    if v and v != "" and v != 0
                )
                confidence = round(filled / len(schema), 2)

    except Exception as e:
        logger.warning("F3 note LLM extraction failed for %s: %s", wp_id, e)
        return _resp(temp_id, ocr_text, dict(empty_fields), 0.0)

    out_id, written = await finalize_linked_ocr_writeback(
        db,
        wp_id=wp_uuid,
        linked_att_id=linked_att_id,
        temp_id=temp_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
    return _resp(out_id, ocr_text, extracted_fields, confidence, written_back=written)
