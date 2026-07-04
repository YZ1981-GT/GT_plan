"""F2 计价/跌价/检查组 — 导入导出."""

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

router = APIRouter(tags=["f2-val-import-export"])

_STORAGE_FIELD = "remark"

_VAL_HEADERS = [
    "序号", "凭证号", "品名", "期初数量", "期初金额", "入库数量", "入库金额",
    "发出数量", "账面金额", "FIFO单价", "标准单价", "标准数量", "实际单价", "实际数量",
]
_VAL_KEYS = [
    "seq", "voucherNo", "itemName", "openingQty", "openingAmt", "inboundQty", "inboundAmt",
    "issueQty", "bookIssueAmt", "fifoUnitPrice", "stdPrice", "stdQty", "actPrice", "actQty",
]

_INSPECTION_HEADERS = ["序号", "供应商/部门", "单号", "品名", "金额", "凭证号", "备注"]
_INSPECTION_KEYS = ["seq", "party", "docNo", "itemName", "amount", "voucherNo", "remark"]

_F2_VAL_SPECS: dict[str, dict[str, Any]] = {
    "F2-33": {
        "item_id": "F2-33-rows",
        "title": "F2-33 采购入库检查",
        "headers": _INSPECTION_HEADERS,
        "field_keys": _INSPECTION_KEYS,
        "guidance": ["F2-33 采购入库检查 编制说明", "", "借方存货科目1401~1411发生。"],
    },
    "F2-34": {
        "item_id": "F2-34-rows",
        "title": "F2-34 材料领用检查",
        "headers": _INSPECTION_HEADERS,
        "field_keys": _INSPECTION_KEYS,
        "guidance": ["F2-34 材料领用检查 编制说明", "", "贷方存货科目发生。"],
    },
    "F2-35": {
        "item_id": "F2-35-rows",
        "title": "F2-35 委托加工核查",
        "headers": _INSPECTION_HEADERS + ["账龄(天)"],
        "field_keys": _INSPECTION_KEYS + ["daysOutstanding"],
        "guidance": ["F2-35 委托加工核查 编制说明", "", "在外天数>180天需关注。"],
    },
    "F2-38": {
        "item_id": "F2-38-rows",
        "title": "F2-38 加权平均计价测试",
        "headers": _VAL_HEADERS,
        "field_keys": _VAL_KEYS,
        "guidance": ["F2-38 计价测试 编制说明", "", "差异率>1%需关注。"],
    },
    "F2-39": {
        "item_id": "F2-39-rows",
        "title": "F2-39 先进先出计价测试",
        "headers": _VAL_HEADERS,
        "field_keys": _VAL_KEYS,
        "guidance": ["F2-39 计价测试 编制说明", "", "差异率>1%需关注。"],
    },
    "F2-40": {
        "item_id": "F2-40-rows",
        "title": "F2-40 标准成本差异测试",
        "headers": _VAL_HEADERS,
        "field_keys": _VAL_KEYS,
        "guidance": ["F2-40 标准成本 编制说明", "", "差异率>5%需关注。"],
    },
    "F2-41": {
        "item_id": "F2-41-rows",
        "title": "F2-41 生产成本明细",
        "headers": ["产品名称", "期初材料", "本期投入材料", "本期转出材料", "期末材料", "期初人工", "投入人工", "转出人工", "期末人工"],
        "field_keys": ["productName", "openingMaterial", "inputMaterial", "outputMaterial", "closingMaterial", "openingLabor", "inputLabor", "outputLabor", "closingLabor"],
        "guidance": ["F2-41 生产成本 编制说明", "", "期末=期初+投入-转出。"],
    },
    "F2-42": {
        "item_id": "F2-42-rows",
        "title": "F2-42 直接人工分析",
        "headers": ["产品", "人数", "工时", "工资率", "实际人工", "标准人工", "差异"],
        "field_keys": ["productName", "headcount", "hours", "wageRate", "actualLabor", "standardLabor", "variance"],
        "guidance": ["F2-42 直接人工 编制说明", "", "人工费=人数×工时×工资率。"],
    },
    "F2-43": {
        "item_id": "F2-43-rows",
        "title": "F2-43 制造费用明细",
        "headers": ["费用项目", "预算数", "实际数", "变动额", "分配基数", "分配率"],
        "field_keys": ["itemName", "budgetAmt", "actualAmt", "varianceAmt", "allocationBase", "allocationRate"],
        "guidance": ["F2-43 制造费用 编制说明", "", "变动率>20%需关注。"],
    },
    "F2-44": {
        "item_id": "F2-44-rows",
        "title": "F2-44 成本分配",
        "headers": ["产品", "分配基准", "基准数量", "材料分配", "人工分配", "制造费用分配"],
        "field_keys": ["productName", "basisType", "basisQty", "materialAlloc", "laborAlloc", "overheadAlloc"],
        "guidance": ["F2-44 成本分配 编制说明", "", "分配比例合计应=100%。"],
    },
    "F2-47": {
        "item_id": "F2-47-rows",
        "title": "F2-47 跌价准备NRV测试",
        "headers": ["序号", "品名", "数量", "单位成本", "估计售价", "完工成本", "销售费用", "税金", "已计提跌价", "结论"],
        "field_keys": ["seq", "itemName", "qty", "unitCost", "sellingPrice", "completionCost", "sellingExpense", "tax", "existingProvision", "conclusion"],
        "guidance": ["F2-47 跌价测试 编制说明", "", "NRV=售价-完工-销售费-税金。"],
    },
    "F2-48": {
        "item_id": "F2-48-rows",
        "title": "F2-48 呆滞存货",
        "headers": ["品名", "数量", "金额", "库龄(天)", "保质期(天)", "处理方案", "跌价建议"],
        "field_keys": ["itemName", "qty", "amount", "ageDays", "shelfDays", "disposalPlan", "impairmentSuggestion"],
        "guidance": ["F2-48 呆滞存货 编制说明", "", "超保质或呆滞需橙色标记。"],
    },
    "F2-49": {
        "item_id": "F2-49-rows",
        "title": "F2-49 跌价转回",
        "headers": ["品名", "账面成本", "上期已计提", "估计售价", "完工成本", "销售费用", "转回上限", "转回合理性"],
        "field_keys": ["itemName", "bookCost", "priorProvision", "sellingPrice", "completionCost", "sellingExpense", "reversalCap", "reversalReason"],
        "guidance": ["F2-49 跌价转回 编制说明", "", "转回≤累计计提。"],
    },
    "F2-52": {
        "item_id": "F2-52-rows",
        "title": "F2-52 关联采购",
        "headers": ["供应商", "品名", "数量", "单价", "可比单价", "定价方式", "公允性结论"],
        "field_keys": ["supplierName", "itemName", "qty", "unitPrice", "comparablePrice", "pricingMethod", "fairnessConclusion"],
        "guidance": ["F2-52 关联采购 编制说明", "", "差异率>10%需关注。"],
    },
}

_SUPPORTED = set(_F2_VAL_SPECS.keys())


def _validate(sheet: str) -> None:
    if sheet not in _SUPPORTED:
        raise HTTPException(400, f"不支持的sheet: {sheet}")


def _spec(sheet: str) -> dict[str, Any]:
    return _F2_VAL_SPECS[sheet]


def _normalize(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, row in enumerate(rows):
        r = dict(row)
        if not r.get("rowId") and not r.get("id"):
            r["rowId"] = f"imp-{uuid.uuid4().hex[:12]}"
        elif not r.get("rowId") and r.get("id"):
            r["rowId"] = r["id"]
        if not r.get("id"):
            r["id"] = r.get("rowId") or f"imp-{uuid.uuid4().hex[:12]}"
        if not r.get("seq"):
            r["seq"] = i + 1
        out.append(r)
    return out


@router.post("/api/workpapers/{wp_id}/f2-val/export-template")
async def f2_val_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate(sheet)
    sp = _spec(sheet)
    wb = build_workbook_template(sheet, sp["headers"], title=sp["title"], guidance=sp["guidance"])
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/f2-val/export-data")
async def f2_val_export_data(
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


@router.post("/api/workpapers/{wp_id}/f2-val/import-data")
async def f2_val_import_data(
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
        actual, raw = parse_upload_xlsx(content, sp["headers"], header_row=2)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "imported_count": 0}
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件")
    rows, truncated = import_rows_generic(
        raw, actual, sp["field_keys"],
        parse_fn=lambda r, h: parse_row_by_headers(r, h, sp["field_keys"]),
    )
    rows = _normalize(rows)
    await upsert_json_rows(db, wp_id, sp["item_id"], rows, field=_STORAGE_FIELD)
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
