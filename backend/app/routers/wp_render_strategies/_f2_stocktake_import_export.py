"""F2 存货监盘 — 导入导出."""

from __future__ import annotations

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

router = APIRouter(tags=["f2-st-import-export"])

_STORAGE_FIELD = "remark"

_F2_ST_SPECS: dict[str, dict[str, Any]] = {
    "F2-24": {
        "item_id": "F2-24-rows",
        "title": "F2-24 账面与ERP核对（资产负债表日）",
        "headers": ["品名", "规格", "账面数量", "账面金额", "ERP数量", "ERP金额", "备注"],
        "field_keys": ["itemName", "spec", "bookQty", "bookAmount", "erpQty", "erpAmount", "remark"],
        "guidance": ["F2-24（一）资产负债表日核对", "", "差异列由系统计算。"],
    },
    "F2-24-count": {
        "item_id": "F2-24-count-rows",
        "title": "F2-24 账面与ERP核对（盘点日）",
        "headers": ["品名", "规格", "账面数量", "账面金额", "ERP数量", "ERP金额", "备注"],
        "field_keys": ["itemName", "spec", "bookQty", "bookAmount", "erpQty", "erpAmount", "remark"],
        "guidance": ["F2-24（二）盘点日核对", "", "仅盘点日≠截止日时填写；差异列由系统计算。"],
    },
    "F2-25": {
        "item_id": "F2-25-rows",
        "title": "F2-25 抽盘结果汇总（记录→实物）",
        "headers": [
            "存货编码",
            "名称类别",
            "规格",
            "单位",
            "单价",
            "账面数量",
            "账面金额",
            "企业盘点数量",
            "抽盘数量",
            "品质状况",
            "差异原因",
            "备注",
        ],
        "field_keys": [
            "itemCode",
            "itemName",
            "spec",
            "unit",
            "unitPrice",
            "bookQty",
            "bookAmount",
            "clientCountQty",
            "sampleQty",
            "qualityStatus",
            "varianceReason",
            "remark",
        ],
        "guidance": [
            "F2-25 抽盘汇总（一）记录→实物",
            "",
            "差异列由系统计算：抽盘−账面 / 抽盘−企业 / 企业−账面。",
            "实物→记录表请另存或在系统第二节录入（F2-25-floor-rows）。",
        ],
    },
    "F2-25-floor": {
        "item_id": "F2-25-floor-rows",
        "title": "F2-25 抽盘结果汇总（实物→记录）",
        "headers": [
            "存货编码",
            "名称类别",
            "规格",
            "单位",
            "单价",
            "账面数量",
            "账面金额",
            "企业盘点数量",
            "抽盘数量",
            "品质状况",
            "差异原因",
            "备注",
        ],
        "field_keys": [
            "itemCode",
            "itemName",
            "spec",
            "unit",
            "unitPrice",
            "bookQty",
            "bookAmount",
            "clientCountQty",
            "sampleQty",
            "qualityStatus",
            "varianceReason",
            "remark",
        ],
        "guidance": [
            "F2-25 抽盘汇总（二）实物→记录",
            "",
            "差异列由系统计算。",
        ],
    },
    "F2-26": {
        "item_id": "F2-26-rows",
        "title": "F2-26 日前盘点倒轧（顺推）",
        "headers": [
            "类别",
            "编码",
            "品名",
            "规格",
            "单位",
            "单价",
            "仓库",
            "盘点日实存",
            "入库数量",
            "发出数量",
            "截止日账面",
            "差异原因",
            "是否调整",
            "备注",
        ],
        "field_keys": [
            "category",
            "itemCode",
            "itemName",
            "spec",
            "unit",
            "unitPrice",
            "warehouse",
            "countDayQty",
            "inboundQty",
            "outboundQty",
            "bookQty",
            "varianceReason",
            "needAdjust",
            "remark",
        ],
        "guidance": [
            "F2-26（二）资产负债表日前盘点倒轧",
            "",
            "D=A+入库−发出；数量差异=D−账面。计算列勿填。",
        ],
    },
    "F2-26-after": {
        "item_id": "F2-26-after-rows",
        "title": "F2-26 日后盘点倒轧（倒推）",
        "headers": [
            "类别",
            "编码",
            "品名",
            "规格",
            "单位",
            "单价",
            "仓库",
            "盘点日实存",
            "发出数量",
            "入库数量",
            "截止日账面",
            "差异原因",
            "是否调整",
            "备注",
        ],
        "field_keys": [
            "category",
            "itemCode",
            "itemName",
            "spec",
            "unit",
            "unitPrice",
            "warehouse",
            "countDayQty",
            "outboundQty",
            "inboundQty",
            "bookQty",
            "varianceReason",
            "needAdjust",
            "remark",
        ],
        "guidance": [
            "F2-26（一）资产负债表日后盘点倒轧",
            "",
            "D=A+发出−入库；数量差异=D−账面。计算列勿填。",
        ],
    },
}

_SUPPORTED = set(_F2_ST_SPECS.keys())


def _validate(sheet: str) -> None:
    if sheet not in _SUPPORTED:
        raise HTTPException(400, f"不支持的sheet: {sheet}")


def _spec(sheet: str) -> dict[str, Any]:
    return _F2_ST_SPECS[sheet]


def _normalize(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, row in enumerate(rows):
        r = dict(row)
        if not r.get("id"):
            r["id"] = f"imp-{uuid.uuid4().hex[:12]}"
        out.append(r)
    return out


def _num(val: Any, default: float = 0) -> float:
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _parse_row(sheet: str, row: dict) -> dict:
    r = dict(row)
    if sheet in ("F2-24", "F2-24-count", "F2-25", "F2-25-floor", "F2-26", "F2-26-after"):
        for k in (
            "bookQty",
            "bookAmount",
            "erpQty",
            "erpAmount",
            "sampleQty",
            "unitPrice",
            "clientCountQty",
            "countDayQty",
            "inboundQty",
            "outboundQty",
        ):
            if k in r:
                r[k] = _num(r.get(k))
    return r


@router.post("/api/workpapers/{wp_id}/f2-st/export-template")
async def f2_st_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate(sheet)
    sp = _spec(sheet)
    wb = build_workbook_template(sheet, sp["headers"], title=sp["title"], guidance=sp["guidance"])
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/f2-st/export-data")
async def f2_st_export_data(
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


@router.post("/api/workpapers/{wp_id}/f2-st/import-data")
async def f2_st_import_data(
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
    payload = [_parse_row(sheet, r) for r in _normalize(rows)]
    await upsert_json_rows(db, wp_id, sp["item_id"], payload, field=_STORAGE_FIELD)
    out: dict[str, Any] = {"ok": True, "imported_count": len(payload), "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
