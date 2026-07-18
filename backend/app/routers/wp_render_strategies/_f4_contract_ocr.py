"""F4 应付账款 — 长期挂账、未入账、抽凭检查及供应商融资支持性证据OCR识别。"""

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
router = APIRouter(tags=["f4-ai"])

# F4-8 应付账款检查表 — 弹窗逐单据核对
VOUCHER_FIELDS_SCHEMA: dict[str, str] = {
    "supplierName": "供应商名称",
    "voucherDate": "凭证日期(YYYY-MM-DD)",
    "voucherNo": "凭证编号",
    "businessContent": "业务内容/摘要",
    "counterAccount": "对方科目",
    "detailAccount": "明细科目",
    "amount": "凭证金额(数字)",
}

APPROVAL_FIELDS_SCHEMA: dict[str, str] = {
    "approvalDateNo": "付款审批单日期/编号",
    "approvalProper": "是否经过恰当审批（是/否，根据审批签字/流程判断，不确定填空）",
}

BANK_RECEIPT_FIELDS_SCHEMA: dict[str, str] = {
    "bankReceiptDate": "银行回单日期(YYYY-MM-DD)",
    "bankPayee": "收款方名称",
    "bankAmount": "回单金额(数字)",
}

GOODS_RECEIPT_FIELDS_SCHEMA: dict[str, str] = {
    "receiptDateNo": "入库单/验收单日期/编号",
    "receiptProduct": "品名",
    "receiptUnit": "计量单位",
    "receiptQty": "数量(数字)",
}

INVOICE_FIELDS_SCHEMA: dict[str, str] = {
    "invoiceDateNo": "发票日期/号码",
    "invoiceCounterparty": "对手方（销售方）名称",
    "invoiceAmount": "发票金额(数字)",
}

# F4-9 供应商融资检查表
SUPPLIER_FINANCING_FIELDS_SCHEMA: dict[str, str] = {
    "supplierName": "供应商名称",
    "promisedPayer": "承诺付款方/核心企业名称",
    "financingNo": "融资单号/融资合同编号",
    "fundProvider": "资金提供方（金融机构）名称",
    "status": "融资状态（未放款/已放款/已转让/已还款/逾期等）",
    "financingAmount": "融资金额(数字)",
    "supplierSignDate": "供应商签收日期(YYYY-MM-DD)",
    "disbursementDate": "放款日期(YYYY-MM-DD)",
    "transferDate": "债权转让日期(YYYY-MM-DD)",
    "promisedRepayDate": "承诺还款日期(YYYY-MM-DD)",
    "actualRepayDate": "实际还款日期(YYYY-MM-DD)",
    "purchaseAmount": "对应本期采购金额(数字，仅文件明确时填写)",
    "loanBalance": "期末借款/应付余额(数字)",
    "remark": "其他需要记录的事项",
}

LONG_OUTSTANDING_FIELDS_SCHEMA: dict[str, str] = {
    "creditor": "债权人名称",
    "closingBalance": "期末应付余额或文件载明金额（数字）",
    "aging": "账龄（1～2年/2～3年/3年以上；文件未明确则空）",
    "businessDescription": "经济业务或款项性质说明",
    "unsettledReason": "未偿还或未结转的原因",
    "unableToPay": "是否无法支付（是/否/不适用；仅在文件明确时填写）",
    "litigation": "是否涉及诉讼（是/否/不适用；仅在文件明确时填写）",
    "paymentPlan": "支付计划、预计支付日期或分期安排",
    "auditedAmount": "经确认/对账/判决等支持的审定金额（数字）",
    "supportingEvidence": "支持性证据名称、编号及关键结论",
    "remark": "其他需要记录的事项",
}

UNRECORDED_PAYMENT_WINDOW_SCHEMA = {
    "supplierName": "供应商名称",
    "openingBalance": "期初余额（数字）",
    "currentDebit": "本期借方发生额（数字）",
    "currentCredit": "本期贷方发生额（数字）",
    "postPaymentAmount": "期后付款金额（数字）",
    "withinAverageDays": "期后付款是否在平均付款天数内（是/否；仅在文件明确时填写）",
    "remark": "付款日期、银行回单号或其他关键核对说明",
}

UNRECORDED_ESTIMATED_INBOUND_SCHEMA = {
    "receiptDate": "入库单/验收单日期（YYYY-MM-DD）",
    "receiptNo": "入库单/验收单编号",
    "quantity": "入库数量（数字）",
    "contractUnitPrice": "合同不含税单价（数字，不得把含税价当作不含税价）",
    "estimatedAmount": "文件明确记载的暂估金额（数字）",
    "voucherDate": "暂估入账记账凭证日期（YYYY-MM-DD）",
    "voucherNo": "暂估入账记账凭证编号",
    "voucherAmount": "记账凭证金额（数字）",
    "shouldAdjust": "文件明确的是否应调整结论（是/否；无则空）",
    "remark": "货物名称、合同号或其他关键说明",
}

UNRECORDED_UNPROCESSED_INVOICE_SCHEMA = {
    "invoiceDate": "购货发票日期（YYYY-MM-DD）",
    "invoiceNo": "购货发票编号",
    "quantity": "发票数量（数字）",
    "invoiceContent": "发票货物或服务内容",
    "amount": "发票金额（数字）",
    "supplierName": "供应商名称",
    "shouldIncludeReportPeriod": "是否应计入报告期（是/否；仅在文件明确时填写）",
    "reportPeriodAmount": "文件明确应计入报告期的金额（数字）",
    "remark": "合同、入库、验收或服务期间等关键说明",
}

UNRECORDED_SUBSEQUENT_PAYMENT_SCHEMA = {
    "voucherDate": "期后付款记账凭证日期（YYYY-MM-DD）",
    "voucherNo": "期后付款记账凭证编号",
    "bankDocumentDate": "银行付款凭单/回单日期（YYYY-MM-DD）",
    "bankDocumentNo": "银行付款凭单/回单编号或流水号",
    "amount": "付款金额（数字）",
    "supplierName": "供应商/收款方名称",
    "shouldIncludeReportPeriod": "相关负债是否应计入报告期（是/否；仅在文件明确时填写）",
    "reportPeriodAmount": "文件明确应计入报告期的金额（数字）",
    "remark": "摘要、付款用途或其他关键说明",
}

UNRECORDED_SUBSEQUENT_INCREASE_SCHEMA = {
    "voucherDate": "期后应付增加记账凭证日期（YYYY-MM-DD）",
    "voucherNo": "记账凭证编号",
    "purchaseInvoiceDate": "购货发票日期（YYYY-MM-DD）",
    "purchaseInvoiceNo": "购货发票编号",
    "amount": "应付增加或发票金额（数字）",
    "supplierName": "供应商名称",
    "shouldIncludeReportPeriod": "是否应计入报告期（是/否；仅在文件明确时填写）",
    "reportPeriodAmount": "文件明确应计入报告期的金额（数字）",
    "remark": "货物/服务内容、入库验收或其他关键说明",
}

DOCUMENT_SCHEMAS: dict[str, dict[str, str]] = {
    "long-outstanding": LONG_OUTSTANDING_FIELDS_SCHEMA,
    "unrecorded-payment-window": UNRECORDED_PAYMENT_WINDOW_SCHEMA,
    "unrecorded-estimated-inbound": UNRECORDED_ESTIMATED_INBOUND_SCHEMA,
    "unrecorded-unprocessed-invoice": UNRECORDED_UNPROCESSED_INVOICE_SCHEMA,
    "unrecorded-subsequent-payment": UNRECORDED_SUBSEQUENT_PAYMENT_SCHEMA,
    "unrecorded-subsequent-increase": UNRECORDED_SUBSEQUENT_INCREASE_SCHEMA,
    "voucher": VOUCHER_FIELDS_SCHEMA,
    "approval": APPROVAL_FIELDS_SCHEMA,
    "bank-receipt": BANK_RECEIPT_FIELDS_SCHEMA,
    "goods-receipt": GOODS_RECEIPT_FIELDS_SCHEMA,
    "invoice": INVOICE_FIELDS_SCHEMA,
    "supplier-financing": SUPPLIER_FINANCING_FIELDS_SCHEMA,
}

DOCUMENT_CONTEXTS = {
    "long-outstanding": "长期挂账应付账款支持性证据",
    "unrecorded-payment-window": "供应商明细账、期后付款凭证、银行回单或对账单",
    "unrecorded-estimated-inbound": "入库单、验收单、采购合同和暂估入账记账凭证",
    "unrecorded-unprocessed-invoice": "截止现场结束日未处理的供应商发票及入库验收资料",
    "unrecorded-subsequent-payment": "期后付款记账凭证、银行付款凭单或银行回单",
    "unrecorded-subsequent-increase": "期后应付增加记账凭证、购货发票及入库验收资料",
    "voucher": "应付账款记账凭证",
    "approval": "付款审批单/付款申请单",
    "bank-receipt": "银行回单/电子回单",
    "goods-receipt": "入库单/验收单/到货单",
    "invoice": "增值税发票/采购发票",
    "supplier-financing": "供应链融资平台明细、融资合同、放款回单或债权转让凭证",
}

NUMERIC_FIELDS = {
    "closingBalance", "auditedAmount", "openingBalance", "currentDebit", "currentCredit",
    "postPaymentAmount", "quantity", "contractUnitPrice", "estimatedAmount",
    "voucherAmount", "amount", "reportPeriodAmount", "bankAmount", "receiptQty", "invoiceAmount",
    "financingAmount", "purchaseAmount", "loanBalance",
}


class F4EvidenceOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float


def _empty_fields(schema: dict[str, str]) -> dict:
    return {key: 0 if key in NUMERIC_FIELDS else "" for key in schema}


def _system_prompt(schema: dict[str, str], document_type: str) -> str:
    return (
        "你是注册会计师团队的应付账款证据提取助手。"
        f"当前材料属于：{DOCUMENT_CONTEXTS[document_type]}。"
        "只能提取文件中明确出现的事实，不得推测交易归属期间、债务是否灭失或是否应作审计调整。"
        "日期、编号、供应商和金额必须保持同一张单据的对应关系，禁止拼接不同交易。"
        "严格返回JSON；不确定的文本字段填空字符串，金额填0。\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
    )


def _parse_llm_json(result: str) -> dict:
    text = result.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


@router.post("/api/workpapers/{wp_id}/f4/contract-ocr")
async def f4_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    document_type: str = Form("long-outstanding"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F4EvidenceOcrResponse:
    """识别F4-5/F4-7/F4-8/F4-9附件并返回待用户预览、编辑和确认的字段。"""
    del db, current_user
    schema = DOCUMENT_SCHEMAS.get(document_type)
    if schema is None:
        raise HTTPException(400, f"不支持的F4文档类型: {document_type}")

    allowed_types = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed_types}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "accounts-payable"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{attachment_id}{suffix}"
    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as target:
        await target.write(content)

    empty_fields = _empty_fields(schema)
    try:
        ocr_result = await UnifiedOCRService().recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as exc:
        logger.warning("F4 evidence OCR failed for %s/%s: %s", wp_id, document_type, exc)
        return F4EvidenceOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=empty_fields,
            confidence=0,
        )

    if not ocr_text.strip():
        return F4EvidenceOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=empty_fields,
            confidence=0,
        )

    extracted = dict(empty_fields)
    confidence = 0.0
    try:
        result = await chat_completion(
            messages=[
                {"role": "system", "content": _system_prompt(schema, document_type)},
                {"role": "user", "content": f"OCR文本：\n{ocr_text[:7000]}"},
            ],
            temperature=0.1,
            max_tokens=1800,
        )
        if isinstance(result, str):
            parsed = _parse_llm_json(result)
            for key in schema:
                if key in parsed and parsed[key] is not None:
                    extracted[key] = parsed[key]
            filled = sum(1 for value in extracted.values() if value not in ("", 0, None))
            confidence = round(filled / len(schema), 2)
    except Exception as exc:
        logger.warning("F4 evidence extraction failed for %s/%s: %s", wp_id, document_type, exc)

    return F4EvidenceOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted,
        confidence=confidence,
    )
