"""F1 预付账款 — 导入导出（列结构对齐 HTML 底稿）."""

from __future__ import annotations

import io
import json
import logging
from typing import Any, Callable, Iterable, Sequence
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    col_val,
    import_rows_generic,
    load_json_rows,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_rows,
    workbook_to_response,
)
from ._cycle_import_export_common import (
    match_import_aging,
    resolve_aging_segments,
    subject_aging_periods,
    aging_export_values,
    build_aging_headers,
)
from ._d3_import_export import (
    _D3_2_BASE_HEADERS,
    _export_d3_2_row,
    _export_d3_5_row,
    _export_d3_6_row,
    _export_d3_7_row,
    _get_headers as _d3_get_headers,
    _parse_d3_2_row,
    _parse_d3_5_row,
    _parse_d3_6_row,
    _parse_d3_7_row,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f1-import-export"])

# F1-2 基础列（与 D3-2 同结构；账龄另按 F1 三期动态追加）
_F1_2_BASE_HEADERS: list[str] = list(_D3_2_BASE_HEADERS)


def _f1_2_dynamic_headers(segments: list[Any]) -> list[str]:
    """F1-2：基础列 + 3N 账龄列（期初/期末未审/期末审定）。"""
    return _F1_2_BASE_HEADERS + build_aging_headers(segments, subject_aging_periods("F1"))


def _export_f1_2_row_dynamic(data: dict, segments: list[Any]) -> list:
    base = [
        safe_str(data.get("customerName")),
        safe_str(data.get("companyCode")),
        safe_str(data.get("nature")),
        safe_str(data.get("relationType")),
        safe_float(data.get("priorUnadjusted")),
        safe_float(data.get("priorAdjustment")),
        safe_float(data.get("priorReclass")),
        safe_float(data.get("debit")),
        safe_float(data.get("credit")),
        safe_float(data.get("entityReclass")),
        safe_float(data.get("endAje")),
        safe_float(data.get("endRje")),
        safe_str(data.get("isConfirmed")),
        safe_float(data.get("postPeriodSettlement")),
        safe_str(data.get("remark")),
    ]
    return base + aging_export_values(data, segments, subject_aging_periods("F1"))


def _parse_f1_2_row(row: tuple, actual_headers: list[str], segments: list[Any] | None = None) -> dict:
    """解析 F1-2：支持「债权人名称」别名，账龄按 F1 三期匹配。"""
    parsed = _parse_d3_2_row(row, actual_headers, None)
    # 债权人名称 / 期后回款 / 是否函证 别名
    creditor = safe_str(col_val(row, actual_headers, "债权人名称"))
    if creditor and not parsed.get("customerName"):
        parsed["customerName"] = creditor
    post_pay = col_val(row, actual_headers, "期后回款")
    if post_pay is not None and post_pay != "":
        parsed["postPeriodSettlement"] = safe_float(post_pay)
    confirmed = safe_str(col_val(row, actual_headers, "是否函证"))
    if confirmed:
        parsed["isConfirmed"] = confirmed

    if segments:
        aging_nested, _unmatched = match_import_aging(
            lambda h: col_val(row, actual_headers, h),
            actual_headers,
            segments,
            subject_aging_periods("F1"),
        )
        parsed.update(aging_nested)
    return parsed


_F1_5_HEADERS = [
    "债务人名称",
    "期末余额",
    "账龄",
    "经济业务说明",
    "未偿还或未结转的原因",
    "计划供货还是退款",
    "是否诉讼",
    "是否转入其他应收款",
    "计提坏账准备金额",
    "审定余额",
    "期后供货或退款金额",
    "支持性证据",
    "备注",
]


def _export_f1_5_row(data: dict) -> list:
    end_balance = safe_float(data.get("endBalance"))
    bad_debt = safe_float(data.get("badDebtProvision"))
    audited = data.get("auditedBalance")
    if audited is None or audited == "":
        audited = end_balance - bad_debt
    return [
        safe_str(data.get("customerName")),
        end_balance,
        safe_str(data.get("aging")),
        safe_str(data.get("businessDescription")),
        safe_str(data.get("reason") or data.get("unsettledReason")),
        safe_str(data.get("plan")),
        safe_str(data.get("isLitigation")),
        safe_str(data.get("transferToOtherReceivable")),
        bad_debt,
        safe_float(audited),
        safe_float(
            data.get("postSettlementAmount")
            if data.get("postSettlementAmount") is not None
            else data.get("settlementAmount", data.get("settledAmount"))
        ),
        safe_str(data.get("supportingEvidence")),
        safe_str(data.get("remark")),
    ]


def _parse_f1_5_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 F1-5：支持 Excel 13 列及旧版 8 列别名。"""
    name = safe_str(col_val(row, actual_headers, "债务人名称")) or safe_str(
        col_val(row, actual_headers, "对方单位名称")
    )
    end_balance = safe_float(col_val(row, actual_headers, "期末余额"))
    bad_debt = safe_float(col_val(row, actual_headers, "计提坏账准备金额"))
    audited_raw = col_val(row, actual_headers, "审定余额")
    audited = safe_float(audited_raw) if audited_raw not in (None, "") else end_balance - bad_debt

    reason = safe_str(col_val(row, actual_headers, "未偿还或未结转的原因")) or safe_str(
        col_val(row, actual_headers, "未结转或未偿还的原因")
    )
    plan = safe_str(col_val(row, actual_headers, "计划供货还是退款")) or safe_str(
        col_val(row, actual_headers, "处理计划")
    )
    post = col_val(row, actual_headers, "期后供货或退款金额")
    if post in (None, ""):
        post = col_val(row, actual_headers, "至审计日结转或偿还金额")

    return {
        "rowId": str(uuid4()),
        "customerName": name,
        "endBalance": end_balance,
        "aging": safe_str(col_val(row, actual_headers, "账龄")),
        "businessDescription": safe_str(col_val(row, actual_headers, "经济业务说明")),
        "reason": reason,
        "plan": plan,
        "isLitigation": safe_str(col_val(row, actual_headers, "是否诉讼")),
        "transferToOtherReceivable": safe_str(col_val(row, actual_headers, "是否转入其他应收款")),
        "badDebtProvision": bad_debt,
        "auditedBalance": audited,
        "postSettlementAmount": safe_float(post),
        "supportingEvidence": safe_str(col_val(row, actual_headers, "支持性证据")),
        "remark": safe_str(col_val(row, actual_headers, "备注")),
    }


_F1_6_HEADERS = [
    "关联方名称",
    "关联关系",
    "期初余额",
    "借方发生额",
    "贷方发生额",
    "期末余额",
    "减：坏账准备",
    "账面价值",
    "发生时间及账龄",
    "发生原因（款项性质）",
    "期后到货",
    "索引号",
    "备注",
]


def _export_f1_6_row(data: dict) -> list:
    prior = safe_float(data.get("priorBalance"))
    debit = safe_float(data.get("debit"))
    credit = safe_float(data.get("credit"))
    end_balance = data.get("endBalance")
    if end_balance is None or end_balance == "":
        end_balance = prior + debit - credit
    else:
        end_balance = safe_float(end_balance)
    bad_debt = safe_float(data.get("badDebt") or data.get("badDebtProvision"))
    book = data.get("bookValue")
    if book is None or book == "":
        book = end_balance - bad_debt
    return [
        safe_str(data.get("partyName") or data.get("customerName")),
        safe_str(data.get("relationship")),
        prior,
        debit,
        credit,
        end_balance,
        bad_debt,
        safe_float(book),
        safe_str(data.get("agingDescription")),
        safe_str(data.get("natureDescription") or data.get("nature")),
        safe_float(data.get("postPeriodDelivery") or data.get("postPeriodSettlement")),
        safe_str(data.get("indexRef")),
        safe_str(data.get("remark")),
    ]


def _parse_f1_6_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 F1-6：支持 Excel 13 列及旧版 10 列别名。"""
    prior = safe_float(col_val(row, actual_headers, "期初余额"))
    debit = safe_float(col_val(row, actual_headers, "借方发生额"))
    if debit == 0:
        debit = safe_float(col_val(row, actual_headers, "借方发生"))
    credit = safe_float(col_val(row, actual_headers, "贷方发生额"))
    if credit == 0:
        credit = safe_float(col_val(row, actual_headers, "贷方发生"))
    end_raw = col_val(row, actual_headers, "期末余额")
    end_balance = safe_float(end_raw) if end_raw not in (None, "") else prior + debit - credit
    bad_debt = safe_float(col_val(row, actual_headers, "减：坏账准备"))
    book_raw = col_val(row, actual_headers, "账面价值")
    book = safe_float(book_raw) if book_raw not in (None, "") else end_balance - bad_debt
    nature = (
        safe_str(col_val(row, actual_headers, "发生原因（款项性质）"))
        or safe_str(col_val(row, actual_headers, "发生原因"))
        or safe_str(col_val(row, actual_headers, "款项性质"))
    )

    return {
        "rowId": str(uuid4()),
        "partyName": safe_str(col_val(row, actual_headers, "关联方名称")),
        "relationship": safe_str(col_val(row, actual_headers, "关联关系")),
        "priorBalance": prior,
        "debit": debit,
        "credit": credit,
        "endBalance": end_balance,
        "badDebt": bad_debt,
        "bookValue": book,
        "agingDescription": safe_str(col_val(row, actual_headers, "发生时间及账龄")),
        "natureDescription": nature,
        "postPeriodDelivery": safe_float(col_val(row, actual_headers, "期后到货")),
        "indexRef": safe_str(col_val(row, actual_headers, "索引号"))
        or safe_str(col_val(row, actual_headers, "索引")),
        "remark": safe_str(col_val(row, actual_headers, "备注")),
    }


_SUPPORTED_SHEETS: set[str] = {"F1-2", "F1-5", "F1-6", "F1-7", "F1-7-credit", "F1-7-post"}

_SHEET_ITEM_ID: dict[str, str] = {
    "F1-2": "F1-det-rows",
    "F1-5": "F1-lt-rows",
    "F1-6": "F1-rp-rows",
    "F1-7": "F1-vc-current-rows",
    "F1-7-credit": "F1-vc-credit-rows",
    "F1-7-post": "F1-vc-post-rows",
}

_D3_SHEET_MAP: dict[str, str] = {
    "F1-2": "D3-2",
    "F1-5": "D3-5",
    "F1-6": "D3-6",
}

# F1-7 (1) 本期借方 — 对齐 Excel：记账凭证 + 付款审批 + 银行回单 + 合同
_F1_7_DEBIT_HEADERS = [
    "供应商名称",
    "日期",
    "凭证编号",
    "业务内容",
    "对方科目",
    "对方明细科目",
    "借方金额",
    "付款审批日期/编号",
    "是否审批",
    "银行回单付款",
    "银行回单收款方",
    "银行回单金额",
    "合同名称/合规",
    "合同金额",
    "签收单据",
    "索引号",
    "是否异常",
    "备注",
]

# F1-7 (2)(3) 本期贷方 / 期后 — 入库单 + 发票
_F1_7_CREDIT_HEADERS = [
    "供应商名称",
    "日期",
    "凭证编号",
    "业务内容",
    "对方科目",
    "对方明细科目",
    "贷方金额",
    "入库单日期/编号",
    "品名",
    "单位",
    "数量",
    "发票日期/编号",
    "发票对方单位",
    "发票金额",
    "索引号",
    "是否异常",
    "备注",
]


def _export_f1_7_debit_row(data: dict) -> list:
    return [
        safe_str(data.get("supplierName") or data.get("customerName")),
        safe_str(data.get("date")),
        safe_str(data.get("voucherNo")),
        safe_str(data.get("businessContent")),
        safe_str(data.get("counterAccount")),
        safe_str(data.get("counterDetailAccount")),
        safe_float(data.get("debitAmount")),
        safe_str(data.get("approvalDateNo")),
        safe_str(data.get("approvalOk")),
        safe_str(data.get("bankPayment")),
        safe_str(data.get("bankPayee")),
        safe_float(data.get("bankAmount")),
        safe_str(data.get("contractName")),
        safe_float(data.get("contractAmount")),
        safe_str(data.get("receiptDoc") or data.get("supportingDoc")),
        safe_str(data.get("indexRef")),
        safe_str(data.get("isAbnormal")),
        safe_str(data.get("remark")),
    ]


def _export_f1_7_credit_row(data: dict) -> list:
    return [
        safe_str(data.get("supplierName") or data.get("customerName")),
        safe_str(data.get("date")),
        safe_str(data.get("voucherNo")),
        safe_str(data.get("businessContent")),
        safe_str(data.get("counterAccount")),
        safe_str(data.get("counterDetailAccount")),
        safe_float(data.get("creditAmount")),
        safe_str(data.get("recvDateNo")),
        safe_str(data.get("recvItemName")),
        safe_str(data.get("recvUnit")),
        safe_str(data.get("recvQty")),
        safe_str(data.get("invoiceDateNo")),
        safe_str(data.get("invoiceCounterparty")),
        safe_float(data.get("invoiceAmount")),
        safe_str(data.get("indexRef")),
        safe_str(data.get("isAbnormal")),
        safe_str(data.get("remark") or data.get("supportingDoc")),
    ]


def _parse_f1_7_debit_row(row: tuple, headers: list[str]) -> dict:
    name = safe_str(col_val(row, headers, "供应商名称")) or safe_str(col_val(row, headers, "客户名称"))
    return {
        "rowId": str(uuid4()),
        "supplierName": name,
        "date": safe_str(col_val(row, headers, "日期")),
        "voucherNo": safe_str(col_val(row, headers, "凭证编号")),
        "businessContent": safe_str(col_val(row, headers, "业务内容")),
        "counterAccount": safe_str(col_val(row, headers, "对方科目")),
        "counterDetailAccount": safe_str(col_val(row, headers, "对方明细科目")),
        "debitAmount": safe_float(col_val(row, headers, "借方金额")),
        "approvalDateNo": safe_str(col_val(row, headers, "付款审批日期/编号")),
        "approvalOk": safe_str(col_val(row, headers, "是否审批")),
        "bankPayment": safe_str(col_val(row, headers, "银行回单付款")),
        "bankPayee": safe_str(col_val(row, headers, "银行回单收款方")),
        "bankAmount": safe_float(col_val(row, headers, "银行回单金额")),
        "contractName": safe_str(col_val(row, headers, "合同名称/合规")),
        "contractAmount": safe_float(col_val(row, headers, "合同金额")),
        "receiptDoc": safe_str(col_val(row, headers, "签收单据"))
        or safe_str(col_val(row, headers, "支持性文件")),
        "indexRef": safe_str(col_val(row, headers, "索引号")),
        "isAbnormal": safe_str(col_val(row, headers, "是否异常")),
        "remark": safe_str(col_val(row, headers, "备注"))
        or safe_str(col_val(row, headers, "备注说明")),
    }


def _parse_f1_7_credit_row(row: tuple, headers: list[str]) -> dict:
    name = safe_str(col_val(row, headers, "供应商名称")) or safe_str(col_val(row, headers, "客户名称"))
    return {
        "rowId": str(uuid4()),
        "supplierName": name,
        "date": safe_str(col_val(row, headers, "日期")),
        "voucherNo": safe_str(col_val(row, headers, "凭证编号")),
        "businessContent": safe_str(col_val(row, headers, "业务内容")),
        "counterAccount": safe_str(col_val(row, headers, "对方科目")),
        "counterDetailAccount": safe_str(col_val(row, headers, "对方明细科目")),
        "creditAmount": safe_float(col_val(row, headers, "贷方金额")),
        "recvDateNo": safe_str(col_val(row, headers, "入库单日期/编号")),
        "recvItemName": safe_str(col_val(row, headers, "品名")),
        "recvUnit": safe_str(col_val(row, headers, "单位")),
        "recvQty": safe_str(col_val(row, headers, "数量")),
        "invoiceDateNo": safe_str(col_val(row, headers, "发票日期/编号")),
        "invoiceCounterparty": safe_str(col_val(row, headers, "发票对方单位")),
        "invoiceAmount": safe_float(col_val(row, headers, "发票金额")),
        "indexRef": safe_str(col_val(row, headers, "索引号")),
        "isAbnormal": safe_str(col_val(row, headers, "是否异常")),
        "remark": safe_str(col_val(row, headers, "备注"))
        or safe_str(col_val(row, headers, "备注说明"))
        or safe_str(col_val(row, headers, "支持性文件")),
    }


_SHEET_META: dict[str, dict[str, Any]] = {
    "F1-2": {
        "title": "F1-2 预付账款明细表",
        "guidance": [
            "F1-2 预付账款明细表 编制说明",
            "",
            "列结构与 Excel F1-2 一致：债权人|关联方|款项性质|期初/发生/期末|三期账龄|函证|期后回款等。",
            "期末余额=期初审定+借方-贷方；账龄与期末余额由系统自动校验；期后回款与 F1-7 期后检查联动。",
        ],
    },
    "F1-5": {
        "title": "F1-5 账龄1年及以上大额预付账款检查表",
        "guidance": [
            "F1-5 编制说明",
            "",
            "13列对齐 Excel：债务人|期末余额|账龄|业务说明|未结转原因|计划供货/退款|"
            "是否诉讼|是否转其他应收|坏账准备|审定余额|期后供货退款|支持性证据|备注。",
            "审定余额=期末余额−坏账准备；可从 F1-2 导入超1年户。",
        ],
    },
    "F1-6": {
        "title": "F1-6 预付账款关联方及交易检查表",
        "guidance": [
            "F1-6 编制说明",
            "",
            "13列对齐 Excel：关联方|关系|期初|借方|贷方|期末|坏账准备|账面价值|"
            "发生时间及账龄|款项性质|期后到货|索引号|备注。",
            "期末=期初+借方−贷方；账面价值=期末−坏账准备；可从 F1-2 导入关联方户。",
        ],
    },
    "F1-7": {
        "title": "F1-7 预付账款检查表 — (1) 本期借方核查",
        "guidance": [
            "F1-7 本期借方 编制说明",
            "",
            "对齐 Excel：供应商|凭证|借方金额|付款审批|银行回单|合同/订单|索引|是否异常。",
            "核实预付增加真实性与审批/资金流出证据。",
        ],
    },
    "F1-7-credit": {
        "title": "F1-7 预付账款检查表 — (2) 本期贷方核查",
        "guidance": [
            "F1-7 本期贷方 编制说明",
            "",
            "对齐 Excel：供应商|凭证|贷方金额|入库/验收|发票|索引|是否异常。",
        ],
    },
    "F1-7-post": {
        "title": "F1-7 预付账款检查表 — (3) 期后发生额核查",
        "guidance": [
            "F1-7 期后核查 编制说明",
            "",
            "列结构同本期贷方；与 F1-2 期后结转(Z列)交叉验证。",
        ],
    },
}


def _headers(sheet_code: str) -> list[str]:
    if sheet_code == "F1-7":
        return _F1_7_DEBIT_HEADERS
    if sheet_code in ("F1-7-credit", "F1-7-post"):
        return _F1_7_CREDIT_HEADERS
    if sheet_code == "F1-5":
        return _F1_5_HEADERS
    if sheet_code == "F1-6":
        return _F1_6_HEADERS
    return _d3_get_headers(_D3_SHEET_MAP[sheet_code])


def _validate_sheet(sheet_code: str) -> None:
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}")


def _export_row(sheet_code: str, data: dict) -> list:
    if sheet_code == "F1-7":
        return _export_f1_7_debit_row(data)
    if sheet_code in ("F1-7-credit", "F1-7-post"):
        return _export_f1_7_credit_row(data)
    if sheet_code == "F1-5":
        return _export_f1_5_row(data)
    if sheet_code == "F1-6":
        return _export_f1_6_row(data)
    d3 = _D3_SHEET_MAP.get(sheet_code, "D3-7")
    if d3 == "D3-2":
        return _export_d3_2_row(data)
    if d3 == "D3-5":
        return _export_d3_5_row(data)
    if d3 == "D3-6":
        return _export_d3_6_row(data)
    return _export_d3_7_row(data)


def _parse_row(sheet_code: str, row: tuple, headers: list[str]) -> dict:
    if sheet_code == "F1-7":
        return _parse_f1_7_debit_row(row, headers)
    if sheet_code in ("F1-7-credit", "F1-7-post"):
        return _parse_f1_7_credit_row(row, headers)
    if sheet_code == "F1-5":
        return _parse_f1_5_row(row, headers)
    if sheet_code == "F1-6":
        return _parse_f1_6_row(row, headers)
    d3 = _D3_SHEET_MAP[sheet_code]
    if d3 == "D3-2":
        return _parse_d3_2_row(row, headers)
    if d3 == "D3-5":
        return _parse_d3_5_row(row, headers)
    return _parse_d3_6_row(row, headers)


def _template_meta(sheet: str) -> tuple[str | None, str | None, list[str]]:
    meta = _SHEET_META.get(sheet, {})
    return meta.get("title"), None, meta.get("guidance", [])


@router.post("/api/workpapers/{wp_id}/f1/export-template")
async def f1_export_template(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    # F1-2 明细表：账龄列头按项目账龄配置动态生成（三期：期初/期末未审/期末审定）
    if sheet == "F1-2":
        segments = await _resolve_f1_segments(db, wp_id)
        headers = _f1_2_dynamic_headers(segments)
    else:
        headers = _headers(sheet)
    title, subtitle, guidance = _template_meta(sheet)
    wb = build_workbook_template(sheet, headers, title=title, subtitle=subtitle, guidance=guidance)
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/f1/export-data")
async def f1_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    item_id = _SHEET_ITEM_ID[sheet]
    rows_data = await load_json_rows(db, wp_id, item_id, field="remark")
    title, subtitle, guidance = _template_meta(sheet)
    # F1-2 明细表：账龄列头/值按项目账龄配置动态生成（三期）
    f1_2_segments: list[Any] = []
    if sheet == "F1-2":
        f1_2_segments = await _resolve_f1_segments(db, wp_id)
        headers = _f1_2_dynamic_headers(f1_2_segments)
    else:
        headers = _headers(sheet)
    wb = build_workbook_template(sheet, headers, title=title, subtitle=subtitle, guidance=guidance)
    ws = wb[sheet]
    for d in rows_data:
        if sheet == "F1-2":
            ws.append(_export_f1_2_row_dynamic(d, f1_2_segments))
        else:
            ws.append(_export_row(sheet, d))
    return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/f1/import-data")
async def f1_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _validate_sheet(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")
    header_row = 2 if _SHEET_META.get(sheet, {}).get("title") else 1

    # F1-2 明细表：账龄列按 label 动态匹配当前项目配置（三期），验证仅校验基础列
    f1_2_segments: list[Any] = []
    skipped_columns: list[str] = []
    if sheet == "F1-2":
        f1_2_segments = await _resolve_f1_segments(db, wp_id)
        # 「对方单位名称」与 Excel「债权人名称」二选一即可
        headers = [h for h in _F1_2_BASE_HEADERS if h != "对方单位名称"]
    elif sheet == "F1-5":
        # 新 13 列与旧 8 列共用核心列；名称列二选一
        headers = ["期末余额", "账龄", "经济业务说明", "备注"]
    elif sheet == "F1-6":
        # 新 13 列与旧版共用核心列；关联方名称必填
        headers = ["关联方名称", "关联关系", "期初余额", "期末余额"]
    elif sheet == "F1-7":
        headers = ["日期", "凭证编号", "借方金额"]
    elif sheet in ("F1-7-credit", "F1-7-post"):
        headers = ["日期", "凭证编号", "贷方金额"]
    else:
        headers = _headers(sheet)

    try:
        actual, raw_rows = parse_upload_xlsx(content, headers, header_row=header_row)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "imported_count": 0}
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件")

    if sheet == "F1-2":
        if "对方单位名称" not in actual and "债权人名称" not in actual:
            return {"ok": False, "errors": ["缺少列: 对方单位名称 或 债权人名称"], "imported_count": 0}
        _, skipped_columns = match_import_aging(
            lambda _h: None, actual, f1_2_segments, subject_aging_periods("F1"),
        )
        rows_data, truncated = import_rows_generic(
            raw_rows, actual, [], parse_fn=lambda r, h: _parse_f1_2_row(r, h, f1_2_segments),
        )
    elif sheet == "F1-5":
        if "债务人名称" not in actual and "对方单位名称" not in actual:
            return {"ok": False, "errors": ["缺少列: 债务人名称 或 对方单位名称"], "imported_count": 0}
        rows_data, truncated = import_rows_generic(
            raw_rows, actual, [], parse_fn=lambda r, h: _parse_f1_5_row(r, h),
        )
    elif sheet == "F1-6":
        rows_data, truncated = import_rows_generic(
            raw_rows, actual, [], parse_fn=lambda r, h: _parse_f1_6_row(r, h),
        )
    elif sheet == "F1-7":
        if "供应商名称" not in actual and "客户名称" not in actual:
            return {"ok": False, "errors": ["缺少列: 供应商名称 或 客户名称"], "imported_count": 0}
        rows_data, truncated = import_rows_generic(
            raw_rows, actual, [], parse_fn=lambda r, h: _parse_f1_7_debit_row(r, h),
        )
    elif sheet in ("F1-7-credit", "F1-7-post"):
        if "供应商名称" not in actual and "客户名称" not in actual:
            return {"ok": False, "errors": ["缺少列: 供应商名称 或 客户名称"], "imported_count": 0}
        rows_data, truncated = import_rows_generic(
            raw_rows, actual, [], parse_fn=lambda r, h: _parse_f1_7_credit_row(r, h),
        )
    else:
        rows_data, truncated = import_rows_generic(
            raw_rows, actual, [], parse_fn=lambda r, h: _parse_row(sheet, r, h),
        )
    await upsert_json_rows(db, wp_id, _SHEET_ITEM_ID[sheet], rows_data, field="remark")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows_data), "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    if skipped_columns:
        out["skipped_columns"] = skipped_columns
        out["warnings"] = [
            f"以下账龄列未匹配当前账龄配置，已跳过: {', '.join(skipped_columns)}"
        ]
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# F1 账龄口径解析（表级枚举覆盖 > 项目配置 > 科目默认 THREE_YEAR）
#
# 前端 useF1Detail 支持**表级**账龄枚举覆盖（3年段/5年段/自定义），持久化于
# checklist_responses：
#   - `F1-det-aging-preset`           = THREE_YEAR | FIVE_YEAR | CUSTOM
#   - `F1-det-aging-custom-segments`  = JSON 字符串数组（自定义段标签，2-10 段）
# 导入导出列头必须与前端当前口径一致，否则导出模板列头与行数据 key 不匹配、
# 导入时账龄列按 label 匹配失败被整段跳过。
# ═══════════════════════════════════════════════════════════════════════════════

_F1_AGING_PRESET_ITEM_ID = "F1-det-aging-preset"
_F1_AGING_CUSTOM_ITEM_ID = "F1-det-aging-custom-segments"


def build_f1_custom_segments(labels: Iterable[Any]) -> list[Any]:
    """纯函数：自定义段标签列表 → AgingSegment 列表（key 与前端 `custom-{i}` 一致）。"""
    from app.services.aging_config_service import AgingSegment

    segs: list[Any] = []
    for i, raw in enumerate(labels):
        label = str(raw or "").strip()
        if not label:
            continue
        segs.append(AgingSegment(key=f"custom-{i}", label=label, dayFrom=0, dayTo=None))
        if len(segs) >= 10:
            break
    return segs


async def _resolve_f1_segments(db: AsyncSession, wp_id: str) -> list[Any]:
    """F1 有效账龄段：表级枚举覆盖优先，否则项目级配置（异常兜底 THREE_YEAR）。"""
    from app.services.aging_config_service import AgingPreset, resolve_segments

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id IN (:p, :c)"
            ),
            {"wp_id": wp_id, "p": _F1_AGING_PRESET_ITEM_ID, "c": _F1_AGING_CUSTOM_ITEM_ID},
        )
        raw: dict[str, str] = {r.item_id: (r.remark or "") for r in result.fetchall()}
        preset_raw = (raw.get(_F1_AGING_PRESET_ITEM_ID) or "").strip().upper()
        if preset_raw in ("THREE_YEAR", "FIVE_YEAR"):
            return resolve_segments(AgingPreset(preset_raw), None)
        if preset_raw == "CUSTOM":
            labels = json.loads(raw.get(_F1_AGING_CUSTOM_ITEM_ID) or "[]")
            segs = build_f1_custom_segments(labels if isinstance(labels, list) else [])
            if len(segs) >= 2:
                return segs
            # 自定义段不足 2 段：视为未生效，回退项目配置
    except Exception as e:  # noqa: BLE001 — 表级覆盖读取失败不阻断导入导出
        logger.warning("F1 表级账龄覆盖解析失败 wp_id=%s: %s", wp_id, e)
        try:
            await db.rollback()
        except Exception:
            pass
    return await resolve_aging_segments(db, wp_id, "F1")


# ═══════════════════════════════════════════════════════════════════════════════
# F1-2 明细表 ← tb_aux_balance（科目 1123 预付账款，按往来单位维度归集）
#
# 🔴 与 D3/D5/D6/D7 的历史 aux 导入实现不同：本实现使用 tb_aux_balance 的**真实列**
#   （opening_balance / debit_amount / credit_amount / closing_balance），
#   并遵守两条四表库铁律：
#     ① 数据集版本：经 `get_active_filter` 只取 active dataset（禁裸 is_deleted）；
#     ② aux 维度冗余：同一科目同一余额会在多个 aux_type（如「客户」「成本中心」）
#        各存一份，必须**锁定单一 aux_type** 后再归集，否则金额双算。
#   另：账套里 1123 通常落在子科目（1123.01/1123.03/…），故用前缀匹配而非精确等值。
# ═══════════════════════════════════════════════════════════════════════════════

_AUX_ACCOUNT_PREFIX = "1123"
# 往来单位维度优先关键词（命中则优先作为归集维度）
_AUX_TYPE_PREFERRED_KEYWORDS = ("客户", "供应商", "往来", "单位", "个人", "职员", "员工")


def pick_aux_type(
    candidates: Iterable[tuple[str, int, float]],
) -> str | None:
    """纯函数：从 `(aux_type, 行数, 余额绝对值合计)` 候选中挑唯一归集维度。

    优先含往来单位关键词的维度；其次余额合计更大者；再次行数更多者。
    无候选返回 None。
    """
    items = [(str(t or ""), int(n or 0), float(amt or 0)) for t, n, amt in candidates]
    if not items:
        return None
    preferred = [
        it for it in items
        if any(kw in it[0] for kw in _AUX_TYPE_PREFERRED_KEYWORDS)
    ]
    pool = preferred or items
    pool.sort(key=lambda it: (abs(it[2]), it[1], it[0]), reverse=True)
    return pool[0][0]


def build_f1_detail_rows_from_aux(
    aux_entries: Iterable[Sequence],
    segments: list[Any],
    *,
    row_limit: int = ROW_LIMIT,
    row_id_factory: Callable[[], str] | None = None,
) -> list[dict]:
    """纯函数：1123 辅助余额归集结果 → F1-2 明细行（账龄按当前枚举段，落首段）。

    Args:
        aux_entries: 每项按位置解构为 `(aux_name, opening, debit, credit, closing)`。
        segments: 当前有效账龄段（表级覆盖/项目配置），行内 aging 字段按其 key 建桶。
        row_limit: 行数上限（超出截断）。
        row_id_factory: rowId 工厂（默认 uuid4；单测可注入确定性工厂）。

    账龄不臆造：辅助余额表无账龄维度，故金额整笔落**首段**（通常「1年以内」）并在
    端点返回 message 提示审计师按实际账龄调整（前端 `allocateAging` 可一键改档）。
    """
    make_row_id = row_id_factory or (lambda: str(uuid4()))
    seg_keys = [str(getattr(s, "key", "") or "") for s in segments]
    seg_keys = [k for k in seg_keys if k]
    first_key = seg_keys[0] if seg_keys else "within1"

    def _aging(amount: float) -> dict[str, float]:
        bucket = {k: 0.0 for k in (seg_keys or [first_key])}
        bucket[first_key] = amount
        return bucket

    rows: list[dict] = []
    for entry in list(aux_entries)[:row_limit]:
        name = str(entry[0] or "").strip()
        if not name:
            continue
        opening = safe_float(entry[1])
        debit = safe_float(entry[2])
        credit = safe_float(entry[3])
        closing_raw = safe_float(entry[4])
        end_balance = round(opening + debit - credit, 2)
        # 期末优先用账套 closing（含账套自身结转口径），缺失时用滚存值
        end_unadjusted = closing_raw if abs(closing_raw) > 1e-9 else end_balance
        rows.append({
            "rowId": make_row_id(),
            "customerName": name,
            "companyCode": "",
            "nature": "",
            "relationType": "非关联方",
            "priorUnadjusted": opening,
            "priorAdjustment": 0,
            "priorReclass": 0,
            "priorAudited": opening,
            "agingPrior": _aging(opening),
            "debit": debit,
            "credit": credit,
            "endBalance": end_balance,
            "entityReclass": 0,
            "endUnadjusted": end_unadjusted,
            "agingCurrent": _aging(end_unadjusted),
            "endAje": 0,
            "endRje": 0,
            "endAudited": end_unadjusted,
            "agingAudited": _aging(end_unadjusted),
            "isConfirmed": "",
            "postPeriodSettlement": 0,
            "remark": "由辅助余额表(1123)导入",
        })
    return rows


async def aggregate_f1_detail_rows_from_aux(
    db: AsyncSession,
    project_id: str,
    year: int,
    segments: list[Any],
    *,
    row_limit: int = ROW_LIMIT,
    row_id_factory: Callable[[], str] | None = None,
) -> tuple[list[dict], str | None, int]:
    """可复用入口：tb_aux_balance 1123 按单一 aux_type 归集 → F1-2 行。

    Returns:
        `(rows, aux_type, total_units)`；无数据时 `([], None, 0)`。
        `total_units` 为归集出的往来单位总数（可能 > len(rows)，即被 row_limit 截断）。
    """
    from app.models.audit_platform_models import TbAuxBalance
    from app.services.dataset_query import get_active_filter

    active_filter = await get_active_filter(db, TbAuxBalance.__table__, project_id, year)
    base_where = sa.and_(
        active_filter,
        TbAuxBalance.account_code.like(f"{_AUX_ACCOUNT_PREFIX}%"),
    )

    # ① 先定维度（防 aux_type 冗余双算）
    type_rows = (
        await db.execute(
            sa.select(
                TbAuxBalance.aux_type,
                sa.func.count().label("n"),
                sa.func.coalesce(
                    sa.func.sum(sa.func.abs(sa.func.coalesce(TbAuxBalance.closing_balance, 0))), 0
                ).label("amt"),
            )
            .where(base_where)
            .group_by(TbAuxBalance.aux_type)
        )
    ).fetchall()
    aux_type = pick_aux_type([(r.aux_type, r.n, r.amt) for r in type_rows])
    if not aux_type:
        return [], None, 0

    # ② 锁定维度后按往来单位名称归集
    agg_rows = (
        await db.execute(
            sa.select(
                TbAuxBalance.aux_name,
                sa.func.coalesce(sa.func.sum(TbAuxBalance.opening_balance), 0).label("opening"),
                sa.func.coalesce(sa.func.sum(TbAuxBalance.debit_amount), 0).label("debit"),
                sa.func.coalesce(sa.func.sum(TbAuxBalance.credit_amount), 0).label("credit"),
                sa.func.coalesce(sa.func.sum(TbAuxBalance.closing_balance), 0).label("closing"),
            )
            .where(sa.and_(base_where, TbAuxBalance.aux_type == aux_type))
            .group_by(TbAuxBalance.aux_name)
            .order_by(TbAuxBalance.aux_name)
        )
    ).fetchall()

    entries = [
        (r.aux_name, r.opening, r.debit, r.credit, r.closing) for r in agg_rows
    ]
    rows = build_f1_detail_rows_from_aux(
        entries, segments, row_limit=row_limit, row_id_factory=row_id_factory
    )
    return rows, aux_type, len(entries)


@router.post("/api/workpapers/{wp_id}/f1/import-aux-balance")
async def f1_import_aux_balance(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """从 tb_aux_balance（科目 1123，按往来单位维度）归集导入 F1-2 明细表。

    merge 语义：已存在的往来单位名称不重复导入（手工录入优先，不覆盖）。
    """
    wp_row = (
        await db.execute(
            sa.text(
                "SELECT wp.project_id, p.audit_year "
                "FROM working_paper wp JOIN projects p ON p.id = wp.project_id "
                "WHERE wp.id = :wp_id"
            ),
            {"wp_id": wp_id},
        )
    ).fetchone()
    if not wp_row:
        raise HTTPException(404, "底稿不存在")

    project_id = str(wp_row.project_id)
    year = int(wp_row.audit_year or 0)

    segments = await _resolve_f1_segments(db, wp_id)
    rows_data, aux_type, total_units = await aggregate_f1_detail_rows_from_aux(
        db, project_id, year, segments
    )

    if not rows_data:
        return {
            "ok": True,
            "imported_count": 0,
            "rows": [],
            "message": "未找到科目1123的辅助余额数据",
        }

    item_id = _SHEET_ITEM_ID["F1-2"]
    existing_rows = await load_json_rows(db, wp_id, item_id, field="remark")
    existing_names = {
        str((r or {}).get("customerName", "")).strip() for r in existing_rows
    }
    new_rows = [r for r in rows_data if r["customerName"] not in existing_names]
    merged = list(existing_rows) + new_rows

    await upsert_json_rows(db, wp_id, item_id, merged, field="remark")

    first_label = ""
    if segments:
        first_label = str(getattr(segments[0], "label", "") or "")
    truncated = total_units > len(rows_data)
    msg = (
        f"从辅助余额表(1123·{aux_type})归集 {total_units} 个往来单位，"
        f"新增 {len(new_rows)} 行；账龄已整笔落「{first_label}」，请按实际账龄调整。"
    )
    out: dict[str, Any] = {
        "ok": True,
        "imported_count": len(new_rows),
        "total_rows": len(merged),
        "total_units": total_units,
        "aux_type": aux_type,
        "rows": new_rows,
    }
    if truncated:
        out["truncated"] = True
        msg += f" 超过 {len(rows_data)} 行上限已截断，请按重要性补录其余单位。"
    out["message"] = msg
    return out
