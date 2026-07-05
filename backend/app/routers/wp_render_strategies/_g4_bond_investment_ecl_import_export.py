"""G4 债权投资(ECL组) — 导入导出端点

支持 4 张动态行表格：
  G4-9 三阶段划分 / G4-10 减值准备测算表(2区段Tab) /
  G4-12 转回核销检查表(2Tab) / G4-13 凭证检查表(3区段Tab)

字段键与前端 composable（useG4EclStageClassification / useG4EclImpairmentCalc /
useG4EclReversalWriteOff / useG4EclVoucherCheck 的行接口）严格对齐，保证 round-trip。

G4-10 按2区段分sheet导出（未审数+审计调整 / 审定数+差异）。
G4-12 按2Tab分sheet导出（转回检查 / 核销检查）。
G4-13 按3区段分sheet导出（记账凭证 / 支持性文件+核对 / 结论+备注）。
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

router = APIRouter(tags=["g4-ecl-import-export"])


# ═══════════════════════════════════════════════════════════════════════════════
# G4-9 三阶段划分（11列，单sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

_G4_9_HEADERS = [
    "投资项目", "初始信用评级", "当前信用评级", "评级变动",
    "是否逾期30天以上(是/否)", "是否发生信用减值事件(是/否)",
    "企业划分阶段", "审计判断阶段", "一致性(是/否)",
    "差异说明", "索引",
]
_G4_9_KEYS = [
    "investProject", "initialRating", "currentRating", "ratingChange",
    "overdue30Days", "creditImpaired",
    "companyStage", "auditStage", "isConsistent",
    "discrepancyNote", "indexRef",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G4-10 减值准备测算表（19列 → 2区段Tab多sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 未审数+审计调整(11列)
_G4_10_SEG1_HEADERS = [
    "投资项目", "所属Stage", "账面余额①", "预计未来现金流量现值",
    "预期信用损失率②", "减值准备③", "账面价值④",
    "账面余额调整⑤", "调整后信用损失率②A", "减值准备调整⑥", "差异说明",
]
_G4_10_SEG1_KEYS = [
    "investProject", "stageGroup", "bookBalance", "pvFutureCashFlow",
    "creditLossRate", "impairmentProvision", "bookValue",
    "balanceAdjustment", "adjustedCreditLossRate", "impairmentAdjustment", "differenceNote",
]

# 区段2: 审定数+差异(8列)
_G4_10_SEG2_HEADERS = [
    "投资项目", "所属Stage", "审定账面余额⑦", "审定减值准备⑧",
    "审定账面价值⑨", "上年减值准备", "本年计提", "本年转回",
]
_G4_10_SEG2_KEYS = [
    "investProject", "stageGroup", "adjBookBalance", "adjImpairment",
    "adjBookValue", "priorImpairment", "currentProvision", "currentReversal",
]

# 全列合并（用于导入解析）
_G4_10_ALL_HEADERS = [
    "投资项目", "所属Stage", "账面余额①", "预计未来现金流量现值",
    "预期信用损失率②", "减值准备③", "账面价值④",
    "账面余额调整⑤", "调整后信用损失率②A", "减值准备调整⑥",
    "审定账面余额⑦", "审定减值准备⑧", "审定账面价值⑨",
    "上年减值准备", "本年计提", "本年转回", "差异说明",
]
_G4_10_ALL_KEYS = [
    "investProject", "stageGroup", "bookBalance", "pvFutureCashFlow",
    "creditLossRate", "impairmentProvision", "bookValue",
    "balanceAdjustment", "adjustedCreditLossRate", "impairmentAdjustment",
    "adjBookBalance", "adjImpairment", "adjBookValue",
    "priorImpairment", "currentProvision", "currentReversal", "differenceNote",
]

_G4_10_SEGMENTS = [
    ("未审数+审计调整", _G4_10_SEG1_HEADERS, _G4_10_SEG1_KEYS),
    ("审定数+差异", _G4_10_SEG2_HEADERS, _G4_10_SEG2_KEYS),
]

# ═══════════════════════════════════════════════════════════════════════════════
# G4-12 转回核销检查表（20列 → 2 Tab多sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

# Tab1: 转回检查(10列)
_G4_12_TAB1_HEADERS = [
    "序号", "单位名称", "转回原因", "收回方式", "原确定坏账准备依据",
    "收回或转回金额", "收回前累计计提", "合理性分析", "是否合理", "索引",
]
_G4_12_TAB1_KEYS = [
    "seq", "unitName", "reversalReason", "recoveryMethod", "originalBasis",
    "reversalAmount", "accumulatedProvision", "reasonAnalysis", "isReasonable", "indexRef",
]

# Tab2: 核销检查(10列)
_G4_12_TAB2_HEADERS = [
    "序号", "单位名称", "核销性质", "核销金额", "核销原因",
    "核销程序", "是否关联交易(是/否)", "合理性分析", "是否合理", "索引",
]
_G4_12_TAB2_KEYS = [
    "seq", "unitName", "writeOffType", "writeOffAmount", "writeOffReason",
    "writeOffProcedure", "isRelatedParty", "reasonAnalysis", "isReasonable", "indexRef",
]

_G4_12_TABS = [
    ("转回检查", _G4_12_TAB1_HEADERS, _G4_12_TAB1_KEYS),
    ("核销检查", _G4_12_TAB2_HEADERS, _G4_12_TAB2_KEYS),
]

# ═══════════════════════════════════════════════════════════════════════════════
# G4-13 凭证检查表（19列 → 3区段Tab多sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 记账凭证基础列(8列)
_G4_13_SEG1_HEADERS = [
    "区域(借方/贷方)", "日期", "凭证编号", "业务内容",
    "对方科目", "明细科目", "借方金额", "贷方金额",
]
_G4_13_SEG1_KEYS = [
    "section", "date", "voucherNo", "businessContent",
    "counterAccount", "detailAccount", "debitAmount", "creditAmount",
]

# 区段2: 支持性文件+核对内容(7列)
_G4_13_SEG2_HEADERS = [
    "区域(借方/贷方)", "凭证编号", "支持性文件描述",
    "核对1-原始凭证完整(是/否)", "核对2-有授权批准(是/否)",
    "核对3-账务处理正确(是/否)", "核对4-初始成本计算正确(是/否)",
    "核对5-利息计算正确(是/否)", "核对6-减值计提正确(是/否)",
]
_G4_13_SEG2_KEYS = [
    "section", "voucherNo", "supportingDocDesc",
    "checkOriginalComplete", "checkAuthorized",
    "checkAccountingCorrect", "checkInitialCostCorrect",
    "checkInterestCorrect", "checkImpairmentCorrect",
]

# 区段3: 结论+备注(4列)
_G4_13_SEG3_HEADERS = [
    "区域(借方/贷方)", "凭证编号", "索引号", "是否异常(是/否)", "异常说明", "备注",
]
_G4_13_SEG3_KEYS = [
    "section", "voucherNo", "indexRef", "isAbnormal", "abnormalNote", "remark",
]

_G4_13_SEGMENTS = [
    ("记账凭证", _G4_13_SEG1_HEADERS, _G4_13_SEG1_KEYS),
    ("支持性文件+核对", _G4_13_SEG2_HEADERS, _G4_13_SEG2_KEYS),
    ("结论+备注", _G4_13_SEG3_HEADERS, _G4_13_SEG3_KEYS),
]

# 全列合并（用于导入解析）
_G4_13_ALL_HEADERS = [
    "区域(借方/贷方)", "日期", "凭证编号", "业务内容",
    "对方科目", "明细科目", "借方金额", "贷方金额",
    "支持性文件描述",
    "核对1-原始凭证完整(是/否)", "核对2-有授权批准(是/否)",
    "核对3-账务处理正确(是/否)", "核对4-初始成本计算正确(是/否)",
    "核对5-利息计算正确(是/否)", "核对6-减值计提正确(是/否)",
    "索引号", "是否异常(是/否)", "异常说明", "备注",
]
_G4_13_ALL_KEYS = [
    "section", "date", "voucherNo", "businessContent",
    "counterAccount", "detailAccount", "debitAmount", "creditAmount",
    "supportingDocDesc",
    "checkOriginalComplete", "checkAuthorized",
    "checkAccountingCorrect", "checkInitialCostCorrect",
    "checkInterestCorrect", "checkImpairmentCorrect",
    "indexRef", "isAbnormal", "abnormalNote", "remark",
]


# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G4-9": "G4-9-rows",
    "G4-10": "G4-10-rows",
    "G4-12": "G4-12-rows",
    "G4-13": "G4-13-rows",
}

# G4-12 分别存储转回和核销
_G4_12_ITEM_IDS = {
    "reversals": "G4-12-reversals",
    "writeOffs": "G4-12-writeoffs",
}

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())

# G4-10 数值字段
_G4_10_NUMERIC_KEYS = {
    "bookBalance", "pvFutureCashFlow", "creditLossRate", "impairmentProvision",
    "bookValue", "balanceAdjustment", "adjustedCreditLossRate", "impairmentAdjustment",
    "adjBookBalance", "adjImpairment", "adjBookValue",
    "priorImpairment", "currentProvision", "currentReversal",
}

# G4-12 数值字段
_G4_12_NUMERIC_KEYS = {
    "seq", "reversalAmount", "accumulatedProvision", "writeOffAmount",
}

# G4-13 数值字段
_G4_13_NUMERIC_KEYS = {
    "debitAmount", "creditAmount",
}

# G4-13 布尔字段
_G4_13_BOOL_KEYS = {
    "checkOriginalComplete", "checkAuthorized", "checkAccountingCorrect",
    "checkInitialCostCorrect", "checkInterestCorrect", "checkImpairmentCorrect",
    "isAbnormal",
}


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
        raw = values[i] if i < len(values) else None
        if key == "id":
            continue
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
# G4-10 多sheet导出（2区段→2 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g4_10_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G4-10 按2区段分sheet导出，每个区段一个worksheet."""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G4_10_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        # 标题行
        ws.append([f"G4-10 减值准备测算表 — {seg_name}"])
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
    ws_guide.append(["G4-10 减值准备测算表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "19列拆为2区段Tab：未审数+审计调整(11列) / 审定数+差异(8列)。",
        "公式列（③=①×②, ④=①-③, ⑥=⑤×②A+①×(②A-②), ⑦=①+⑤, ⑧=③+⑥, ⑨=⑦-⑧）导入后前端自动重算。",
        "所属Stage填：Stage1 / Stage2 / Stage3。",
        "信用损失率②和调整后信用损失率②A填小数（如 0.05 表示 5%）。",
        "减值准备调整⑥可为负数（当审计师调低信用损失率时）。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g4_10_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G4-10导入文件，支持多sheet或单sheet两种格式。返回(rows, errors)."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet格式（2区段分sheet）
    multi_sheet = len(wb.sheetnames) >= 2 and any("未审数" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G4_10_SEGMENTS:
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
                    if key in _G4_10_NUMERIC_KEYS:
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
                if h in _G4_10_ALL_HEADERS:
                    key_idx = _G4_10_ALL_HEADERS.index(h)
                    key = _G4_10_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G4_10_NUMERIC_KEYS:
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
# G4-12 多sheet导出（2 Tab → 2 worksheet: 转回检查 + 核销检查）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g4_12_multi_sheet_workbook(
    reversals: list[dict], writeoffs: list[dict], *, template_only: bool = False
) -> Workbook:
    """G4-12 按2Tab分sheet导出."""
    wb = Workbook()
    wb.remove(wb.active)

    # Tab1: 转回检查
    ws1 = wb.create_sheet(title="转回检查")
    ws1.append(["G4-12 减值准备转回核销检查表 — 转回检查"])
    ws1.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(_G4_12_TAB1_HEADERS), 1))
    ws1["A1"].font = Font(bold=True, size=12)
    ws1.append(_G4_12_TAB1_HEADERS)
    ws1.freeze_panes = "A3"
    for col_idx in range(1, len(_G4_12_TAB1_HEADERS) + 1):
        ws1.column_dimensions[get_column_letter(col_idx)].width = 16
    if not template_only:
        for d in reversals:
            ws1.append(export_row_by_keys(d, _G4_12_TAB1_KEYS))

    # Tab2: 核销检查
    ws2 = wb.create_sheet(title="核销检查")
    ws2.append(["G4-12 减值准备转回核销检查表 — 核销检查"])
    ws2.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(_G4_12_TAB2_HEADERS), 1))
    ws2["A1"].font = Font(bold=True, size=12)
    ws2.append(_G4_12_TAB2_HEADERS)
    ws2.freeze_panes = "A3"
    for col_idx in range(1, len(_G4_12_TAB2_HEADERS) + 1):
        ws2.column_dimensions[get_column_letter(col_idx)].width = 16
    if not template_only:
        for d in writeoffs:
            ws2.append(_export_row_with_types(d, _G4_12_TAB2_KEYS, bool_keys={"isRelatedParty"}))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G4-12 减值准备转回核销检查表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "20列拆为2Tab：转回检查(10列) / 核销检查(10列)。",
        "Tab1 转回检查：收回或转回金额不得超过收回前累计计提（前端自动校验红色高亮）。",
        "Tab2 核销检查：核销性质填 到期/逾期/其他；是否关联交易填 是/否。",
        "是否合理填：合理 / 不合理。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g4_12_import(content: bytes) -> tuple[list[dict], list[dict], list[dict]]:
    """解析G4-12导入文件。返回(reversals, writeoffs, errors)."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    reversals: list[dict] = []
    writeoffs: list[dict] = []

    # 策略1: 多sheet
    has_tabs = any("转回" in s for s in wb.sheetnames) and any("核销" in s for s in wb.sheetnames)

    if has_tabs:
        for tab_name, tab_headers, tab_keys in _G4_12_TABS:
            ws = None
            for name in wb.sheetnames:
                if tab_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append({"row_number": 0, "field": tab_name, "reason": f"缺少工作表: {tab_name}"})
                continue
            header_row_idx = 2
            actual_headers = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
            ]
            missing = [h for h in tab_headers if h not in actual_headers]
            if missing:
                errors.append({"row_number": 0, "field": tab_name, "reason": f"缺少列: {', '.join(missing)}"})
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True), start=1):
                if all(v is None for v in row):
                    continue
                if tab_name == "转回检查":
                    parsed = _parse_row_with_types(
                        row, tab_headers, tab_keys, _G4_12_NUMERIC_KEYS,
                    )
                    reversals.append(parsed)
                else:
                    parsed = _parse_row_with_types(
                        row, tab_headers, tab_keys, _G4_12_NUMERIC_KEYS, bool_keys={"isRelatedParty"},
                    )
                    writeoffs.append(parsed)
    else:
        # 单sheet：尝试第一个sheet作为转回
        ws = wb.active
        if ws is None:
            wb.close()
            return [], [], [{"row_number": 0, "field": "", "reason": "xlsx文件中无活动工作表"}]
        header_row_idx = 2
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        ]
        # 判断是转回还是核销格式
        if "收回或转回金额" in actual_headers or "转回原因" in actual_headers:
            for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
                if all(v is None for v in row):
                    continue
                reversals.append(_parse_row_with_types(
                    row, _G4_12_TAB1_HEADERS, _G4_12_TAB1_KEYS, _G4_12_NUMERIC_KEYS,
                ))
        elif "核销金额" in actual_headers or "核销性质" in actual_headers:
            for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
                if all(v is None for v in row):
                    continue
                writeoffs.append(_parse_row_with_types(
                    row, _G4_12_TAB2_HEADERS, _G4_12_TAB2_KEYS, _G4_12_NUMERIC_KEYS, bool_keys={"isRelatedParty"},
                ))
        else:
            errors.append({"row_number": header_row_idx, "field": "", "reason": "无法识别表头格式（既非转回也非核销）"})

    wb.close()
    return reversals, writeoffs, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G4-13 多sheet导出（3区段→3 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g4_13_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G4-13 按3区段分sheet导出."""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G4_13_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        ws.append([f"G4-13 凭证检查表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16

        if not template_only:
            for row_data in rows:
                ws.append(_export_row_with_types(
                    row_data, seg_keys, bool_keys=_G4_13_BOOL_KEYS,
                ))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G4-13 凭证检查表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "19列拆为3区段Tab：记账凭证(8列) / 支持性文件+核对(9列) / 结论+备注(6列)。",
        "区域(借方/贷方) 填：debit 或 credit。",
        "核对列填：是/否（是=通过，否=不通过）。",
        "6项核对全通过时，前端自动标记为正常凭证。任一核对为'否'时标记为异常。",
        "借方金额和贷方金额为数值列。",
        "凭证编号用于跨区段行关联（同一凭证编号的行在3个sheet间对应同一笔）。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g4_13_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G4-13导入文件。返回(rows, errors)."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet
    multi_sheet = len(wb.sheetnames) >= 3 and any("记账凭证" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G4_13_SEGMENTS:
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
                    if key in _G4_13_NUMERIC_KEYS:
                        rows_dict[row_idx][key] = safe_float(raw)
                    elif key in _G4_13_BOOL_KEYS:
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
            if "凭证编号" in test_row or "区域" in test_row:
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
        if "凭证编号" not in actual_headers and "区域(借方/贷方)" not in actual_headers:
            errors.append({"row_number": header_row_idx, "field": "", "reason": "无法识别表头，缺少'凭证编号'或'区域(借方/贷方)'列"})
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
                if h in _G4_13_ALL_HEADERS:
                    key_idx = _G4_13_ALL_HEADERS.index(h)
                    key = _G4_13_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G4_13_NUMERIC_KEYS:
                        parsed[key] = safe_float(raw)
                    elif key in _G4_13_BOOL_KEYS:
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

@router.post("/api/workpapers/{wp_id}/g4-ecl/export-template")
async def g4_ecl_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)

    if sheet == "G4-9":
        wb = build_workbook_template(
            "G4-9",
            _G4_9_HEADERS,
            title="G4-9 债权投资三阶段划分",
            guidance=[
                "G4-9 三阶段划分 编制说明",
                "",
                "每行一个投资项目，填写三阶段判定相关信息。",
                "企业划分阶段和审计判断阶段填：Stage1 / Stage2 / Stage3。",
                "一致性(是/否) = 企业阶段与审计阶段是否相同（前端自动判断）。",
                "不一致时差异说明为必填项。",
                "是否逾期30天以上、是否发生信用减值事件 填：是/否。",
            ],
        )
        return workbook_to_response(wb, "G4-9_三阶段划分_模板.xlsx")
    elif sheet == "G4-10":
        wb = _build_g4_10_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G4-10_减值准备测算表_模板.xlsx")
    elif sheet == "G4-12":
        wb = _build_g4_12_multi_sheet_workbook([], [], template_only=True)
        return workbook_to_response(wb, "G4-12_转回核销检查表_模板.xlsx")
    else:  # G4-13
        wb = _build_g4_13_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G4-13_凭证检查表_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g4-ecl/export-data")
async def g4_ecl_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)

    if sheet == "G4-9":
        item_id = _ITEM_IDS["G4-9"]
        rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
        wb = build_workbook_template(
            "G4-9",
            _G4_9_HEADERS,
            title="G4-9 债权投资三阶段划分",
            guidance=["每行一个投资项目。Stage填Stage1/Stage2/Stage3。"],
        )
        ws = wb["G4-9"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G4_9_KEYS))
        return workbook_to_response(wb, "G4-9_三阶段划分_数据.xlsx")

    elif sheet == "G4-10":
        item_id = _ITEM_IDS["G4-10"]
        rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
        wb = _build_g4_10_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G4-10_减值准备测算表_数据.xlsx")

    elif sheet == "G4-12":
        reversals = await load_json_rows(db, wp_id, _G4_12_ITEM_IDS["reversals"], field="conclusion")
        writeoffs = await load_json_rows(db, wp_id, _G4_12_ITEM_IDS["writeOffs"], field="conclusion")
        wb = _build_g4_12_multi_sheet_workbook(reversals, writeoffs, template_only=False)
        return workbook_to_response(wb, "G4-12_转回核销检查表_数据.xlsx")

    else:  # G4-13
        item_id = _ITEM_IDS["G4-13"]
        rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
        wb = _build_g4_13_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G4-13_凭证检查表_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g4-ecl/import-data")
async def g4_ecl_import_data(
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

    if sheet == "G4-9":
        try:
            actual, raw = parse_upload_xlsx(content, _G4_9_HEADERS, header_row=2)
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
            parsed = parse_row_by_headers(r, actual, _G4_9_KEYS)
            # 校验Stage值
            for stage_field in ("companyStage", "auditStage"):
                val = parsed.get(stage_field, "")
                if val and val not in ("Stage1", "Stage2", "Stage3", ""):
                    errors.append({
                        "row_number": i + 2,
                        "field": stage_field,
                        "reason": f"阶段值'{val}'无效，应为Stage1/Stage2/Stage3",
                    })
            rows.append(parsed)
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        item_id = _ITEM_IDS["G4-9"]
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
        return {"ok": True, "imported_count": len(rows), "errors": errors}

    elif sheet == "G4-10":
        rows, errors = _parse_g4_10_import(content)
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        item_id = _ITEM_IDS["G4-10"]
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
        out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
        if len(rows) >= ROW_LIMIT:
            out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        return out

    elif sheet == "G4-12":
        reversals, writeoffs, errors = _parse_g4_12_import(content)
        if errors and not reversals and not writeoffs:
            return {"ok": False, "errors": errors, "imported_count": 0}
        if reversals:
            await upsert_json_rows(db, wp_id, _G4_12_ITEM_IDS["reversals"], reversals, field="conclusion")
        if writeoffs:
            await upsert_json_rows(db, wp_id, _G4_12_ITEM_IDS["writeOffs"], writeoffs, field="conclusion")
        total = len(reversals) + len(writeoffs)
        return {"ok": True, "imported_count": total, "errors": errors}

    else:  # G4-13
        rows, errors = _parse_g4_13_import(content)
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        item_id = _ITEM_IDS["G4-13"]
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
        out = {"ok": True, "imported_count": len(rows), "errors": errors}
        if len(rows) >= ROW_LIMIT:
            out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        return out
