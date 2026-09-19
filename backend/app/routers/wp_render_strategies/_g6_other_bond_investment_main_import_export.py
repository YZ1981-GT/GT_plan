"""G6 其他债权投资(main组) — 导入导出端点

支持 3 张动态行表格：
  G6-2 明细表(33列→3区段Tab) / G6-3 坏账准备明细表(20列→2区段Tab) / G6-4 调整分录(10列)

字段键与前端 composable 行接口严格对齐，保证 round-trip。

G6-2 按3区段分sheet导出（基础信息/期初+变动/期末+审定）。
G6-3 按2区段分sheet导出（未审+调整/审定数）。
G6-4 单sheet导出。
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
    load_json_rows,
    safe_float,
    safe_str,
    upsert_json_rows,
    workbook_to_response,
)

router = APIRouter(tags=["g6-main-import-export"])


# ═══════════════════════════════════════════════════════════════════════════════
# G6-2 明细表（33列，3区段Tab）— 多sheet导出
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 基础信息
_G6_2_SEG1_HEADERS = [
    "投资种类", "投资项目", "证券代码", "面值", "持仓数量(账面)",
    "票面利率(%)", "实际利率(%)", "到期日", "计息方式", "付息周期",
    "信用评级", "担保情况",
]
_G6_2_SEG1_KEYS = [
    "investCategory", "investProject", "securitiesCode", "faceValue", "bookQuantity",
    "couponRate", "effectiveRate", "maturityDate", "interestMethod", "paymentCycle",
    "creditRating", "guarantee",
]

# 区段2: 期初+变动(12列)
_G6_2_SEG2_HEADERS = [
    "期初成本", "期初利息调整", "期初应计利息", "期初小计",
    "本期增加", "本期减少", "利息收入", "本期变动小计",
    "期初减值准备", "期初公允价值变动", "期初摊余成本", "期初备注",
]
_G6_2_SEG2_KEYS = [
    "openingCost", "openingInterestAdj", "openingAccruedInterest", "openingSubtotal",
    "periodIncrease", "periodDecrease", "interestIncome", "periodChangeSubtotal",
    "openingImpairment", "openingFVChange", "openingAmortizedCost", "openingRemark",
]

# 区段3: 期末+审定(11列)
_G6_2_SEG3_HEADERS = [
    "期末成本", "期末利息调整", "期末应计利息", "期末小计",
    "期末减值准备", "期末公允价值变动", "期末摊余成本",
    "审定调整", "审定数", "索引", "备注",
]
_G6_2_SEG3_KEYS = [
    "closingCost", "closingInterestAdj", "closingAccruedInterest", "closingSubtotal",
    "closingImpairment", "closingFVChange", "closingAmortizedCost",
    "auditAdjustment", "auditedAmount", "indexRef", "closingRemark",
]

# 全列合并（用于导入解析）
_G6_2_ALL_HEADERS = _G6_2_SEG1_HEADERS + _G6_2_SEG2_HEADERS + _G6_2_SEG3_HEADERS
_G6_2_ALL_KEYS = _G6_2_SEG1_KEYS + _G6_2_SEG2_KEYS + _G6_2_SEG3_KEYS

_G6_2_SEGMENTS = [
    ("基础信息", _G6_2_SEG1_HEADERS, _G6_2_SEG1_KEYS),
    ("期初+变动", _G6_2_SEG2_HEADERS, _G6_2_SEG2_KEYS),
    ("期末+审定", _G6_2_SEG3_HEADERS, _G6_2_SEG3_KEYS),
]

# G6-2 数值字段
_G6_2_NUMERIC_KEYS = {
    "faceValue", "bookQuantity", "couponRate", "effectiveRate",
    "openingCost", "openingInterestAdj", "openingAccruedInterest", "openingSubtotal",
    "periodIncrease", "periodDecrease", "interestIncome", "periodChangeSubtotal",
    "openingImpairment", "openingFVChange", "openingAmortizedCost",
    "closingCost", "closingInterestAdj", "closingAccruedInterest", "closingSubtotal",
    "closingImpairment", "closingFVChange", "closingAmortizedCost",
    "auditAdjustment", "auditedAmount",
}

# ═══════════════════════════════════════════════════════════════════════════════
# G6-3 坏账准备明细表（20列，2区段Tab）— 多sheet导出
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 未审+调整(10列)
_G6_3_SEG1_HEADERS = [
    "投资项目", "所属Stage", "账面余额①", "预期信用损失率②",
    "减值准备③", "账面价值④", "账面余额调整⑤",
    "调整后信用损失率②A", "减值准备调整⑥", "差异说明",
]
_G6_3_SEG1_KEYS = [
    "investProject", "stageGroup", "bookBalance", "creditLossRate",
    "impairmentProvision", "bookValue", "balanceAdjustment",
    "adjustedCreditLossRate", "impairmentAdjustment", "differenceNote",
]

# 区段2: 审定数(10列)
_G6_3_SEG2_HEADERS = [
    "投资项目", "所属Stage", "审定账面余额⑦", "审定减值准备⑧",
    "审定账面价值⑨", "上年减值准备", "本年计提",
    "本年转回", "本年核销", "备注",
]
_G6_3_SEG2_KEYS = [
    "investProject", "stageGroup", "adjBookBalance", "adjImpairment",
    "adjBookValue", "priorImpairment", "currentProvision",
    "currentReversal", "currentWriteOff", "remark",
]

# 全列合并
_G6_3_ALL_HEADERS = [
    "投资项目", "所属Stage", "账面余额①", "预期信用损失率②",
    "减值准备③", "账面价值④", "账面余额调整⑤",
    "调整后信用损失率②A", "减值准备调整⑥",
    "审定账面余额⑦", "审定减值准备⑧", "审定账面价值⑨",
    "上年减值准备", "本年计提", "本年转回", "本年核销",
    "差异说明", "备注",
]
_G6_3_ALL_KEYS = [
    "investProject", "stageGroup", "bookBalance", "creditLossRate",
    "impairmentProvision", "bookValue", "balanceAdjustment",
    "adjustedCreditLossRate", "impairmentAdjustment",
    "adjBookBalance", "adjImpairment", "adjBookValue",
    "priorImpairment", "currentProvision", "currentReversal", "currentWriteOff",
    "differenceNote", "remark",
]

_G6_3_SEGMENTS = [
    ("未审+调整", _G6_3_SEG1_HEADERS, _G6_3_SEG1_KEYS),
    ("审定数", _G6_3_SEG2_HEADERS, _G6_3_SEG2_KEYS),
]

# G6-3 数值字段
_G6_3_NUMERIC_KEYS = {
    "bookBalance", "creditLossRate", "impairmentProvision", "bookValue",
    "balanceAdjustment", "adjustedCreditLossRate", "impairmentAdjustment",
    "adjBookBalance", "adjImpairment", "adjBookValue",
    "priorImpairment", "currentProvision", "currentReversal", "currentWriteOff",
}

# ═══════════════════════════════════════════════════════════════════════════════
# G6-4 调整分录汇总（10列，单sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

_G6_4_HEADERS = [
    "调整事项说明", "类别（报表调整/账项调整/其他）", "报表项目", "科目代码", "科目名称",
    "附注项目", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_G6_4_KEYS = [
    "description", "category", "reportItem", "accountCode", "accountName",
    "noteItem", "debitAmount", "creditAmount", "indexRef", "remark",
]

# G6-4 数值字段
_G6_4_NUMERIC_KEYS = {"debitAmount", "creditAmount"}


# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G6-2": "G6-2-rows",
    "G6-3": "G6-3-rows",
    "G6-4": "G6-4-rows",
}

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


# ═══════════════════════════════════════════════════════════════════════════════
# G6-2 多sheet导出（3区段→3 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g6_2_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G6-2 按3区段分sheet导出，每个区段一个worksheet."""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G6_2_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        ws.append([f"G6-2 明细表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16

        if not template_only:
            for row_data in rows:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G6-2 其他债权投资明细表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "基础信息区段含：投资种类/项目、证券代码、面值、持仓数量(账面)、利率、到期日等。",
        "持仓数量(账面)为资产负债表日账面持仓，供 G6-9 盘点 / G6-10 倒轧带入。",
        "期初小计=期初成本+期初利息调整+期初应计利息（前端自动计算）。",
        "期末小计=期初小计+本期增加-本期减少+利息收入（前端自动计算）。",
        "票面利率和实际利率填百分比数值（如5.5表示5.5%）。",
        "所有金额列以元为单位。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g6_2_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-2导入文件，支持多sheet或单sheet两种格式。返回(rows, errors)."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet格式（3区段分sheet）
    multi_sheet = len(wb.sheetnames) >= 3 and any("基础信息" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G6_2_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append({"row_number": 0, "field": "", "reason": f"缺少工作表: {seg_name}"})
                continue
            header_row_idx = 2
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {"id": str(uuid4())}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    if col_i >= len(values):
                        break
                    raw = values[col_i]
                    if key in _G6_2_NUMERIC_KEYS:
                        rows_dict[row_idx][key] = safe_float(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
    else:
        # 策略2: 单sheet宽表
        ws = wb.active
        if ws is None:
            wb.close()
            return [], [{"row_number": 0, "field": "", "reason": "xlsx文件中无活动工作表"}]
        header_row_idx = 1
        for r in range(1, min(5, (ws.max_row or 1) + 1)):
            row_cells = list(ws.iter_rows(min_row=r, max_row=r))
            if not row_cells:
                continue
            test_row = [str(c.value).strip() if c.value else "" for c in row_cells[0]]
            if "投资项目" in test_row or "投资种类" in test_row:
                header_row_idx = r
                break
        header_cells = list(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        if not header_cells:
            wb.close()
            return [], [{"row_number": 0, "field": "", "reason": "无有效表头行"}]
        actual_headers = [str(c.value).strip() if c.value else "" for c in header_cells[0]]
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append({"row_number": row_idx, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in _G6_2_ALL_HEADERS:
                    key_idx = _G6_2_ALL_HEADERS.index(h)
                    key = _G6_2_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_2_NUMERIC_KEYS:
                        parsed[key] = safe_float(raw)
                    else:
                        parsed[key] = safe_str(raw)
            rows_dict[row_idx] = parsed

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append({"row_number": ROW_LIMIT, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G6-3 多sheet导出（2区段→2 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g6_3_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G6-3 按2区段分sheet导出，每个区段一个worksheet."""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G6_3_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        ws.append([f"G6-3 坏账准备明细表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16

        if not template_only:
            for row_data in rows:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G6-3 坏账准备明细表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "20列拆为2区段Tab：未审+调整(10列) / 审定数(10列)。",
        "ECL公式链：③=①×②, ④=①-③, ⑥=⑤×②A+①×(②A-②), ⑦=①+⑤, ⑧=③+⑥, ⑨=⑦-⑧。",
        "导入后公式列前端自动重算。",
        "所属Stage填：Stage1 / Stage2 / Stage3 / 单项。",
        "信用损失率②和调整后信用损失率②A填小数（如 0.05 表示 5%）。",
        "损失率必须在[0,1]范围内，超出将触发红框高亮。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g6_3_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-3导入文件。返回(rows, errors)."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet
    multi_sheet = len(wb.sheetnames) >= 2 and any("未审" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G6_3_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append({"row_number": 0, "field": "", "reason": f"缺少工作表: {seg_name}"})
                continue
            header_row_idx = 2
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {"id": str(uuid4())}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    if col_i >= len(values):
                        break
                    raw = values[col_i]
                    if key in _G6_3_NUMERIC_KEYS:
                        rows_dict[row_idx][key] = safe_float(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
    else:
        # 策略2: 单sheet宽表
        ws = wb.active
        if ws is None:
            wb.close()
            return [], [{"row_number": 0, "field": "", "reason": "xlsx文件中无活动工作表"}]
        header_row_idx = 1
        for r in range(1, min(5, (ws.max_row or 1) + 1)):
            row_cells = list(ws.iter_rows(min_row=r, max_row=r))
            if not row_cells:
                continue
            test_row = [str(c.value).strip() if c.value else "" for c in row_cells[0]]
            if "投资项目" in test_row or "账面余额" in test_row:
                header_row_idx = r
                break
        header_cells = list(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        if not header_cells:
            wb.close()
            return [], [{"row_number": 0, "field": "", "reason": "无有效表头行"}]
        actual_headers = [str(c.value).strip() if c.value else "" for c in header_cells[0]]
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append({"row_number": row_idx, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in _G6_3_ALL_HEADERS:
                    key_idx = _G6_3_ALL_HEADERS.index(h)
                    key = _G6_3_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_3_NUMERIC_KEYS:
                        parsed[key] = safe_float(raw)
                    else:
                        parsed[key] = safe_str(raw)
            rows_dict[row_idx] = parsed

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append({"row_number": ROW_LIMIT, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# 端点: export-template
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g6-main/export-template")
async def g6_main_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)

    if sheet == "G6-2":
        wb = _build_g6_2_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G6-2_明细表_模板.xlsx")
    elif sheet == "G6-3":
        wb = _build_g6_3_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G6-3_坏账准备明细表_模板.xlsx")
    else:  # G6-4
        wb = build_workbook_template(
            "G6-4",
            _G6_4_HEADERS,
            title="G6-4 调整分录汇总",
            guidance=[
                "G6-4 调整分录汇总 编制说明",
                "",
                "列结构对齐 Excel：调整事项说明 / 类别 / 报表项目 / 科目 / 附注项目 / 借贷金额 / 索引 / 备注。",
                "类别填：账项调整、报表调整、其他。报表调整不回写审定表。",
                "同一调整事项的借方合计与贷方合计必须相等（借贷平衡）。",
                "科目代码示例：150301 成本、150302 利息调整、150305 减值准备。",
            ],
        )
        return workbook_to_response(wb, "G6-4_调整分录_模板.xlsx")


# ═══════════════════════════════════════════════════════════════════════════════
# 端点: export-data
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g6-main/export-data")
async def g6_main_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    item_id = _ITEM_IDS[sheet]
    rows = await load_json_rows(db, wp_id, item_id, field="conclusion")

    if sheet == "G6-2":
        wb = _build_g6_2_multi_sheet_workbook(rows)
        return workbook_to_response(wb, "G6-2_明细表_数据.xlsx")
    elif sheet == "G6-3":
        wb = _build_g6_3_multi_sheet_workbook(rows)
        return workbook_to_response(wb, "G6-3_坏账准备明细表_数据.xlsx")
    else:  # G6-4
        wb = build_workbook_template(
            "G6-4",
            _G6_4_HEADERS,
            title="G6-4 调整分录汇总",
            guidance=["每行一笔调整分录。借贷平衡校验由前端完成。"],
        )
        ws = wb["G6-4"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G6_4_KEYS))
        return workbook_to_response(wb, "G6-4_调整分录_数据.xlsx")


# ═══════════════════════════════════════════════════════════════════════════════
# 端点: import-data
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g6-main/import-data")
async def g6_main_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _validate_sheet(sheet)

    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(422, "仅支持 .xlsx/.xls 格式文件")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(422, "文件大小超过10MB限制")

    if sheet == "G6-2":
        rows, errors = _parse_g6_2_import(content)
    elif sheet == "G6-3":
        rows, errors = _parse_g6_3_import(content)
    else:  # G6-4
        rows, errors = _parse_g6_4_import(content)

    if not rows and errors:
        raise HTTPException(422, detail={"message": "导入失败", "errors": errors})

    # 持久化
    item_id = _ITEM_IDS[sheet]
    await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")

    return {
        "ok": True,
        "imported_count": len(rows),
        "errors": errors,
        "sheet": sheet,
    }


def _parse_g6_4_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-4导入文件（单sheet，10列）。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows: list[dict] = []

    ws = wb.active
    if ws is None:
        wb.close()
        return [], [{"row_number": 0, "field": "", "reason": "xlsx文件中无活动工作表"}]

    # 找表头行
    header_row_idx = 1
    for r in range(1, min(5, (ws.max_row or 1) + 1)):
        row_cells = list(ws.iter_rows(min_row=r, max_row=r))
        if not row_cells:
            continue
        test_row = [str(c.value).strip() if c.value else "" for c in row_cells[0]]
        if (
            "调整事项说明" in test_row
            or "类别" in "".join(test_row)
            or "序号" in test_row
            or "分录类型" in test_row
            or "摘要" in test_row
        ):
            header_row_idx = r
            break

    for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
        if all(v is None for v in row):
            continue
        if row_idx >= ROW_LIMIT:
            errors.append({"row_number": row_idx, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
            break
        values = list(row) + [None] * max(0, len(_G6_4_KEYS) - len(row))
        parsed: dict[str, Any] = {"id": str(uuid4())}
        for col_i, key in enumerate(_G6_4_KEYS):
            if col_i >= len(values):
                break
            raw = values[col_i]
            if key in _G6_4_NUMERIC_KEYS:
                parsed[key] = safe_float(raw)
            else:
                parsed[key] = safe_str(raw)
        rows.append(parsed)

    wb.close()
    return rows, errors
