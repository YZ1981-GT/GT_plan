"""F1 预付账款 — 导入导出（列结构对齐 HTML 底稿）."""

from __future__ import annotations

import io
import logging
from typing import Any
from uuid import uuid4

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
from ._d3_import_export import (
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

_SUPPORTED_SHEETS: set[str] = {"F1-2", "F1-5", "F1-6", "F1-7", "F1-7-post"}

_SHEET_ITEM_ID: dict[str, str] = {
    "F1-2": "F1-det-rows",
    "F1-5": "F1-lt-rows",
    "F1-6": "F1-rp-rows",
    "F1-7": "F1-vc-current-rows",
    "F1-7-post": "F1-vc-post-rows",
}

_D3_SHEET_MAP: dict[str, str] = {
    "F1-2": "D3-2",
    "F1-5": "D3-5",
    "F1-6": "D3-6",
}

# F1-7 本期增减 — 比 D3-7 多「借方金额」列（对齐 F1TabComprehensiveCheck）
_F1_7_HEADERS = [
    "客户名称", "日期", "凭证编号", "业务内容", "对方科目", "对方明细科目",
    "借方金额", "贷方金额", "支持性文件",
    "核对内容1", "核对内容2", "核对内容3", "核对内容4", "核对内容5",
    "索引号", "是否异常", "备注说明",
]

_SHEET_META: dict[str, dict[str, Any]] = {
    "F1-2": {
        "title": "F1-2 预付账款明细表",
        "guidance": [
            "F1-2 预付账款明细表 编制说明",
            "",
            "列结构与 HTML 底稿 27 列一致：对方单位|款项性质|期初/发生/期末|账龄|期后结转等。",
            "账龄与期末余额由系统自动校验；期后结转(Z列)与 F1-7 期后检查联动。",
        ],
    },
    "F1-5": {
        "title": "F1-5 账龄1年以上检查表",
        "guidance": ["F1-5 编制说明", "", "8列：对方单位|期末余额|账龄|业务说明|未结转原因|至审计日结转金额|处理计划|备注"],
    },
    "F1-6": {
        "title": "F1-6 关联方检查表",
        "guidance": ["F1-6 编制说明", "", "10列：关联方|关系|期初|借贷方|期末|账龄说明|款项性质|索引|备注"],
    },
    "F1-7": {
        "title": "F1-7 预付账款检查表 — (1) 本期增减变动",
        "guidance": [
            "F1-7 本期增减 编制说明",
            "",
            "17列宽表，含借方/贷方金额；核对内容1~5填 Y/是 表示已核对。",
            "可从抽凭引擎分配样本后导出/导入。",
        ],
    },
    "F1-7-post": {
        "title": "F1-7 预付账款检查表 — (2) 期后结转检查",
        "guidance": [
            "F1-7 期后结转 编制说明",
            "",
            "16列（无借方金额列），与 F1-2 期后结转(Z列)交叉验证。",
        ],
    },
}


def _headers(sheet_code: str) -> list[str]:
    if sheet_code == "F1-7":
        return _F1_7_HEADERS
    if sheet_code == "F1-7-post":
        return _d3_get_headers("D3-7")
    return _d3_get_headers(_D3_SHEET_MAP[sheet_code])


def _validate_sheet(sheet_code: str) -> None:
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}")


def _export_row(sheet_code: str, data: dict) -> list:
    if sheet_code == "F1-7":
        check_items = data.get("checkItems", [False] * 5)
        return [
            safe_str(data.get("customerName")),
            safe_str(data.get("date")),
            safe_str(data.get("voucherNo")),
            safe_str(data.get("businessContent")),
            safe_str(data.get("counterAccount")),
            safe_str(data.get("counterDetailAccount")),
            safe_float(data.get("debitAmount")),
            safe_float(data.get("creditAmount")),
            safe_str(data.get("supportingDoc")),
            *["Y" if c else "" for c in (check_items + [False] * 5)[:5]],
            safe_str(data.get("indexRef")),
            safe_str(data.get("isAbnormal")),
            safe_str(data.get("remark")),
        ]
    d3 = _D3_SHEET_MAP.get(sheet_code, "D3-7")
    if d3 == "D3-2":
        return _export_d3_2_row(data)
    if d3 == "D3-5":
        return _export_d3_5_row(data)
    if d3 == "D3-6":
        return _export_d3_6_row(data)
    return _export_d3_7_row(data)


def _parse_f1_7_row(row: tuple, headers: list[str]) -> dict:
    check_items = [
        safe_str(col_val(row, headers, f"核对内容{i}")).upper() in ("Y", "是", "TRUE", "1")
        for i in range(1, 6)
    ]
    return {
        "rowId": str(uuid4()),
        "customerName": safe_str(col_val(row, headers, "客户名称")),
        "date": safe_str(col_val(row, headers, "日期")),
        "voucherNo": safe_str(col_val(row, headers, "凭证编号")),
        "businessContent": safe_str(col_val(row, headers, "业务内容")),
        "counterAccount": safe_str(col_val(row, headers, "对方科目")),
        "counterDetailAccount": safe_str(col_val(row, headers, "对方明细科目")),
        "debitAmount": safe_float(col_val(row, headers, "借方金额")),
        "creditAmount": safe_float(col_val(row, headers, "贷方金额")),
        "supportingDoc": safe_str(col_val(row, headers, "支持性文件")),
        "checkItems": check_items,
        "indexRef": safe_str(col_val(row, headers, "索引号")),
        "isAbnormal": safe_str(col_val(row, headers, "是否异常")),
        "remark": safe_str(col_val(row, headers, "备注说明")),
    }


def _parse_row(sheet_code: str, row: tuple, headers: list[str]) -> dict:
    if sheet_code == "F1-7":
        return _parse_f1_7_row(row, headers)
    if sheet_code == "F1-7-post":
        return _parse_d3_7_row(row, headers)
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
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
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
    headers = _headers(sheet)
    item_id = _SHEET_ITEM_ID[sheet]
    rows_data = await load_json_rows(db, wp_id, item_id, field="remark")
    title, subtitle, guidance = _template_meta(sheet)
    wb = build_workbook_template(sheet, headers, title=title, subtitle=subtitle, guidance=guidance)
    ws = wb[sheet]
    for d in rows_data:
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
    headers = _headers(sheet)
    header_row = 2 if _SHEET_META.get(sheet, {}).get("title") else 1
    try:
        actual, raw_rows = parse_upload_xlsx(content, headers, header_row=header_row)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "imported_count": 0}
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件")
    rows_data, truncated = import_rows_generic(
        raw_rows, actual, [], parse_fn=lambda r, h: _parse_row(sheet, r, h),
    )
    await upsert_json_rows(db, wp_id, _SHEET_ITEM_ID[sheet], rows_data, field="remark")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows_data), "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
