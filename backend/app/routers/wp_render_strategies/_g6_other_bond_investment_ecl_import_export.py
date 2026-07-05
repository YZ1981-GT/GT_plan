"""G6 其他债权投资(ECL组) — 导入导出端点

支持 3 张动态行表格：
  G6-12 减值准备测算表(22列→2区段Tab) /
  G6-14 转回核销检查表(42行×8列) /
  G6-15 凭证检查表(22列→3区段Tab)

字段键与前端 composable（useG6EclImpairmentCalc / useG6EclReversalWriteOff /
useG6EclVoucherCheck 的行接口）严格对齐，保证 round-trip。

G6-12 按2区段分sheet导出（未审+调整 / 审定数）。
G6-14 单sheet导出（8列简洁结构）。
G6-15 按3区段分sheet导出（凭证基础 / 核对内容 / 结论）。
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
    parse_row_by_headers,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_rows,
    workbook_to_response,
)

router = APIRouter(tags=["g6-ecl-import-export"])


# ═══════════════════════════════════════════════════════════════════════════════
# G6-12 减值准备测算表（22列 → 2区段Tab多sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 未审+调整(12列)
_G6_12_SEG1_HEADERS = [
    "投资项目", "摊余成本余额①", "公允价值", "预期信用损失率②",
    "坏账准备③", "账面价值④", "余额调整⑤",
    "调整后损失率②A", "坏账调整⑥", "阶段", "OCI影响", "索引",
]
_G6_12_SEG1_KEYS = [
    "investProject", "amortizedCost", "fairValue", "creditLossRate",
    "impairmentProvision", "bookValue", "balanceAdjustment",
    "adjustedCreditLossRate", "impairmentAdjustment", "stage", "ociImpact", "indexRef",
]

# 区段2: 审定数(10列)
_G6_12_SEG2_HEADERS = [
    "投资项目", "审定余额⑦", "审定坏账⑧", "审定账面价值⑨",
    "审定公允价值", "上年坏账", "本年计提",
    "本年转回", "OCI调整", "差异说明",
]
_G6_12_SEG2_KEYS = [
    "investProject", "adjBalance", "adjImpairment", "adjBookValue",
    "adjFairValue", "priorImpairment", "currentProvision",
    "currentReversal", "ociAdjustment", "differenceNote",
]

# 全列合并（用于导入解析）
_G6_12_ALL_HEADERS = [
    "投资项目", "摊余成本余额①", "公允价值", "预期信用损失率②",
    "坏账准备③", "账面价值④", "余额调整⑤",
    "调整后损失率②A", "坏账调整⑥", "阶段", "OCI影响",
    "审定余额⑦", "审定坏账⑧", "审定账面价值⑨",
    "审定公允价值", "上年坏账", "本年计提",
    "本年转回", "OCI调整", "差异说明", "索引",
]
_G6_12_ALL_KEYS = [
    "investProject", "amortizedCost", "fairValue", "creditLossRate",
    "impairmentProvision", "bookValue", "balanceAdjustment",
    "adjustedCreditLossRate", "impairmentAdjustment", "stage", "ociImpact",
    "adjBalance", "adjImpairment", "adjBookValue",
    "adjFairValue", "priorImpairment", "currentProvision",
    "currentReversal", "ociAdjustment", "differenceNote", "indexRef",
]

_G6_12_SEGMENTS = [
    ("未审+调整", _G6_12_SEG1_HEADERS, _G6_12_SEG1_KEYS),
    ("审定数", _G6_12_SEG2_HEADERS, _G6_12_SEG2_KEYS),
]

# G6-12 数值字段
_G6_12_NUMERIC_KEYS = {
    "amortizedCost", "fairValue", "creditLossRate",
    "impairmentProvision", "bookValue", "balanceAdjustment",
    "adjustedCreditLossRate", "impairmentAdjustment", "ociImpact",
    "adjBalance", "adjImpairment", "adjBookValue",
    "adjFairValue", "priorImpairment", "currentProvision",
    "currentReversal", "ociAdjustment",
}


# ═══════════════════════════════════════════════════════════════════════════════
# G6-14 转回核销检查表（8列，单sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

_G6_14_HEADERS = [
    "序号", "投资项目", "转回/核销类型", "金额",
    "原因", "审批程序", "合理性结论", "索引",
]
_G6_14_KEYS = [
    "seq", "investProject", "type", "amount",
    "reason", "approvalProcedure", "reasonConclusion", "indexRef",
]

# G6-14 数值字段
_G6_14_NUMERIC_KEYS = {"seq", "amount"}


# ═══════════════════════════════════════════════════════════════════════════════
# G6-15 凭证检查表（22列 → 3区段Tab多sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 凭证基础(8列)
_G6_15_SEG1_HEADERS = [
    "日期", "凭证号", "业务内容", "对方科目",
    "明细", "借方", "贷方", "附件",
]
_G6_15_SEG1_KEYS = [
    "date", "voucherNo", "businessContent", "counterAccount",
    "detailAccount", "debitAmount", "creditAmount", "attachment",
]

# 区段2: 核对内容(8列)
_G6_15_SEG2_HEADERS = [
    "凭证号", "支持性文件",
    "核对1-原始凭证(是/否)", "核对2-授权(是/否)",
    "核对3-账务(是/否)", "核对4-金额(是/否)",
    "核对5-分类(是/否)", "核对6-减值(是/否)", "核对7-利息(是/否)",
]
_G6_15_SEG2_KEYS = [
    "voucherNo", "supportingDoc",
    "checkOriginal", "checkAuthorized",
    "checkAccounting", "checkAmount",
    "checkClassification", "checkImpairment", "checkInterest",
]

# 区段3: 结论(6列)
_G6_15_SEG3_HEADERS = [
    "凭证号", "索引", "是否异常(是/否)", "异常说明",
    "风险等级", "处理建议", "备注",
]
_G6_15_SEG3_KEYS = [
    "voucherNo", "indexRef", "isAbnormal", "abnormalNote",
    "riskLevel", "suggestion", "remark",
]

_G6_15_SEGMENTS = [
    ("凭证基础", _G6_15_SEG1_HEADERS, _G6_15_SEG1_KEYS),
    ("核对内容", _G6_15_SEG2_HEADERS, _G6_15_SEG2_KEYS),
    ("结论", _G6_15_SEG3_HEADERS, _G6_15_SEG3_KEYS),
]

# 全列合并（用于导入解析）
_G6_15_ALL_HEADERS = [
    "日期", "凭证号", "业务内容", "对方科目",
    "明细", "借方", "贷方", "附件",
    "支持性文件",
    "核对1-原始凭证(是/否)", "核对2-授权(是/否)",
    "核对3-账务(是/否)", "核对4-金额(是/否)",
    "核对5-分类(是/否)", "核对6-减值(是/否)", "核对7-利息(是/否)",
    "索引", "是否异常(是/否)", "异常说明",
    "风险等级", "处理建议", "备注",
]
_G6_15_ALL_KEYS = [
    "date", "voucherNo", "businessContent", "counterAccount",
    "detailAccount", "debitAmount", "creditAmount", "attachment",
    "supportingDoc",
    "checkOriginal", "checkAuthorized",
    "checkAccounting", "checkAmount",
    "checkClassification", "checkImpairment", "checkInterest",
    "indexRef", "isAbnormal", "abnormalNote",
    "riskLevel", "suggestion", "remark",
]

# G6-15 数值字段
_G6_15_NUMERIC_KEYS = {"debitAmount", "creditAmount"}

# G6-15 布尔字段
_G6_15_BOOL_KEYS = {
    "checkOriginal", "checkAuthorized", "checkAccounting",
    "checkAmount", "checkClassification", "checkImpairment",
    "checkInterest", "isAbnormal",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G6-12": "G6-12-rows",
    "G6-14": "G6-14-rows",
    "G6-15": "G6-15-rows",
}

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


def _parse_bool(val: Any) -> bool:
    """解析布尔值：'是'/True/'true'/'1' → True, 其他 → False."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("是", "true", "1", "yes", "✓", "√")


def _export_bool(val: Any) -> str:
    """导出布尔值：True→'是', False→'否'."""
    return "是" if val else "否"


def _parse_row_with_types(
    row: tuple,
    headers: list[str],
    field_keys: list[str],
    numeric_keys: set[str],
    bool_keys: set[str] | None = None,
) -> dict[str, Any]:
    """通用行解析，支持数值/布尔/字符串三种类型."""
    values = list(row) + [None] * max(0, len(headers) - len(row))
    out: dict[str, Any] = {"id": str(uuid4())}
    for i, key in enumerate(field_keys):
        if key == "id":
            continue
        raw = values[i] if i < len(values) else None
        if key in numeric_keys:
            out[key] = safe_float(raw)
        elif bool_keys and key in bool_keys:
            out[key] = _parse_bool(raw)
        else:
            out[key] = safe_str(raw)
    return out


def _export_row_with_types(
    data: dict,
    field_keys: list[str],
    bool_keys: set[str] | None = None,
) -> list:
    """通用行导出，布尔字段导出为"是/否"."""
    row: list[Any] = []
    for key in field_keys:
        val = data.get(key)
        if bool_keys and key in bool_keys:
            row.append(_export_bool(val))
        elif isinstance(val, (float, int)):
            row.append(val)
        elif val is None:
            row.append("")
        else:
            row.append(val)
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# G6-12 多sheet导出（2区段→2 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g6_12_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G6-12 按2区段分sheet导出，每个区段一个worksheet."""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G6_12_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        # 标题行
        ws.append([f"G6-12 其他债权投资减值准备测算表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        # 表头行
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16

        if not template_only:
            for row_data in rows:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G6-12 其他债权投资减值准备测算表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "22列拆为2区段Tab：未审+调整(12列) / 审定数(10列)。",
        "公式列（③=①×②, ④=①-③, ⑥=⑤×②A+①×(②A-②), ⑦=①+⑤, ⑧=③+⑥, ⑨=⑦-⑧）导入后前端自动重算。",
        "阶段填：Stage1 / Stage2 / Stage3。",
        "预期信用损失率②和调整后损失率②A填小数（如 0.05 表示 5%）。",
        "坏账调整⑥可为负数（当审计师调低信用损失率时=冲回）。",
        "OCI影响/OCI调整为其他债权投资特有列（FVOCI类减值通过OCI调整）。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g6_12_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-12导入文件，支持多sheet或单sheet两种格式。返回(rows, errors)."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet格式（2区段分sheet）
    multi_sheet = len(wb.sheetnames) >= 2 and any("未审" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G6_12_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append({"row_number": 0, "field": "", "reason": f"缺少工作表: {seg_name}"})
                continue
            header_row_idx = 2
            actual_headers = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
            ]
            missing = [h for h in seg_headers if h not in actual_headers]
            if missing:
                errors.append({"row_number": 0, "field": seg_name, "reason": f"缺少列: {', '.join(missing)}"})
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {"id": str(uuid4())}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    if key == "id":
                        continue
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_12_NUMERIC_KEYS:
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
            if "投资项目" in test_row or "摊余成本" in test_row:
                header_row_idx = r
                break
        header_cells = list(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        if not header_cells:
            errors.append({"row_number": 0, "field": "", "reason": "xlsx文件中无有效表头行"})
            wb.close()
            return [], errors
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in header_cells[0]
        ]
        if "投资项目" not in actual_headers:
            errors.append({"row_number": header_row_idx, "field": "", "reason": "无法识别表头，缺少'投资项目'列"})
            wb.close()
            return [], errors
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append({"row_number": row_idx + header_row_idx + 1, "field": "", "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in _G6_12_ALL_HEADERS:
                    key_idx = _G6_12_ALL_HEADERS.index(h)
                    key = _G6_12_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_12_NUMERIC_KEYS:
                        parsed[key] = safe_float(raw)
                    else:
                        parsed[key] = safe_str(raw)
            rows_dict[row_idx] = parsed

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append({"row_number": ROW_LIMIT, "field": "", "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G6-15 多sheet导出（3区段→3 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g6_15_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G6-15 按3区段分sheet导出."""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G6_15_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        ws.append([f"G6-15 凭证检查表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16

        if not template_only:
            for row_data in rows:
                ws.append(_export_row_with_types(
                    row_data, seg_keys, bool_keys=_G6_15_BOOL_KEYS,
                ))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G6-15 凭证检查表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "22列拆为3区段Tab：凭证基础(8列) / 核对内容(8列) / 结论(6列)。",
        "核对列填：是/否（是=通过，否=不通过）。",
        "7项核对全通过时，前端自动标记为正常凭证。任一核对为'否'时标记为异常。",
        "借方金额和贷方金额为数值列。",
        "凭证号用于跨区段行关联（同一凭证号的行在3个sheet间对应同一笔）。",
        "风险等级填：高 / 中 / 低。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g6_15_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-15导入文件。返回(rows, errors)."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet
    multi_sheet = len(wb.sheetnames) >= 3 and any("凭证基础" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G6_15_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append({"row_number": 0, "field": seg_name, "reason": f"缺少工作表: {seg_name}"})
                continue
            header_row_idx = 2
            actual_headers = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
            ]
            missing = [h for h in seg_headers if h not in actual_headers]
            if missing:
                errors.append({"row_number": 0, "field": seg_name, "reason": f"缺少列: {', '.join(missing)}"})
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {"id": str(uuid4())}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    if key == "id":
                        continue
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_15_NUMERIC_KEYS:
                        rows_dict[row_idx][key] = safe_float(raw)
                    elif key in _G6_15_BOOL_KEYS:
                        rows_dict[row_idx][key] = _parse_bool(raw)
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
            if "凭证号" in test_row or "日期" in test_row:
                header_row_idx = r
                break
        header_cells = list(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        if not header_cells:
            errors.append({"row_number": 0, "field": "", "reason": "xlsx文件中无有效表头行"})
            wb.close()
            return [], errors
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in header_cells[0]
        ]
        if "凭证号" not in actual_headers and "日期" not in actual_headers:
            errors.append({"row_number": header_row_idx, "field": "", "reason": "无法识别表头，缺少'凭证号'或'日期'列"})
            wb.close()
            return [], errors
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append({"row_number": row_idx + header_row_idx + 1, "field": "", "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in _G6_15_ALL_HEADERS:
                    key_idx = _G6_15_ALL_HEADERS.index(h)
                    key = _G6_15_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_15_NUMERIC_KEYS:
                        parsed[key] = safe_float(raw)
                    elif key in _G6_15_BOOL_KEYS:
                        parsed[key] = _parse_bool(raw)
                    else:
                        parsed[key] = safe_str(raw)
            rows_dict[row_idx] = parsed

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append({"row_number": ROW_LIMIT, "field": "", "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g6-ecl/export-template")
async def g6_ecl_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空模板（含表头+编制说明）."""
    _validate_sheet(sheet)

    if sheet == "G6-12":
        wb = _build_g6_12_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G6-12_减值准备测算表_模板.xlsx")
    elif sheet == "G6-14":
        wb = build_workbook_template(
            "G6-14",
            _G6_14_HEADERS,
            title="G6-14 减值准备转回（收回）、核销检查表",
            guidance=[
                "G6-14 转回核销检查表 编制说明",
                "",
                "每行一笔转回/核销/收回记录。",
                "转回/核销类型填：转回 / 核销 / 收回。",
                "合理性结论填：合理 / 基本合理 / 不合理。",
                "金额为数值列。",
            ],
        )
        return workbook_to_response(wb, "G6-14_转回核销检查表_模板.xlsx")
    else:  # G6-15
        wb = _build_g6_15_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G6-15_凭证检查表_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g6-ecl/export-data")
async def g6_ecl_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出已填写数据."""
    _validate_sheet(sheet)

    if sheet == "G6-12":
        item_id = _ITEM_IDS["G6-12"]
        rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
        wb = _build_g6_12_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G6-12_减值准备测算表_数据.xlsx")

    elif sheet == "G6-14":
        item_id = _ITEM_IDS["G6-14"]
        rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
        wb = build_workbook_template(
            "G6-14",
            _G6_14_HEADERS,
            title="G6-14 减值准备转回（收回）、核销检查表",
            guidance=["每行一笔转回/核销/收回记录。类型填转回/核销/收回。"],
        )
        ws = wb["G6-14"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G6_14_KEYS))
        return workbook_to_response(wb, "G6-14_转回核销检查表_数据.xlsx")

    else:  # G6-15
        item_id = _ITEM_IDS["G6-15"]
        rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
        wb = _build_g6_15_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G6-15_凭证检查表_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g6-ecl/import-data")
async def g6_ecl_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx数据."""
    _validate_sheet(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    if sheet == "G6-12":
        rows, errors = _parse_g6_12_import(content)
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        item_id = _ITEM_IDS["G6-12"]
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
        out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
        if len(rows) >= ROW_LIMIT:
            out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        return out

    elif sheet == "G6-14":
        try:
            actual, raw = parse_upload_xlsx(content, _G6_14_HEADERS, header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [{"row_number": 0, "field": "", "reason": str(e)}], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        rows: list[dict] = []
        errors: list[dict] = []
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append({"row_number": i + 2, "field": "", "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
                break
            parsed = parse_row_by_headers(r, actual, _G6_14_KEYS)
            # 校验type值
            type_val = parsed.get("type", "")
            if type_val and type_val not in ("转回", "核销", "收回", ""):
                errors.append({
                    "row_number": i + 2,
                    "field": "type",
                    "reason": f"类型'{type_val}'无效，应为 转回/核销/收回",
                })
            rows.append(parsed)
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        item_id = _ITEM_IDS["G6-14"]
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
        return {"ok": True, "imported_count": len(rows), "errors": errors}

    else:  # G6-15
        rows, errors = _parse_g6_15_import(content)
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        item_id = _ITEM_IDS["G6-15"]
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
        out = {"ok": True, "imported_count": len(rows), "errors": errors}
        if len(rows) >= ROW_LIMIT:
            out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        return out
