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
        "title": "F3-2 应付票据明细表（25列）",
        "headers": [
            "序号", "出票日期", "到期日", "票据类型", "出票人", "收票人", "面值", "币种", "用途",
            "票面利率(%)", "期限(天)", "是否带息", "是否逾期", "逾期天数", "承兑银行", "票据状态", "备注",
            "期初余额", "本期增加", "本期减少", "期末余额", "账项调整", "重分类", "审定余额", "索引",
        ],
        "field_keys": [
            "seq", "issueDate", "dueDate", "noteType", "drawer", "payee", "faceValue", "currency", "purpose",
            "interestRate", "termDays", "isInterestBearing", "isOverdue", "overdueDays", "acceptBank", "noteStatus", "remark",
            "openingBalance", "increase", "decrease", "closingBalance", "aje", "rje", "adjustedBalance", "indexRef",
        ],
        "guidance": [
            "F3-2 明细表 编制说明",
            "",
            "25列与 HTML 三区段Tab合并为宽表。公式列导入后由系统重算。",
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
        "title": "F3-4 带息票据利息测算表",
        "headers": [
            "序号", "出票人", "票据面值", "票面利率(%)", "出票日", "到期日", "期限(天)",
            "计息起始日", "计息截止日", "应计天数", "应付利息", "企业计提利息", "差异",
        ],
        "field_keys": [
            "seq", "drawer", "faceValue", "interestRate", "issueDate", "dueDate", "termDays",
            "interestStart", "interestEnd", "accruedDays", "payableInterest", "bookInterest", "variance",
        ],
        "guidance": ["F3-4 利息测算 编制说明", "", "应付利息=面值×利率×天数/360。"],
    },
    "F3-5": {
        "item_id": "F3-5-rows",
        "title": "F3-5 逾期票据检查表",
        "headers": [
            "序号", "出票人", "票据类型", "面值", "出票日", "到期日", "逾期天数", "逾期原因",
            "承兑方", "承兑方信用等级", "是否已转应付账款", "催收情况", "风险等级", "审计建议", "备注",
        ],
        "field_keys": [
            "seq", "drawer", "noteType", "faceValue", "issueDate", "dueDate", "overdueDays", "overdueReason",
            "acceptor", "acceptorRating", "transferredToAp", "collectionStatus", "riskLevel", "auditAdvice", "remark",
        ],
        "guidance": ["F3-5 逾期检查 编制说明", "", "逾期天数由系统按到期日重算。"],
    },
    "F3-6": {
        "item_id": "F3-6-rows",
        "title": "F3-6 关联方票据检查表",
        "headers": [
            "序号", "关联方名称", "关联关系", "票据类型", "面值", "出票日", "到期日", "期限", "利率", "用途",
            "占比(%)", "是否正常结算", "结算方式", "定价公允性", "审计评价", "备注",
        ],
        "field_keys": [
            "seq", "partyName", "relationship", "noteType", "faceValue", "issueDate", "dueDate", "term", "rate", "purpose",
            "concentration", "isNormalSettlement", "settlementMethod", "fairness", "auditEvaluation", "remark",
        ],
        "guidance": ["F3-6 关联方检查 编制说明", "", "占比=该行面值/合计。"],
    },
    "F3-7-credit": {
        "item_id": "F3-7-credit-rows",
        "title": "F3-7 贷方检查区（增加）",
        "headers": [
            "序号", "摘要", "对方科目", "金额", "凭证日期", "凭证编号", "票据类型", "承兑方",
            "采购合同核对", "商品验收核对", "审计结论", "备注",
        ],
        "field_keys": [
            "seq", "summary", "counterAccount", "amount", "voucherDate", "voucherNo", "noteType", "acceptor",
            "purchaseContractCheck", "goodsReceiptCheck", "auditConclusion", "remark",
        ],
        "guidance": ["F3-7 贷方检查区 编制说明", "", "科目2201贷方发生（票据增加）。"],
    },
    "F3-7-debit": {
        "item_id": "F3-7-debit-rows",
        "title": "F3-7 借方检查区（减少）",
        "headers": [
            "序号", "摘要", "对方科目", "金额", "凭证日期", "凭证编号", "付款方式", "银行流水核对",
            "是否逾期付款", "审计结论", "备注",
        ],
        "field_keys": [
            "seq", "summary", "counterAccount", "amount", "voucherDate", "voucherNo", "paymentMethod", "bankReconciliation",
            "isOverduePayment", "auditConclusion", "remark",
        ],
        "guidance": ["F3-7 借方检查区 编制说明", "", "科目2201借方发生（票据减少/兑付）。"],
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
