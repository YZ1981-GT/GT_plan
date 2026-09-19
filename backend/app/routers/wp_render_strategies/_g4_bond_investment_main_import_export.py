"""G4 债权投资(main组) — 导入导出（列结构对齐 requirements + composable field keys）.

支持动态行表格：
  G4-1 审定表(keyed store) / G4-2 明细表(44列/5区段Tab) /
  G4-3 调整分录(10列) / G4-4 利息测算表(19列/2section)

字段键与前端 composable（useG4MainAdjudication/useG4MainDetail/useG4MainAdjustment/useG4MainInterestCalc）
严格对齐，保证 round-trip。

G4-2 导出特殊处理：44列按5区段分5 worksheet 导出（多区块分sheet导出）。
存储字段：conclusion（兼容旧 remark）。
"""

from __future__ import annotations

import io
import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    export_row_by_keys,
    is_numeric_field_key,
    load_json_payload,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_payload,
    upsert_json_rows,
    workbook_to_response,
)

router = APIRouter(tags=["g4-main-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# G4-2 明细表（44列，5区段Tab）— 多sheet导出
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 基础信息(6列)
_G4_2_SEG1_HEADERS = ["投资种类", "投资项目", "面值", "票面利率(%)", "实际利率(%)", "到期日"]
_G4_2_SEG1_KEYS = ["investCategory", "investProject", "faceValue", "couponRate", "effectiveRate", "maturityDate"]

# 区段2: 期初余额（对齐 Excel G–O，无备注列）
_G4_2_SEG2_HEADERS = [
    "成本", "利息调整（贷方余额填负数）", "应计利息", "小计",
    "债权投资期初减值准备", "债权投资期初摊余成本", "减：期初一年内到期部分",
    "期初调整数", "期初审定数",
]
_G4_2_SEG2_KEYS = [
    "openingCost", "openingInterestAdj", "openingAccruedInterest", "openingSubtotal",
    "openingImpairment", "openingAmortizedCost", "openingOneYearDeduct",
    "openingAdjustment", "openingAdjusted",
]

# 区段3: 本期变动(4列)
_G4_2_SEG3_HEADERS = ["成本", "利息调整", "应计利息", "小计"]
_G4_2_SEG3_KEYS = ["periodCostChange", "periodInterestAdjChange", "periodAccruedInterestChange", "periodChangeSubtotal"]

# 区段4: 期末余额+减值（对齐 Excel T–AB）
_G4_2_SEG4_HEADERS = [
    "成本", "利息调整（贷方余额填负数）", "应计利息", "调整数", "审定数",
    "减值准备（审定）期末数", "阶段划分", "信用组合方式", "信用组合名称",
]
_G4_2_SEG4_KEYS = [
    "closingCost", "closingInterestAdj", "closingAccruedInterest", "closingAdjustment", "closingAudited",
    "closingImpairment", "stageClassification", "creditCombineMethod", "creditCombineName",
]

# 区段5: 摊余成本+一年内到期（对齐 Excel AC–AH）
_G4_2_SEG5_HEADERS = [
    "债权投资期末摊余成本", "减：一年内到期账面余额", "减：一年内到期减值",
    "一年内到期小计", "债权投资期末账面价值", "发函情况",
]
_G4_2_SEG5_KEYS = [
    "amortizedCost", "oneYearBalance", "oneYearImpairment",
    "oneYearSubtotal", "bookValue", "correspondenceStatus",
]

# 全44列合并（用于导入解析）
_G4_2_ALL_HEADERS = _G4_2_SEG1_HEADERS + _G4_2_SEG2_HEADERS + _G4_2_SEG3_HEADERS + _G4_2_SEG4_HEADERS + _G4_2_SEG5_HEADERS
_G4_2_ALL_KEYS = _G4_2_SEG1_KEYS + _G4_2_SEG2_KEYS + _G4_2_SEG3_KEYS + _G4_2_SEG4_KEYS + _G4_2_SEG5_KEYS

# 5 区段名与对应列
_G4_2_SEGMENTS = [
    ("基础信息", _G4_2_SEG1_HEADERS, _G4_2_SEG1_KEYS),
    ("期初余额", _G4_2_SEG2_HEADERS, _G4_2_SEG2_KEYS),
    ("本期变动", _G4_2_SEG3_HEADERS, _G4_2_SEG3_KEYS),
    ("期末余额+减值", _G4_2_SEG4_HEADERS, _G4_2_SEG4_KEYS),
    ("摊余成本+审定", _G4_2_SEG5_HEADERS, _G4_2_SEG5_KEYS),
]

# ═══════════════════════════════════════════════════════════════════════════════
# G4-3 调整分录汇总（10列）
# ═══════════════════════════════════════════════════════════════════════════════

_G4_3_HEADERS = [
    "调整事项说明", "类别（报表调整/账项调整/其他）", "报表项目", "科目代码", "科目名称",
    "附注项目", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_G4_3_KEYS = [
    "description", "category", "reportItem", "accountCode", "accountName",
    "noteItem", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G4-4 利息测算表（19列，初始入账9列 + 利息计算10列 合并导出）
# ═══════════════════════════════════════════════════════════════════════════════

# G4-4 利息收入测算表（初始入账9列 + 利息计算9列，对齐 Excel，无减值阶段列）
_G4_4_HEADERS = [
    # (一) 初始入账价值(9列)
    "投资项目", "面值总额", "初始计量日", "到期日", "购买对价",
    "交易费用", "初始入账价值", "票面利率(%)", "实际利率(%)",
    # (二) 利息计算(9列 A–I)
    "截止日", "期初账面总额", "期初减值准备余额", "期初摊余成本余额",
    "实际利息收入", "现金流入", "已收回本金", "期末账面总额",
    "计息天数",
]
_G4_4_KEYS = [
    "projectName", "faceValueTotal", "initialDate", "maturityDate", "purchasePrice",
    "transactionCost", "initialCarryingAmount", "couponRate", "effectiveRate",
    "cutoffDate", "openingBalance", "openingImpairment", "openingAmortizedCost",
    "effectiveInterest", "cashInflow", "principalRepaid", "closingBalance",
    "days",
]


# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G4-1": "G4-1-rows",
    "G4-2": "G4-2-rows",
    "G4-3": "G4-3-rows",
    "G4-4": "G4-4-rows",
}
_G4_4_PRIMARY_ITEM_ID = "G4-4-interest-calc"

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


async def _load_canonical_rows(
    db: AsyncSession,
    wp_id: str,
    item_id: str,
    *,
    keyed_by: str | None = None,
) -> list[dict]:
    """优先 conclusion，兼容旧 remark。"""
    rows = await load_json_rows(db, wp_id, item_id, field="conclusion", keyed_by=keyed_by)
    if rows:
        return rows
    return await load_json_rows(db, wp_id, item_id, field="remark", keyed_by=keyed_by)


def _rate_to_percent(value: Any) -> float:
    num = safe_float(value)
    if abs(num) <= 1:
        return round(num * 100, 6)
    return num


def _rate_to_decimal(value: Any) -> float:
    num = safe_float(value)
    if abs(num) > 1:
        return round(num / 100, 8)
    return num


def _flatten_g4_4_groups(groups: list[dict]) -> list[dict]:
    """嵌套 InterestCalcGroup[] → 扁平导出行（利率输出为百分数）。"""
    flat: list[dict] = []
    for group in groups or []:
        if not isinstance(group, dict):
            continue
        if "initial" not in group and "periods" not in group:
            # 已是扁平行
            row = dict(group)
            if "couponRate" in row:
                row["couponRate"] = _rate_to_percent(row.get("couponRate"))
            if "effectiveRate" in row:
                row["effectiveRate"] = _rate_to_percent(row.get("effectiveRate"))
            flat.append(row)
            continue
        initial = group.get("initial") if isinstance(group.get("initial"), dict) else {}
        periods = group.get("periods") if isinstance(group.get("periods"), list) else [{}]
        if not periods:
            periods = [{}]
        for idx, period in enumerate(periods):
            period = period if isinstance(period, dict) else {}
            flat.append({
                "projectName": group.get("projectName") or "",
                "faceValueTotal": initial.get("faceValueTotal"),
                "initialDate": initial.get("initialDate"),
                "maturityDate": initial.get("maturityDate"),
                "purchasePrice": initial.get("purchasePrice"),
                "transactionCost": initial.get("transactionCost"),
                "initialCarryingAmount": initial.get("initialCarryingAmount"),
                "couponRate": _rate_to_percent(initial.get("couponRate")),
                "effectiveRate": _rate_to_percent(initial.get("effectiveRate")),
                "cutoffDate": period.get("cutoffDate"),
                "openingBalance": period.get("openingBalance"),
                "openingImpairment": period.get("openingImpairment"),
                "openingAmortizedCost": period.get("openingAmortizedCost"),
                "effectiveInterest": period.get("effectiveInterest"),
                "cashInflow": period.get("cashInflow"),
                "principalRepaid": period.get("principalRepaid"),
                "closingBalance": period.get("closingBalance"),
                "days": period.get("days"),
                "id": group.get("id") if idx == 0 else f"{group.get('id')}-{period.get('id') or idx}",
            })
    return flat


def _nest_g4_4_flat_rows(rows: list[dict]) -> list[dict]:
    """扁平导出行 → 嵌套 InterestCalcGroup[]（利率存为小数）。"""
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for row in rows or []:
        name = safe_str(row.get("projectName")) or "未命名投资项目"
        key = "".join(name.split())
        if key not in grouped:
            grouped[key] = {
                "id": safe_str(row.get("id")) or str(uuid4()),
                "projectName": name,
                "initial": {
                    "faceValueTotal": safe_float(row.get("faceValueTotal")),
                    "initialDate": safe_str(row.get("initialDate")),
                    "maturityDate": safe_str(row.get("maturityDate")),
                    "purchasePrice": safe_float(row.get("purchasePrice")),
                    "transactionCost": safe_float(row.get("transactionCost")),
                    "initialCarryingAmount": safe_float(row.get("initialCarryingAmount")),
                    "couponRate": _rate_to_decimal(row.get("couponRate")),
                    "effectiveRate": _rate_to_decimal(row.get("effectiveRate")),
                },
                "periods": [],
            }
            order.append(key)
        grouped[key]["periods"].append({
            "id": str(uuid4()),
            "cutoffDate": safe_str(row.get("cutoffDate")),
            "openingBalance": safe_float(row.get("openingBalance")),
            "openingImpairment": safe_float(row.get("openingImpairment")),
            "openingAmortizedCost": safe_float(row.get("openingAmortizedCost")),
            "effectiveInterest": safe_float(row.get("effectiveInterest")),
            "cashInflow": safe_float(row.get("cashInflow")),
            "principalRepaid": safe_float(row.get("principalRepaid")),
            "closingBalance": safe_float(row.get("closingBalance")),
            "days": safe_float(row.get("days")) or 365,
            "stage": "Stage1",
        })
    return [grouped[k] for k in order]


async def _load_g4_4_export_rows(db: AsyncSession, wp_id: str) -> list[dict]:
    """优先读 G4-4-interest-calc，兼容 G4-4-rows；嵌套则展平。"""
    for item_id in (_G4_4_PRIMARY_ITEM_ID, _ITEM_IDS["G4-4"]):
        payload = await load_json_payload(db, wp_id, item_id, field="conclusion")
        if payload is None:
            payload = await load_json_payload(db, wp_id, item_id, field="remark")
        if payload is None:
            continue
        if isinstance(payload, list):
            return _flatten_g4_4_groups(payload)
    return []


async def _upsert_dual_fields(
    db: AsyncSession,
    wp_id: str,
    item_id: str,
    payload: Any,
) -> None:
    """conclusion + remark 双写，兼容旧读者。"""
    await upsert_json_payload(db, wp_id, item_id, payload, field="conclusion")
    await upsert_json_payload(db, wp_id, item_id, payload, field="remark")


# ═══════════════════════════════════════════════════════════════════════════════
# G4-2 多sheet导出（5区段→5 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g4_2_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G4-2 按5区段分sheet导出，每个区段一个worksheet。"""
    wb = Workbook()
    # 删除默认sheet
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G4_2_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        # 标题行
        ws.append([f"G4-2 明细表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        # 表头行
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14

        if not template_only:
            for row_data in rows:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G4-2 明细表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "44列拆为5区段Tab：基础信息(6) / 期初余额(10) / 本期变动(4) / 期末余额+减值(10) / 摊余成本+审定(8)。",
        "公式列（期初小计/期初摊余成本/本期变动小计/期末成本~应计利息/期末小计/摊余成本/一年内到期小计/期末账面价值）导入后前端自动重算。",
        "期初小计 = 期初成本 + 期初利息调整 + 期初应计利息。",
        "期初摊余成本 = 期初小计 - 期初减值准备。",
        "期末成本 = 期初成本 + 本期成本变动。",
        "摊余成本 = 期末小计 - 减值准备期末数。",
        "阶段划分填：Stage1 / Stage2 / Stage3。",
        "利率列以百分数填写（如 5.25 表示 5.25%）。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g4_2_import(content: bytes) -> tuple[list[dict], list[str]]:
    """解析G4-2导入文件，支持多sheet或单sheet宽表两种格式。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_dict: dict[int, dict] = {}  # row_index -> merged fields

    # 策略1: 多sheet格式（5区段分sheet）
    multi_sheet = len(wb.sheetnames) >= 5 and any("基础信息" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G4_2_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append(f"缺少工作表: {seg_name}")
                continue
            # 找表头行（跳过标题行）
            header_row_idx = 2  # 默认第2行
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
                    rows_dict[row_idx] = {"id": str(uuid4())}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    raw = values[col_i] if col_i < len(values) else None
                    if is_numeric_field_key(key):
                        rows_dict[row_idx][key] = safe_float(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
    else:
        # 策略2: 单sheet宽表（44列合并）
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        # 自动检测表头行
        header_row_idx = 1
        for r in range(1, 5):
            test_row = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows(min_row=r, max_row=r))]
            if "投资种类" in test_row or "投资项目" in test_row:
                header_row_idx = r
                break
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        ]
        # 至少包含基础信息列
        if "投资项目" not in actual_headers:
            errors.append("无法识别表头，缺少'投资项目'列")
            wb.close()
            return [], errors
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in _G4_2_ALL_HEADERS:
                    key_idx = _G4_2_ALL_HEADERS.index(h)
                    key = _G4_2_ALL_KEYS[key_idx]
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

@router.post("/api/workpapers/{wp_id}/g4-main/export-template")
async def g4_main_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)

    if sheet == "G4-1":
        wb = build_workbook_template(
            "G4-1",
            ["rowKey", "openingUnadjusted", "openingAdjustment", "closingUnadjusted", "closingAdjustment", "reasonAnalysis"],
            title="G4-1 审定表",
            guidance=[
                "G4-1 审定表 编制说明",
                "",
                "按 rowKey 导入（如 original-portfolio / impairment-portfolio）。",
                "存储字段：conclusion（兼容旧 remark）。",
            ],
        )
        return workbook_to_response(wb, "G4-1_审定表_模板.xlsx")
    if sheet == "G4-2":
        wb = _build_g4_2_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G4-2_明细表_模板.xlsx")
    elif sheet == "G4-3":
        wb = build_workbook_template(
            "G4-3",
            _G4_3_HEADERS,
            title="G4-3 调整分录汇总",
            guidance=[
                "G4-3 调整分录 编制说明",
                "",
                "分录类型填 AJE 或 RJE；每张凭证借贷方金额必须相等。",
                "科目代码填完整编码（如 1501）。",
            ],
        )
        return workbook_to_response(wb, "G4-3_调整分录_模板.xlsx")
    else:  # G4-4
        wb = build_workbook_template(
            "G4-4",
            _G4_4_HEADERS,
            title="G4-4 利息测算表",
            guidance=[
                "G4-4 利息测算表 编制说明",
                "",
                "每个投资项目独立一组，初始入账+多行利息计算（每行一个计息期间）。",
                "初始入账价值 = 购买对价 + 交易费用。",
                "期初摊余成本余额 = 期初账面总额 - 期初减值准备余额。",
                "实际利息收入 = 期初摊余成本余额 × 实际利率(%) / 100 × 计息天数 / 365。",
                "现金流入 = 面值总额 × 票面利率(%) / 100 [× 计息天数/365]。",
                "期末账面总额 = 期初账面总额 + 实际利息收入 - 现金流入 - 已收回本金。",
                "利率以百分数填写（如 5.25 表示 5.25%）。",
                "减值阶段填：Stage1 / Stage2 / Stage3。",
            ],
        )
        return workbook_to_response(wb, "G4-4_利息测算表_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g4-main/export-data")
async def g4_main_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    item_id = _ITEM_IDS[sheet]
    keyed_by = "rowKey" if sheet == "G4-1" else None

    if sheet == "G4-1":
        rows = await _load_canonical_rows(db, wp_id, item_id, keyed_by=keyed_by)
        headers = [
            "rowKey",
            "openingUnadjusted",
            "openingAdjustment",
            "closingUnadjusted",
            "closingAdjustment",
            "reasonAnalysis",
        ]
        keys = headers
        wb = build_workbook_template(
            "G4-1",
            headers,
            title="G4-1 审定表",
            guidance=["按 rowKey 导入；存储字段 conclusion（兼容旧 remark）。"],
        )
        ws = wb["G4-1"]
        for d in rows:
            ws.append(export_row_by_keys(d, keys))
        return workbook_to_response(wb, "G4-1_审定表_数据.xlsx")
    if sheet == "G4-2":
        rows = await _load_canonical_rows(db, wp_id, item_id)
        wb = _build_g4_2_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G4-2_明细表_数据.xlsx")
    elif sheet == "G4-3":
        rows = await _load_canonical_rows(db, wp_id, item_id)
        wb = build_workbook_template(
            "G4-3",
            _G4_3_HEADERS,
            title="G4-3 调整分录汇总",
            guidance=["分录类型填 AJE 或 RJE；每张凭证借贷方金额必须相等。"],
        )
        ws = wb["G4-3"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G4_3_KEYS))
        return workbook_to_response(wb, "G4-3_调整分录_数据.xlsx")
    else:  # G4-4
        rows = await _load_g4_4_export_rows(db, wp_id)
        wb = build_workbook_template(
            "G4-4",
            _G4_4_HEADERS,
            title="G4-4 利息测算表",
            guidance=["每个投资项目一组，初始入账+多行利息计算。"],
        )
        ws = wb["G4-4"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G4_4_KEYS))
        return workbook_to_response(wb, "G4-4_利息测算表_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g4-main/import-data")
async def g4_main_import_data(
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
    keyed_by: str | None = None
    keep_keys: list[str] | None = None

    if sheet == "G4-1":
        headers = [
            "rowKey",
            "openingUnadjusted",
            "openingAdjustment",
            "closingUnadjusted",
            "closingAdjustment",
            "reasonAnalysis",
        ]
        keys = headers
        try:
            actual, raw = parse_upload_xlsx(content, headers, header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            row = parse_row_by_headers(r, actual, keys)
            if not str(row.get("rowKey") or "").strip():
                errors.append(f"第{i}行缺少 rowKey，已跳过")
                continue
            rows.append(row)
        keyed_by = "rowKey"
        keep_keys = [
            "openingUnadjusted",
            "openingAdjustment",
            "closingUnadjusted",
            "closingAdjustment",
            "reasonAnalysis",
        ]
    elif sheet == "G4-2":
        rows, errors = _parse_g4_2_import(content)
    elif sheet == "G4-3":
        try:
            actual, raw = parse_upload_xlsx(content, _G4_3_HEADERS, header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            rows.append(parse_row_by_headers(r, actual, _G4_3_KEYS))
    else:  # G4-4
        try:
            actual, raw = parse_upload_xlsx(content, _G4_4_HEADERS, header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            rows.append(parse_row_by_headers(r, actual, _G4_4_KEYS))

    if errors and not rows:
        return {"ok": False, "errors": errors, "imported_count": 0}

    if sheet == "G4-4":
        nested = _nest_g4_4_flat_rows(rows)
        flat = _flatten_g4_4_groups(nested)
        # UI 读嵌套 G4-4-interest-calc；IE/兼容路径读扁平 G4-4-rows — 双写
        await _upsert_dual_fields(db, wp_id, _G4_4_PRIMARY_ITEM_ID, nested)
        await _upsert_dual_fields(db, wp_id, item_id, flat)
    else:
        await upsert_json_rows(
            db,
            wp_id,
            item_id,
            rows,
            field="conclusion",
            keyed_by=keyed_by,
            keep_keys=keep_keys,
        )
        # 兼容旧读者：remark 同步一份
        await upsert_json_rows(
            db,
            wp_id,
            item_id,
            rows,
            field="remark",
            keyed_by=keyed_by,
            keep_keys=keep_keys,
        )
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
    if len(rows) >= ROW_LIMIT:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
