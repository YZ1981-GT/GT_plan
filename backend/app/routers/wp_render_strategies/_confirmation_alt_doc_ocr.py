"""函证替代程序 — 按单据类型识别行内单据（spec attachment-confirmation-evidence-loop 需求 3，ADR-ACE-03）。

POST /api/workpapers/{wp_id}/confirmation-alternative/doc-ocr
表单：file、document_type（下表六类）、attachment_id?、force_reocr?，以及 Spec B 的 evidence_type / evidence_sheet / evidence_cell
（替代程序页传 表页 = 页编码、单元格 = ``row:{行 id}``，附件只挂到本行）。

改造前：H0-5 / K0-5 / K0-6 / G0-6 借 ``d4/contract-ocr``（合同字段）识别回款单、对账单、发票，前端映射键与合同字段对不上，
几乎从不填入；L0-5 的识别地址缺底稿 id。这里按单据类型给出各自字段，前端按「表头分组 | 列名」填入本行空白列。
识别引擎与大模型的用法照 ``_f4_contract_ocr.py``：先建附件再识别，识别失败也写回附件（状态「识别失败」）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.attachment_ocr_writeback import finalize_linked_ocr_writeback, parse_optional_uuid
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService
from app.services.workpaper_evidence_intake import (
    OcrIntakeOptions,
    intake_ocr_upload,
    ocr_intake_options,
    parse_workpaper_id,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["confirmation-alternative-ai"])

#: 单据类型 → 字段（键与前端 ``alternativeDocMapping.ts`` 的映射值一致，守卫读本文件比对）
DOCUMENT_SCHEMAS: dict[str, dict[str, str]] = {
    "bank_receipt": {
        "date": "回单 / 交易日期（YYYY-MM-DD）",
        "doc_no": "回单编号或交易流水号",
        "payer": "付款方（付款人）名称",
        "payee": "收款方（收款人）名称",
        "amount": "金额（数字）",
        "summary": "摘要 / 用途",
    },
    "invoice": {
        "date": "开票日期（YYYY-MM-DD）",
        "doc_no": "发票号码",
        "seller": "销售方名称",
        "buyer": "购买方名称",
        "amount": "价税合计金额（数字）",
        "product": "货物或应税劳务、服务名称",
    },
    "shipping": {
        "date": "单据日期（YYYY-MM-DD）",
        "doc_no": "单据编号（出库单 / 运输单 / 签收单 / 入库单 / 验收单号）",
        "product": "品名 / 资产名称",
        "spec": "规格型号",
        "unit": "计量单位",
        "qty": "数量（数字）",
        "amount": "单据载明或确认的金额（数字）",
        "keeper": "仓库保管员",
        "shipper": "发货人",
        "carrier": "运输公司 / 承运人",
        "address": "运输地址 / 收货地址",
        "signer": "签收人",
        "stamp_type": "盖章类型（公章 / 收货专用章 / 合同章等）",
        "stamp_entity": "盖章单位名称",
        "sign_info": "签字、签章信息摘要",
    },
    "statement": {
        "date": "对账单日期 / 截止日（YYYY-MM-DD）",
        "counterparty": "对方单位 / 开户机构名称",
        "variety": "证券或产品名称（持仓品种）",
        "qty": "持仓数量（数字）",
        "market_value": "市值（数字）",
        "counterparty_balance": "对方记录的余额（数字）",
        "own_balance": "本方（被审计单位）记录的余额（数字）",
        "trade_date": "交易确认 / 交割日期（YYYY-MM-DD）",
        "trade_qty": "成交数量（数字）",
        "trade_price": "成交价（数字）",
        "trade_amount": "成交金额（数字）",
        "fee": "手续费等交易费用（数字）",
        "net_amount": "净收入 / 净额（数字）",
    },
    "contract": {
        "date": "签订日期（YYYY-MM-DD）",
        "doc_no": "合同 / 协议 / 借据编号",
        "counterparty": "对方单位名称",
        "amount": "合同 / 协议金额（数字）",
        "term": "期限（借款期限 / 租赁期等）",
        "ratio": "比例（预收 / 预付 / 投资比例等，原文照录）",
        "terms": "主要条款摘要",
    },
    "voucher": {
        "date": "凭证日期（YYYY-MM-DD）",
        "doc_no": "凭证编号",
        "summary": "摘要 / 业务内容",
        "counter_account": "对方科目",
        "detail_account": "明细科目",
        "amount": "金额（数字）",
        "product": "品名",
        "qty": "数量（数字）",
    },
}

DOCUMENT_CONTEXTS: dict[str, str] = {
    "bank_receipt": "银行回单 / 回款单 / 电子回单",
    "invoice": "增值税发票 / 销售或采购发票",
    "shipping": "出库单、运输单、签收单、入库单、验收单等发运 / 物流单据",
    "statement": "证券账户对账单、持仓证明、交割单或往来对账单",
    "contract": "合同、协议、借据或抵押 / 担保 / 租赁合同",
    "voucher": "记账凭证",
}

#: 单据类型 → 附件缺省证据类型（请求带了 evidence_type 就用请求的）
DOCUMENT_EVIDENCE_TYPES: dict[str, str] = {
    "bank_receipt": "voucher",
    "invoice": "voucher",
    "shipping": "voucher",
    "statement": "support",
    "contract": "contract",
    "voucher": "voucher",
}

NUMERIC_FIELDS = frozenset({
    "amount", "qty", "market_value", "counterparty_balance", "own_balance",
    "trade_qty", "trade_price", "trade_amount", "fee", "net_amount",
})

_ALLOWED_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg")


class AltDocOcrResponse(BaseModel):
    attachment_id: str
    document_type: str
    ocr_text: str
    extracted_fields: dict
    confidence: float
    reused: bool = False
    written_back: bool = False
    governed: bool = False
    requires_human_confirmation: bool = True


def _empty_fields(schema: dict[str, str]) -> dict:
    return {key: 0 if key in NUMERIC_FIELDS else "" for key in schema}


def _system_prompt(document_type: str) -> str:
    return (
        "你是注册会计师团队的函证替代程序证据提取助手。"
        f"当前单据属于：{DOCUMENT_CONTEXTS[document_type]}。"
        "只提取单据上明确出现的事实，不得推测，不得把不同单据或不同交易的信息拼在一起。"
        "日期统一为 YYYY-MM-DD；严格返回 JSON；不确定的文本字段填空字符串，数值填 0。\n"
        f"{json.dumps(DOCUMENT_SCHEMAS[document_type], ensure_ascii=False, indent=2)}"
    )


def _parse_llm_json(result: str) -> dict:
    text = result.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _resp(attachment_id: str, document_type: str, ocr_text: str, fields: dict, confidence: float,
          *, reused: bool = False, written_back: bool = False) -> AltDocOcrResponse:
    return AltDocOcrResponse(
        attachment_id=attachment_id, document_type=document_type, ocr_text=ocr_text,
        extracted_fields=fields, confidence=confidence, reused=reused, written_back=written_back,
    )


@router.post("/api/workpapers/{wp_id}/confirmation-alternative/doc-ocr")
async def confirmation_alternative_doc_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    attachment_id: str | None = Form(None),
    force_reocr: bool = Form(False),
    options: OcrIntakeOptions = Depends(ocr_intake_options),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AltDocOcrResponse:
    """识别替代程序行内的单据，返回该类单据的字段（待用户逐项确认后只填入本行空白列）。"""
    wp_uuid = parse_workpaper_id(wp_id)
    schema = DOCUMENT_SCHEMAS.get(document_type)
    if schema is None:
        raise HTTPException(400, f"不支持的单据类型：{document_type}")
    if parse_optional_uuid(attachment_id) is None:
        suffix = Path(file.filename or "upload.pdf").suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise HTTPException(400, f"不支持的文件类型：{suffix}，仅支持 PDF / PNG / JPG")
    if isinstance(options, OcrIntakeOptions) and not options.evidence_type:
        options.evidence_type = DOCUMENT_EVIDENCE_TYPES[document_type]

    empty = _empty_fields(schema)
    src = await intake_ocr_upload(
        db, wp_id=wp_uuid, file=file, attachment_id=attachment_id, force_reocr=force_reocr,
        user=current_user, native_type=DOCUMENT_EVIDENCE_TYPES[document_type], native_prefix="", options=options,
    )
    if src.reused is not None:
        stored = src.reused.get("extracted_fields") or {}
        merged = {**empty, **{k: stored[k] for k in schema if k in stored}}
        return _resp(str(src.attachment_id), document_type, src.reused["ocr_text"], merged,
                     float(src.reused.get("confidence") or 0), reused=True)

    temp_id = str(src.attachment_id)
    try:
        ocr_result = await UnifiedOCRService().recognize(str(src.path))
        ocr_text = str(ocr_result.get("text", "") or "")
    except Exception as exc:  # noqa: BLE001 — 识别失败如实写回附件（状态「识别失败」），不阻断回执
        logger.warning("替代程序单据识别失败 wp=%s type=%s: %s", wp_id, document_type, exc)
        ocr_text = ""

    if not ocr_text.strip():
        out_id, written = await finalize_linked_ocr_writeback(
            db, wp_id=wp_uuid, linked_att_id=src.attachment_id, temp_id=temp_id,
            ocr_text="", extracted_fields=empty, confidence=0.0,
        )
        return _resp(out_id, document_type, "", empty, 0.0, written_back=written)

    extracted = dict(empty)
    confidence = 0.0
    try:
        result = await chat_completion(
            messages=[
                {"role": "system", "content": _system_prompt(document_type)},
                {"role": "user", "content": f"OCR文本：\n{ocr_text[:7000]}"},
            ],
            temperature=0.1,
            max_tokens=1500,
        )
        if isinstance(result, str):
            parsed = _parse_llm_json(result)
            for key in schema:
                if parsed.get(key) is not None:
                    extracted[key] = parsed[key]
            filled = sum(1 for value in extracted.values() if value not in ("", 0, None))
            confidence = round(filled / len(schema), 2)
    except Exception as exc:  # noqa: BLE001 — 抽取失败只返回空字段，全文仍写回附件
        logger.warning("替代程序单据字段抽取失败 wp=%s type=%s: %s", wp_id, document_type, exc)

    out_id, written = await finalize_linked_ocr_writeback(
        db, wp_id=wp_uuid, linked_att_id=src.attachment_id, temp_id=temp_id,
        ocr_text=ocr_text, extracted_fields=extracted, confidence=confidence,
    )
    return _resp(out_id, document_type, ocr_text, extracted, confidence, written_back=written)
