"""F3 应付票据 — 导入导出（remark 字段对齐 D4/HTML composable）."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    export_row_by_keys,
    import_rows_generic,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    upsert_json_rows,
    workbook_to_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f3-import-export"])

_STORAGE_FIELD = "remark"

# sheet → spec
_F3_SPECS: dict[str, dict[str, Any]] = {
    "F3-2": {
        "item_id": "F3-2-rows",
        "title": "F3-2 期末应付票据明细表（源表宽表）",
        "headers": [
            "序号", "票据号", "票据类别", "关联方类型", "出票人", "承兑人", "收款人",
            "出票日", "到期日", "期限(天)", "到期账龄", "票面利率(%)", "是否承兑", "是否逾期", "逾期天数",
            "期初余额", "本期开票", "本期承兑", "期末未审数", "账项调整", "重分类调整", "期末审定数",
            "已计利息", "是否函证", "票据保证金比例(%)", "保证金金额", "备注",
        ],
        "field_keys": [
            "seq", "ticketNo", "noteType", "relatedPartyType", "drawer", "acceptor", "payee",
            "issueDate", "dueDate", "termDays", "maturityBucket", "interestRate", "isAccepted", "isOverdue", "overdueDays",
            "openingBalance", "currentIssued", "currentAccepted", "closingUnadjusted", "aje", "rje", "closingAdjusted",
            "accruedInterest", "isConfirmed", "depositRate", "depositAmount", "remark",
        ],
        "guidance": [
            "F3-2 明细表 编制说明",
            "",
            "1. 票据类别：银行承兑汇票/商业承兑汇票/供应链票据/其他。",
            "2. 关联方类型、是否承兑、是否函证使用系统枚举。",
            "3. 期限、到期账龄、是否逾期、逾期天数、期末未审数和期末审定数为公式列，导入后由系统重算。",
            "4. 期末未审数=期初余额+本期开票-本期承兑；期末审定数=期末未审数+账项调整+重分类调整。",
            "5. 保证金金额应与其他货币资金保证金核对。",
        ],
    },
    "F3-3": {
        "item_id": "F3-3-rows",
        "title": "F3-3 调整分录汇总表",
        "headers": ["序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方金额", "贷方金额", "编制人", "备注"],
        "field_keys": ["seq", "entryType", "date", "summary", "accountCode", "accountName", "debitAmount", "creditAmount", "preparer", "remark"],
        "guidance": ["F3-3 调整分录 编制说明", "", "分录类型填 AJE 或 RJE。"],
    },
    "F3-4": {
        "item_id": "F3-4-rows",
        "title": "F3-4 应付票据（带息）利息测算表",
        "headers": [
            "序号", "票据类别", "票据号", "出票日", "到期日", "期限(天)",
            "票面金额", "票面利率(%)", "应计利息", "账面已计利息", "差异", "说明",
        ],
        "field_keys": [
            "seq", "noteType", "ticketNo", "issueDate", "dueDate", "termDays",
            "faceValue", "interestRate", "payableInterest", "bookInterest", "variance", "note",
        ],
        "guidance": [
            "F3-4 应付票据（带息）利息测算表 编制说明",
            "",
            "1. 票据类别填：银行承兑汇票 / 商业承兑汇票 / 供应链票据 / 其他。",
            "2. 日期格式 YYYY-MM-DD；期限(天)、应计利息、差异为公式列，导入后自动重算。",
            "3. 应计利息 = 票面金额 × 票面利率% × 期限 / 360；差异 = 应计利息 − 账面已计利息。",
        ],
    },
    "F3-5": {
        "item_id": "F3-5-rows",
        "title": "F3-5 逾期未付票据检查表",
        "headers": [
            "序号", "票据类别", "票据号", "出票人", "承兑人", "收款人", "出票日", "到期日",
            "期限(天)", "票面利率(%)", "票面金额", "期后支付金额", "借款条件", "是否调整",
            "抵押物品名称", "抵押金额",
        ],
        "field_keys": [
            "seq", "noteType", "ticketNo", "drawer", "acceptor", "payee", "issueDate", "dueDate",
            "termDays", "interestRate", "faceValue", "postPaymentAmount", "loanConditions", "isAdjusted",
            "collateralName", "collateralAmount",
        ],
        "guidance": [
            "F3-5 逾期未付票据检查表 编制说明",
            "",
            "1. 票据类别填：银行承兑汇票 / 商业承兑汇票 / 供应链票据 / 其他。",
            "2. 日期格式 YYYY-MM-DD；期限(天)由系统按到期日减出票日自动重算。",
            "3. 是否调整填：是 / 否 / 不适用；期后支付应取得银行回单或兑付凭证。",
            "4. 借款条件列填写追索权、罚息、加速到期、交叉违约等条款；抵押情况分名称和金额填写。",
        ],
    },
    "F3-6": {
        "item_id": "F3-6-rows",
        "title": "F3-6 应付票据关联方及交易检查表",
        "headers": [
            "序号", "关联方名称", "关联关系", "票据类别", "期初余额", "借方发生", "贷方发生",
            "期末余额", "账龄", "定价政策", "发生原因（款项性质）", "期后付款金额", "索引号", "备注",
        ],
        "field_keys": [
            "seq", "partyName", "relationship", "noteType", "openingBalance", "debitMovement", "creditMovement",
            "closingBalance", "aging", "pricingPolicy", "transactionReason", "subsequentPaymentAmount", "indexNo", "remark",
        ],
        "guidance": [
            "F3-6 应付票据关联方及交易检查表 编制说明",
            "",
            "1. 关联关系填：实际控制人 / 控股股东 / 控股股东、实际控制人的附属企业 / "
            "持有5%以上股份的法人或其他组织 / 联营企业 / 合营企业 / 董高监等关键管理人员 / 其他关联方。",
            "2. 期末余额为公式列：期初余额 + 贷方发生 - 借方发生，导入后由系统自动重算。",
            "3. 账龄填：1年以内 / 1至2年 / 2至3年 / 3年以上。",
            "4. 定价政策填市场定价、协议定价、成本加成、参考第三方价格或其他，并说明款项性质。",
        ],
    },
    "F3-7-debit": {
        "item_id": "F3-7-debit-rows",
        "title": "F3-7 本期借方金额检查",
        "headers": [
            "序号", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "借方金额", "票据类别",
            "付款审批单日期/编号", "是否经过恰当审批", "银行回单日期", "收款方", "回单金额",
            "其他证据", "索引号", "是否异常", "异常/检查说明",
        ],
        "field_keys": [
            "seq", "voucherDate", "voucherNo", "businessContent", "counterAccount", "detailAccount",
            "amount", "noteType", "approvalDateNo", "approvalProper", "bankReceiptDate", "bankPayee",
            "bankAmount", "otherEvidence", "indexNo", "isAbnormal", "issueDesc",
        ],
        "guidance": [
            "F3-7 本期借方金额检查 编制说明", "",
            "1. 科目2201借方发生（票据减少：到期兑付/背书转让），逐笔核对记账凭证、付款审批单、银行回单。",
            "2. 是否经过恰当审批填：是 / 否；是否异常填：是 / 否。",
            "3. 回单金额与凭证金额不符时系统标记勾稽不符，需在异常/检查说明中说明。",
        ],
    },
    "F3-7-credit": {
        "item_id": "F3-7-credit-rows",
        "title": "F3-7 本期贷方金额检查",
        "headers": [
            "序号", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "贷方金额", "票据类别",
            "入库单日期/编号", "品名", "单位", "数量", "发票日期/编号", "对手方名称", "发票金额",
            "其他证据", "索引号", "是否异常", "异常/检查说明",
        ],
        "field_keys": [
            "seq", "voucherDate", "voucherNo", "businessContent", "counterAccount", "detailAccount",
            "amount", "noteType", "receiptDateNo", "receiptProduct", "receiptUnit", "receiptQty",
            "invoiceDateNo", "invoiceCounterparty", "invoiceAmount",
            "otherEvidence", "indexNo", "isAbnormal", "issueDesc",
        ],
        "guidance": [
            "F3-7 本期贷方金额检查 编制说明", "",
            "1. 科目2201贷方发生（票据增加：开票承兑），逐笔核对记账凭证、入库单/验收单、采购发票。",
            "2. 发票金额与凭证金额不符时系统标记勾稽不符，需在异常/检查说明中说明。",
        ],
    },
    "F3-7-subsequent": {
        "item_id": "F3-7-subsequent-rows",
        "title": "F3-7 资产负债表日后借方检查",
        "headers": [
            "序号", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "借方金额", "票据类别",
            "付款审批单日期/编号", "是否经过恰当审批", "银行回单日期", "收款方", "回单金额",
            "其他证据", "索引号", "是否异常", "异常/检查说明",
        ],
        "field_keys": [
            "seq", "voucherDate", "voucherNo", "businessContent", "counterAccount", "detailAccount",
            "amount", "noteType", "approvalDateNo", "approvalProper", "bankReceiptDate", "bankPayee",
            "bankAmount", "otherEvidence", "indexNo", "isAbnormal", "issueDesc",
        ],
        "guidance": [
            "F3-7 资产负债表日后借方检查 编制说明", "",
            "1. 关注资产负债表日后已偿付的应付票据，检查有无应计而未计入当期的应付票据。",
            "2. 结构同本期借方检查：逐笔核对记账凭证、付款审批单、银行回单。",
        ],
    },
}

_SUPPORTED = set(_F3_SPECS.keys())


def _validate(sheet: str) -> None:
    if sheet not in _SUPPORTED:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED)}")


def _spec(sheet: str) -> dict[str, Any]:
    return _F3_SPECS[sheet]


def _header_row() -> int:
    return 2


def _normalize_rows(rows: list[dict]) -> list[dict]:
    """为导入行补充 rowId，与前端 composable 一致."""
    out: list[dict] = []
    for i, row in enumerate(rows):
        r = dict(row)
        if not r.get("rowId"):
            r["rowId"] = r.get("id") or f"imp-{uuid.uuid4().hex[:12]}"
        if not r.get("seq"):
            r["seq"] = i + 1
        out.append(r)
    return out


@router.post("/api/workpapers/{wp_id}/f3/export-template")
async def f3_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate(sheet)
    sp = _spec(sheet)
    wb = build_workbook_template(sheet, sp["headers"], title=sp["title"], guidance=sp["guidance"])
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/f3/export-data")
async def f3_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate(sheet)
    sp = _spec(sheet)
    rows = await load_json_rows(db, wp_id, sp["item_id"], field=_STORAGE_FIELD)
    wb = build_workbook_template(sheet, sp["headers"], title=sp["title"], guidance=sp["guidance"])
    ws = wb[sheet]
    for d in rows:
        ws.append(export_row_by_keys(d, sp["field_keys"]))
    return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/f3/import-data")
async def f3_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _validate(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")
    sp = _spec(sheet)
    try:
        actual, raw = parse_upload_xlsx(content, sp["headers"], header_row=_header_row())
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "imported_count": 0}
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件")
    rows, truncated = import_rows_generic(
        raw, actual, sp["field_keys"],
        parse_fn=lambda r, h: parse_row_by_headers(r, h, sp["field_keys"]),
    )
    rows = _normalize_rows(rows)
    await upsert_json_rows(db, wp_id, sp["item_id"], rows, field=_STORAGE_FIELD)
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
