"""G4 债权投资(SPPI组) — 导入导出端点

支持 3 张动态行表格：
  G4-6 合同现金流量特征分析(部分一+部分二) / G4-7 盘点表 / G4-8 倒轧表

字段键与前端 composable (useG4SppiTest / useG4SppiInventory / useG4SppiReconciliation)
行接口严格对齐，保证 round-trip。

G4-8 按 3 区段分 sheet 导出（盘点日实存/增减变动/报表日实存+差异）。
"""

from __future__ import annotations

import io
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    export_row_by_keys,
    is_numeric_field_key,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_rows,
    workbook_to_response,
)

router = APIRouter(tags=["g4-sppi-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# G4-6 合同现金流量特征分析（部分一 + 部分二三步合并）
# ═══════════════════════════════════════════════════════════════════════════════

# 部分(一): 债券投资 SPPI（10列）
_G4_6_BOND_HEADERS = [
    "投资项目", "票面价值", "票面利率(%)", "提前回售(是/否)",
    "展期(是/否)", "权益转换(是/否)", "杠杆(是/否)",
    "结论", "分析项目", "判断逻辑",
]
_G4_6_BOND_KEYS = [
    "investProject", "faceValue", "couponRate", "hasEarlyRedemption",
    "hasExtension", "hasEquityConversion", "hasLeverage",
    "conclusion", "analysisType", "methodologyText",
]

# 部分(二) 第一步: 保本保收益（8列）
_G4_6_STEP1_HEADERS = [
    "投资项目", "投资总额", "保证本金(是/否)", "固定收益(是/否)",
    "固定收益率(%)", "约定浮动收益(是/否)", "浮动收益率(%)", "结论",
]
_G4_6_STEP1_KEYS = [
    "investProject", "totalAmount", "guaranteesPrincipal", "hasFixedReturn",
    "fixedReturnRate", "hasFloatingReturn", "floatingReturnRate", "conclusion",
]

# 部分(二) 第二步: 浮动收益不现实（6列）
_G4_6_STEP2_HEADERS = [
    "投资项目", "固定收益率(%)", "浮动收益确定方式",
    "基础变量历史变动", "是否不现实(是/否)", "结论",
]
_G4_6_STEP2_KEYS = [
    "investProject", "fixedReturnRate", "floatingMethod",
    "baseVariableHistory", "isUnrealistic", "conclusion",
]

# 部分(二) 第三步: 穿透底层资产（4列）
_G4_6_STEP3_HEADERS = [
    "投资项目", "底层资产类型", "底层资产SPPI特征", "穿透结论",
]
_G4_6_STEP3_KEYS = [
    "investProject", "underlyingAssetType", "underlyingSppiFeature", "conclusion",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G4-7 有价证券盘点表（7列）
# ═══════════════════════════════════════════════════════════════════════════════

_G4_7_HEADERS = [
    "序号", "证券名称", "面值", "数量", "总计", "票面利率(%)", "到期日",
]
_G4_7_KEYS = [
    "seq", "securitiesName", "faceValue", "quantity", "total", "couponRate", "maturityDate",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G4-8 盘点倒轧表（18列 → 3区段分sheet）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 盘点日实存(6列)
_G4_8_SEG1_HEADERS = ["证券名称", "数量", "面值", "总计", "票面利率(%)", "到期日"]
_G4_8_SEG1_KEYS = ["securitiesName", "countQuantity", "countFaceValue", "countTotal", "countCouponRate", "countMaturityDate"]

# 区段2: 增减变动(2列)
_G4_8_SEG2_HEADERS = ["增减数量", "增减面值总额"]
_G4_8_SEG2_KEYS = ["changeQuantity", "changeFaceValueTotal"]

# 区段3: 报表日实存+差异(10列)
_G4_8_SEG3_HEADERS = [
    "报表日数量", "报表日面值", "报表日总计", "票面利率(%)", "到期日",
    "账面结存数量", "账面结存面值", "账面结存总计", "差异", "备注",
]
_G4_8_SEG3_KEYS = [
    "reportQuantity", "reportFaceValue", "reportTotal", "reportCouponRate", "reportMaturityDate",
    "bookQuantity", "bookFaceValue", "bookTotal", "variance", "remark",
]

# 全18列（用于单sheet导入解析）
_G4_8_ALL_HEADERS = (
    ["证券名称"] + _G4_8_SEG1_HEADERS[1:] + _G4_8_SEG2_HEADERS + _G4_8_SEG3_HEADERS
)
_G4_8_ALL_KEYS = (
    ["securitiesName"] + _G4_8_SEG1_KEYS[1:] + _G4_8_SEG2_KEYS + _G4_8_SEG3_KEYS
)

_G4_8_SEGMENTS = [
    ("盘点日实存", _G4_8_SEG1_HEADERS, _G4_8_SEG1_KEYS),
    ("增减变动", _G4_8_SEG2_HEADERS, _G4_8_SEG2_KEYS),
    ("报表日实存+差异", _G4_8_SEG3_HEADERS, _G4_8_SEG3_KEYS),
]

# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G4-6": "G4-6-bond-items",
    "G4-7": "G4-7-items",
    "G4-8": "G4-8-items",
}

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


def _bool_to_str(val: Any) -> str:
    """布尔值转中文"是/否"用于导出。"""
    if val is True or val == "true" or val == "True":
        return "是"
    return "否"


def _str_to_bool(val: Any) -> bool:
    """中文"是/否"或True/False转布尔用于导入。"""
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("是", "true", "1", "yes")


# ═══════════════════════════════════════════════════════════════════════════════
# G4-6 多sheet导出（部分一+部分二三步 → 4 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g4_6_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G4-6 按4部分分sheet导出。"""
    wb = Workbook()
    wb.remove(wb.active)

    sections = [
        ("债券投资SPPI", _G4_6_BOND_HEADERS, _G4_6_BOND_KEYS),
        ("第一步-保本保收益", _G4_6_STEP1_HEADERS, _G4_6_STEP1_KEYS),
        ("第二步-浮动收益不现实", _G4_6_STEP2_HEADERS, _G4_6_STEP2_KEYS),
        ("第三步-穿透底层资产", _G4_6_STEP3_HEADERS, _G4_6_STEP3_KEYS),
    ]
    for sec_name, sec_headers, sec_keys in sections:
        ws = wb.create_sheet(title=sec_name)
        ws.append([f"G4-6 合同现金流量特征分析 — {sec_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(sec_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(sec_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(sec_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14

        if not template_only and rows:
            # 根据section从rows中按key提取导出
            section_rows = rows[0].get(sec_name, []) if isinstance(rows[0], dict) and sec_name in rows[0] else rows
            for row_data in section_rows:
                ws.append(export_row_by_keys(row_data, sec_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G4-6 合同现金流量特征分析 编制说明"])
    ws_guide.append([])
    for line in [
        "部分(一)：逐项检查债券投资合同条款SPPI特征（10列）。",
        "部分(二)：银行理财产品三步法判断（保本保收益/浮动收益不现实/穿透底层资产）。",
        '布尔列填"是"或"否"。',
        "结论列填：PASS/FAIL/FURTHER_ANALYSIS。",
        "分析项目填：simple/floating_rate/rate_adjustment/prepayment/extension/non_recourse/linked_instrument。",
    ]:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


# ═══════════════════════════════════════════════════════════════════════════════
# G4-8 多sheet导出（3区段 → 3 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g4_8_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G4-8 按3区段分sheet导出。"""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G4_8_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        ws.append([f"G4-8 盘点倒轧表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14

        if not template_only:
            for row_data in rows:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G4-8 盘点倒轧表 编制说明"])
    ws_guide.append([])
    for line in [
        "18列拆为3区段Tab：盘点日实存(6) / 增减变动(2) / 报表日实存+差异(10)。",
        "公式列（总计/报表日数量/报表日总计/差异）导入后前端自动重算。",
        "总计 = 面值 × 数量。",
        "报表日数量 = 盘点日数量 + 增减数量。",
        "报表日总计 = 报表日面值 × 报表日数量。",
        "差异 = 报表日总计 - 账面结存总计。差异非零时备注必填。",
    ]:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g4_8_import(content: bytes) -> tuple[list[dict], list[str]]:
    """解析G4-8导入文件，支持多sheet或单sheet两种格式。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_dict: dict[int, dict] = {}

    multi_sheet = len(wb.sheetnames) >= 3 and any("盘点日实存" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G4_8_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append(f"缺少工作表: {seg_name}")
                continue
            header_row_idx = 2
            actual_headers = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
            ]
            missing = [h for h in seg_headers if h not in actual_headers]
            if missing:
                errors.append(f"工作表[{seg_name}]缺少列: {', '.join(missing)}")
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {"id": str(uuid4()), "seq": row_idx + 1}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    raw = values[col_i] if col_i < len(values) else None
                    if is_numeric_field_key(key):
                        rows_dict[row_idx][key] = safe_float(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
    else:
        # 单sheet宽表
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        header_row_idx = 1
        for r in range(1, 5):
            test_row = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows(min_row=r, max_row=r))]
            if "证券名称" in test_row:
                header_row_idx = r
                break
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        ]
        if "证券名称" not in actual_headers:
            errors.append("无法识别表头，缺少'证券名称'列")
            wb.close()
            return [], errors
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {"id": str(uuid4()), "seq": row_idx + 1}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in _G4_8_ALL_HEADERS:
                    key_idx = _G4_8_ALL_HEADERS.index(h)
                    key = _G4_8_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if is_numeric_field_key(key):
                        parsed[key] = safe_float(raw)
                    else:
                        parsed[key] = safe_str(raw)
            rows_dict[row_idx] = parsed

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g4-sppi/export-template")
async def g4_sppi_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)

    if sheet == "G4-6":
        wb = _build_g4_6_workbook([], template_only=True)
        return workbook_to_response(wb, "G4-6_合同现金流量特征分析_模板.xlsx")
    elif sheet == "G4-7":
        wb = build_workbook_template(
            "G4-7",
            _G4_7_HEADERS,
            title="G4-7 有价证券盘点表",
            guidance=[
                "G4-7 有价证券盘点表 编制说明",
                "",
                "逐行记录实际盘点到的有价证券。",
                "总计 = 面值 × 数量（导入后前端自动重算）。",
                "利率以百分数填写（如 5.25 表示 5.25%）。",
                "到期日格式：YYYY-MM-DD。",
            ],
        )
        return workbook_to_response(wb, "G4-7_有价证券盘点表_模板.xlsx")
    else:  # G4-8
        wb = _build_g4_8_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G4-8_盘点倒轧表_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g4-sppi/export-data")
async def g4_sppi_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    item_id = _ITEM_IDS[sheet]
    rows = await load_json_rows(db, wp_id, item_id, field="remark")

    if sheet == "G4-6":
        wb = _build_g4_6_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G4-6_合同现金流量特征分析_数据.xlsx")
    elif sheet == "G4-7":
        wb = build_workbook_template(
            "G4-7",
            _G4_7_HEADERS,
            title="G4-7 有价证券盘点表",
            guidance=["逐行记录实际盘点到的有价证券。总计=面值×数量。"],
        )
        ws = wb["G4-7"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G4_7_KEYS))
        return workbook_to_response(wb, "G4-7_有价证券盘点表_数据.xlsx")
    else:  # G4-8
        wb = _build_g4_8_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G4-8_盘点倒轧表_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g4-sppi/import-data")
async def g4_sppi_import_data(
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

    item_id = _ITEM_IDS[sheet]
    errors: list[str] = []
    rows: list[dict] = []

    if sheet == "G4-6":
        # G4-6 导入只解析部分(一)债券投资sheet
        try:
            actual, raw = parse_upload_xlsx(content, _G4_6_BOND_HEADERS, header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            rows.append(parse_row_by_headers(r, actual, _G4_6_BOND_KEYS))
    elif sheet == "G4-7":
        try:
            actual, raw = parse_upload_xlsx(content, _G4_7_HEADERS, header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            rows.append(parse_row_by_headers(r, actual, _G4_7_KEYS))
    else:  # G4-8
        rows, errors = _parse_g4_8_import(content)

    if errors and not rows:
        return {"ok": False, "errors": errors, "imported_count": 0}

    await upsert_json_rows(db, wp_id, item_id, rows, field="remark")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
    if len(rows) >= ROW_LIMIT:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
