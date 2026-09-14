"""H10 资产处置损益 — 导入导出（H10-2 / H10-3 × 3 端点 = 6）."""

from __future__ import annotations

import json
from typing import Any
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
    export_row_by_keys,
    import_rows_generic,
    is_numeric_field_key,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_rows,
    workbook_to_response,
)

_H10_2_HEADERS = [
    "序号", "资产名称", "资产类型", "来源底稿", "来源索引",
    "处置收入", "净值", "处置费用", "税费", "处置损益",
]
_H10_2_KEYS = [
    "seq", "assetName", "assetType", "sourceWp", "sourceIndex",
    "disposalIncome", "netBookValue", "disposalExpense", "taxAmount", "gainLoss",
]

_H10_3_HEADERS = [
    "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方金额", "贷方金额", "编制人", "备注",
]
_H10_3_KEYS = [
    "entryType", "date", "summary", "accountCode", "accountName", "debitAmount", "creditAmount", "preparedBy", "remark",
]

_H10_SPECS: dict[str, dict[str, Any]] = {
    "H10-2": {
        "item_id": "H10-detail-rows",
        "title": "H10-2 资产处置明细表",
        "headers": _H10_2_HEADERS,
        "field_keys": _H10_2_KEYS,
        "guidance": [
            "H10-2 明细表 编制说明",
            "",
            "处置损益=处置收入-净值-处置费用-税费；可与 H6 disposal:completed 事件自动汇入。",
        ],
    },
    "H10-3": {
        "item_id": "H10-aje-rows",
        "title": "H10-3 调整分录汇总",
        "headers": _H10_3_HEADERS,
        "field_keys": _H10_3_KEYS,
        "guidance": ["H10-3 调整分录", "", "分录类型 AJE/RJE；借贷须平衡。"],
    },
}

_SUPPORTED = set(_H10_SPECS.keys())
router = APIRouter(tags=["h10-import-export"])
_HEADER_ROW = 2


def _validate(sheet: str) -> None:
    if sheet not in _SUPPORTED:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED)}")


@router.post("/api/workpapers/{wp_id}/h10/export-template")
async def export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate(sheet)
    sp = _H10_SPECS[sheet]
    wb = build_workbook_template(
        sheet, sp["headers"], title=sp.get("title"), guidance=sp.get("guidance"),
    )
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/h10/export-data")
async def export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate(sheet)
    sp = _H10_SPECS[sheet]
    rows = await load_json_rows(db, wp_id, sp["item_id"], field="remark")
    wb = build_workbook_template(
        sheet, sp["headers"], title=sp.get("title"), guidance=sp.get("guidance"),
    )
    ws = wb[sheet]
    for d in rows:
        ws.append(export_row_by_keys(d, sp["field_keys"]))
    return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/h10/import-data")
async def import_data(
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

    sp = _H10_SPECS[sheet]
    try:
        actual, raw = parse_upload_xlsx(content, sp["headers"], header_row=_HEADER_ROW)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "imported_count": 0}

    keys = sp["field_keys"]
    rows, truncated = import_rows_generic(
        raw, actual, keys, parse_fn=lambda r, h: parse_row_by_headers(r, h, keys),
    )
    for row in rows:
        if "id" not in row:
            row["id"] = str(uuid4())
    await upsert_json_rows(db, wp_id, sp["item_id"], rows, field="remark")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
