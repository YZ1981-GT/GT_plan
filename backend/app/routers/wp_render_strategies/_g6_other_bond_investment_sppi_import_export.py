"""G6 其他债权投资(SPPI组) — 导入导出端点

支持 4 张动态行表格：
  G6-5 公允价值测试表(18列→2区段Tab) / G6-6 利息测算表(11列)
  G6-9 有价证券盘点表(5列) / G6-10 盘点倒轧表(18列→2区段Tab)

字段键与前端 composable 行接口严格对齐，保证 round-trip。

G6-5 按2区段分sheet导出（基础+审定 / 估值详情）。
G6-10 按2区段分sheet导出（倒轧计算 / 增减明细）。
G6-6 单sheet导出。
G6-9 单sheet导出。
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
    load_json_payload,
    load_json_rows,
    safe_float,
    safe_str,
    upsert_json_payload,
    upsert_json_rows,
    workbook_to_response,
)

router = APIRouter(tags=["g6-sppi-import-export"])


# ═══════════════════════════════════════════════════════════════════════════════
# G6-5 公允价值测试表（18列，2区段Tab）— 多sheet导出
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 基础+审定(10列)
_G6_5_SEG1_HEADERS = [
    "投资项目", "面值", "未审数量", "未审单价", "未审公允价值",
    "审定数量", "审定单价", "审定公允价值", "差异", "公允价值层次",
]
_G6_5_SEG1_KEYS = [
    "investProject", "faceValue", "unadjustedQty", "unadjustedPrice", "unadjustedFairValue",
    "auditedQty", "auditedPrice", "auditedFairValue", "variance", "fairValueLevel",
]

# 区段2: 估值详情(8列)
_G6_5_SEG2_HEADERS = [
    "投资项目", "估值方法", "与上期一致性", "来源机构",
    "输入值来源", "估值技术", "不可观察输入值", "估值文件索引",
]
_G6_5_SEG2_KEYS = [
    "investProject", "valuationMethod", "consistencyWithPrior", "sourceInstitution",
    "inputSource", "valuationTechnique", "unobservableInputs", "valuationDocIndex",
]

_G6_5_SEGMENTS = [
    ("基础+审定", _G6_5_SEG1_HEADERS, _G6_5_SEG1_KEYS),
    ("估值详情", _G6_5_SEG2_HEADERS, _G6_5_SEG2_KEYS),
]

# G6-5 数值字段
_G6_5_NUMERIC_KEYS = {
    "faceValue", "unadjustedQty", "unadjustedPrice", "unadjustedFairValue",
    "auditedQty", "auditedPrice", "auditedFairValue", "variance",
}


# ═══════════════════════════════════════════════════════════════════════════════
# G6-6 利息测算表（11列，单sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

_G6_6_HEADERS = [
    "投资项目", "面值", "票面利率", "实际利率", "截止日",
    "期初摊余成本", "实际利息收入", "现金流入", "期末摊余成本",
    "计息天数", "备注",
]
_G6_6_KEYS = [
    "investProject", "faceValue", "couponRate", "effectiveRate", "cutoffDate",
    "openingAmortized", "effectiveInterest", "cashInflow", "endingAmortized",
    "days", "remark",
]

# G6-6 数值字段
_G6_6_NUMERIC_KEYS = {
    "faceValue", "couponRate", "effectiveRate",
    "openingAmortized", "effectiveInterest", "cashInflow", "endingAmortized",
    "days",
}


# ═══════════════════════════════════════════════════════════════════════════════
# G6-9 有价证券盘点表（5列，单sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

_G6_9_HEADERS = [
    "证券名称", "证券代码", "面值", "数量(盘点)", "数量(账面)",
]
_G6_9_KEYS = [
    "securitiesName", "securitiesCode", "faceValue", "countQuantity", "bookQuantity",
]

# G6-9 数值字段
_G6_9_NUMERIC_KEYS = {"faceValue", "countQuantity", "bookQuantity"}


# ═══════════════════════════════════════════════════════════════════════════════
# G6-10 盘点倒轧表（18列，2区段Tab）— 多sheet导出
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 倒轧计算(8列)
_G6_10_SEG1_HEADERS = [
    "证券名称", "盘点日数量", "增减", "账面数量",
    "差异原因", "差异结论", "索引", "备注",
]
_G6_10_SEG1_KEYS = [
    "securitiesName", "countDateQuantity", "changeQuantity", "bookQuantity",
    "varianceReason", "varianceConclusion", "indexRef", "remark",
]

# 区段2: 增减明细(8列)
_G6_10_SEG2_HEADERS = [
    "证券名称", "日期", "交易类型", "数量",
    "金额", "凭证号", "经办人", "备注",
]
_G6_10_SEG2_KEYS = [
    "securitiesName", "date", "transactionType", "quantity",
    "amount", "voucherNo", "handler", "remark",
]

_G6_10_SEGMENTS = [
    ("倒轧计算", _G6_10_SEG1_HEADERS, _G6_10_SEG1_KEYS),
    ("增减明细", _G6_10_SEG2_HEADERS, _G6_10_SEG2_KEYS),
]

# G6-10 数值字段
_G6_10_NUMERIC_KEYS = {
    "countDateQuantity", "changeQuantity", "bookQuantity",
    "quantity", "amount",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G6-5": "G6-5-rows",
    "G6-6": "G6-6-rows",
    "G6-9": "G6-9-rows",
    "G6-10": "G6-10-rows",
}
_G6_6_PRIMARY_ITEM_ID = "G6-6-interest-data"

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


def _rate_to_decimal(value: Any) -> float:
    """Excel 可能填 5 或 0.05；统一存小数。"""
    num = safe_float(value)
    if abs(num) > 1:
        return round(num / 100, 8)
    return num


def _flatten_g6_6_groups(groups: list[dict]) -> list[dict]:
    """嵌套 InterestGroup[] → 扁平导出行。"""
    flat: list[dict] = []
    for group in groups or []:
        if not isinstance(group, dict):
            continue
        if "periods" not in group and ("openingAmortized" in group or "cutoffDate" in group or "periodEnd" in group):
            row = dict(group)
            row["couponRate"] = _rate_to_decimal(row.get("couponRate"))
            row["effectiveRate"] = _rate_to_decimal(row.get("effectiveRate"))
            if not row.get("cutoffDate") and row.get("periodEnd"):
                row["cutoffDate"] = row.get("periodEnd")
            flat.append(row)
            continue
        periods = group.get("periods") if isinstance(group.get("periods"), list) else [{}]
        if not periods:
            periods = [{}]
        for idx, period in enumerate(periods):
            period = period if isinstance(period, dict) else {}
            flat.append({
                "id": group.get("id") if idx == 0 else f"{group.get('id')}-{period.get('id') or idx}",
                "periodId": period.get("id") or "",
                "investProject": group.get("investProject") or "",
                "faceValue": group.get("faceValue"),
                "couponRate": _rate_to_decimal(group.get("couponRate")),
                "effectiveRate": _rate_to_decimal(group.get("effectiveRate")),
                "cutoffDate": period.get("periodEnd") or period.get("cutoffDate") or "",
                "periodEnd": period.get("periodEnd") or period.get("cutoffDate") or "",
                "openingAmortized": period.get("openingAmortized"),
                "effectiveInterest": period.get("effectiveInterest"),
                "cashInflow": period.get("cashInflow"),
                "endingAmortized": period.get("endingAmortized"),
                "days": period.get("days"),
                "remark": period.get("remark") or "",
            })
    return flat


def _nest_g6_6_flat_rows(rows: list[dict], *, existing: dict | None = None) -> dict:
    """扁平导出行 → 嵌套 InterestCalculationData。

    保留已有 conclusion / crossValidation 元数据，避免导入清空审计结论与勾稽基准。
    优先复用 periodId；缺省时按 项目+截止日 匹配旧期间 id。
    """
    prev = existing if isinstance(existing, dict) else {}
    # (normName, periodEnd) → period id
    prev_period_ids: dict[tuple[str, str], str] = {}
    prev_group_ids: dict[str, str] = {}
    for g in prev.get("groups") or []:
        if not isinstance(g, dict):
            continue
        name_key = "".join(safe_str(g.get("investProject")).split())
        if name_key and g.get("id"):
            prev_group_ids[name_key] = safe_str(g.get("id"))
        for p in g.get("periods") or []:
            if not isinstance(p, dict):
                continue
            pend = safe_str(p.get("periodEnd") or p.get("cutoffDate"))
            pid = safe_str(p.get("id"))
            if name_key and pend and pid:
                prev_period_ids[(name_key, pend)] = pid

    grouped: dict[str, dict] = {}
    order: list[str] = []
    for row in rows or []:
        name = safe_str(row.get("investProject") or row.get("projectName")) or "未命名投资项目"
        key = "".join(name.split())
        if key not in grouped:
            row_id = safe_str(row.get("id"))
            # 首行复合 id（组id-期间id）不作为组 id
            if row_id and "-" in row_id and key in prev_group_ids:
                row_id = ""
            grouped[key] = {
                "id": prev_group_ids.get(key) or row_id or str(uuid4()),
                "investProject": name,
                "faceValue": safe_float(row.get("faceValue")),
                "couponRate": _rate_to_decimal(row.get("couponRate")),
                "effectiveRate": _rate_to_decimal(row.get("effectiveRate")),
                "periods": [],
            }
            order.append(key)
        g = grouped[key]
        if not g.get("faceValue") and safe_float(row.get("faceValue")):
            g["faceValue"] = safe_float(row.get("faceValue"))
        if not g.get("couponRate") and safe_float(row.get("couponRate")):
            g["couponRate"] = _rate_to_decimal(row.get("couponRate"))
        if not g.get("effectiveRate") and safe_float(row.get("effectiveRate")):
            g["effectiveRate"] = _rate_to_decimal(row.get("effectiveRate"))
        period_end = safe_str(row.get("periodEnd") or row.get("cutoffDate"))
        period_id = (
            safe_str(row.get("periodId"))
            or prev_period_ids.get((key, period_end))
            or str(uuid4())
        )
        g["periods"].append({
            "id": period_id,
            "periodEnd": period_end,
            "openingAmortized": safe_float(row.get("openingAmortized")),
            "effectiveInterest": safe_float(row.get("effectiveInterest")),
            "cashInflow": safe_float(row.get("cashInflow")),
            "endingAmortized": safe_float(row.get("endingAmortized")),
            "days": safe_float(row.get("days")) or 180,
            "remark": safe_str(row.get("remark")),
        })

    prev_cv = prev.get("crossValidation") if isinstance(prev.get("crossValidation"), dict) else {}
    book_income = safe_float(prev_cv.get("bookInterestIncome"))
    adj_change = safe_float(
        prev_cv.get("interestAdjPeriodChange", prev_cv.get("auditedInterest")),
    )
    return {
        "groups": [grouped[k] for k in order],
        "conclusion": safe_str(prev.get("conclusion")) if prev.get("conclusion") is not None else "",
        "crossValidation": {
            "totalInterest": 0,
            "totalCashInflow": 0,
            "totalAmortization": 0,
            "bookInterestIncome": book_income,
            "interestAdjPeriodChange": adj_change,
            "incomeDiff": 0,
            "amortizationDiff": 0,
            # 兼容旧字段
            "auditedInterest": adj_change,
            "difference": 0,
        },
    }


async def _load_g6_6_nested_payload(db: AsyncSession, wp_id: str) -> dict | None:
    """读取已有嵌套 G6-6-interest-data（若无则尝试从扁平行重建，但不用于元数据）。"""
    for item_id in (_G6_6_PRIMARY_ITEM_ID, _ITEM_IDS["G6-6"]):
        payload = await load_json_payload(db, wp_id, item_id, field="conclusion")
        if payload is None:
            payload = await load_json_payload(db, wp_id, item_id, field="remark")
        if isinstance(payload, dict) and ("groups" in payload or "crossValidation" in payload or "conclusion" in payload):
            return payload
    return None


async def _load_g6_6_flat_rows(db: AsyncSession, wp_id: str) -> list[dict]:
    """优先读嵌套 G6-6-interest-data，兼容扁平 G6-6-rows。"""
    for item_id in (_G6_6_PRIMARY_ITEM_ID, _ITEM_IDS["G6-6"]):
        payload = await load_json_payload(db, wp_id, item_id, field="conclusion")
        if payload is None:
            payload = await load_json_payload(db, wp_id, item_id, field="remark")
        if payload is None:
            continue
        if isinstance(payload, dict) and "groups" in payload:
            return _flatten_g6_6_groups(payload.get("groups") or [])
        if isinstance(payload, list):
            if payload and isinstance(payload[0], dict) and "periods" in payload[0]:
                return _flatten_g6_6_groups(payload)
            return _flatten_g6_6_groups(payload)
    return []


async def _upsert_dual_fields(db: AsyncSession, wp_id: str, item_id: str, payload: Any) -> None:
    await upsert_json_payload(db, wp_id, item_id, payload, field="conclusion")
    await upsert_json_payload(db, wp_id, item_id, payload, field="remark")


# ═══════════════════════════════════════════════════════════════════════════════
# G6-5 多sheet导出（2区段→2 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g6_5_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G6-5 按2区段分sheet导出，每个区段一个worksheet."""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G6_5_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        ws.append([f"G6-5 公允价值测试表 — {seg_name}"])
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
    ws_guide.append(["G6-5 公允价值测试表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "18列拆为2区段Tab：基础+审定(10列) / 估值详情(8列)。",
        "差异 = 审定公允价值 - 未审公允价值（前端自动计算）。",
        "公允价值层次填：L1 / L2 / L3。",
        "Level3时估值详情相关字段必填。",
        "所有金额列以元为单位。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g6_5_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-5导入文件，支持多sheet或单sheet两种格式。返回(rows, errors)."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet格式（2区段分sheet）
    multi_sheet = len(wb.sheetnames) >= 2 and any("基础" in s or "审定" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G6_5_SEGMENTS:
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
                    if key in _G6_5_NUMERIC_KEYS:
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
            if "投资项目" in test_row or "面值" in test_row:
                header_row_idx = r
                break
        header_cells = list(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        if not header_cells:
            wb.close()
            return [], [{"row_number": 0, "field": "", "reason": "无有效表头行"}]
        actual_headers = [str(c.value).strip() if c.value else "" for c in header_cells[0]]
        all_headers = _G6_5_SEG1_HEADERS + _G6_5_SEG2_HEADERS[1:]  # 去重investProject
        all_keys = _G6_5_SEG1_KEYS + _G6_5_SEG2_KEYS[1:]
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append({"row_number": row_idx, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in all_headers:
                    key_idx = all_headers.index(h)
                    key = all_keys[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_5_NUMERIC_KEYS:
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
# G6-6 利息测算导出/导入（单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_g6_6_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-6导入文件（单sheet，11列）。"""
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
        if "投资项目" in test_row or "面值" in test_row or "票面利率" in test_row:
            header_row_idx = r
            break

    for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
        if all(v is None for v in row):
            continue
        if row_idx >= ROW_LIMIT:
            errors.append({"row_number": row_idx, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
            break
        values = list(row) + [None] * max(0, len(_G6_6_KEYS) - len(row))
        parsed: dict[str, Any] = {"id": str(uuid4())}
        for col_i, key in enumerate(_G6_6_KEYS):
            if col_i >= len(values):
                break
            raw = values[col_i]
            if key in _G6_6_NUMERIC_KEYS:
                if key in ("couponRate", "effectiveRate"):
                    parsed[key] = _rate_to_decimal(raw)
                else:
                    parsed[key] = safe_float(raw)
            else:
                parsed[key] = safe_str(raw)
        rows.append(parsed)

    wb.close()
    return rows, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G6-9 有价证券盘点导入（单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_g6_9_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-9导入文件（单sheet，5列）。"""
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
        if "证券名称" in test_row or "证券代码" in test_row:
            header_row_idx = r
            break

    for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
        if all(v is None for v in row):
            continue
        if row_idx >= ROW_LIMIT:
            errors.append({"row_number": row_idx, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
            break
        values = list(row) + [None] * max(0, len(_G6_9_KEYS) - len(row))
        parsed: dict[str, Any] = {"id": str(uuid4())}
        for col_i, key in enumerate(_G6_9_KEYS):
            if col_i >= len(values):
                break
            raw = values[col_i]
            if key in _G6_9_NUMERIC_KEYS:
                parsed[key] = safe_float(raw)
            else:
                parsed[key] = safe_str(raw)
        rows.append(parsed)

    wb.close()
    return rows, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G6-10 多sheet导出（2区段→2 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g6_10_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G6-10 按2区段分sheet导出，每个区段一个worksheet."""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G6_10_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        ws.append([f"G6-10 盘点倒轧表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16

        if not template_only:
            # G6-10 倒轧计算和增减明细可能存不同数据源
            source = rows if seg_name == "倒轧计算" else rows
            for row_data in source:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G6-10 盘点倒轧表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "18列拆为2区段Tab：倒轧计算(8列) / 增减明细(8列)。",
        "基准日数量 = 盘点日数量 ± 增减（前端自动计算）。",
        "差异 = 基准日数量 - 账面数量（前端自动计算）。",
        "交易类型填：买入 / 卖出 / 到期 / 转让。",
        "差异不为零时差异原因必填。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g6_10_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-10导入文件，支持多sheet或单sheet两种格式。返回(rows, errors)."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet格式（2区段分sheet）
    multi_sheet = len(wb.sheetnames) >= 2 and any("倒轧" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G6_10_SEGMENTS:
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
                    if key in _G6_10_NUMERIC_KEYS:
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
            if "证券名称" in test_row or "盘点日" in test_row:
                header_row_idx = r
                break
        header_cells = list(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        if not header_cells:
            wb.close()
            return [], [{"row_number": 0, "field": "", "reason": "无有效表头行"}]
        actual_headers = [str(c.value).strip() if c.value else "" for c in header_cells[0]]
        all_headers = _G6_10_SEG1_HEADERS + _G6_10_SEG2_HEADERS[1:]  # 去重securitiesName
        all_keys = _G6_10_SEG1_KEYS + _G6_10_SEG2_KEYS[1:]
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append({"row_number": row_idx, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in all_headers:
                    key_idx = all_headers.index(h)
                    key = all_keys[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_10_NUMERIC_KEYS:
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

@router.post("/api/workpapers/{wp_id}/g6-sppi/export-template")
async def g6_sppi_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)

    if sheet == "G6-5":
        wb = _build_g6_5_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G6-5_公允价值测试表_模板.xlsx")
    elif sheet == "G6-6":
        wb = build_workbook_template(
            "G6-6",
            _G6_6_HEADERS,
            title="G6-6 利息测算表",
            guidance=[
                "G6-6 利息测算表 编制说明",
                "",
                "按实际利率法确认利息收入。",
                "实际利息 = 期初摊余成本 × 实际利率 × 计息天数/365。",
                "现金流入 = 面值 × 票面利率 × 计息天数/365。",
                "期末摊余 = 期初摊余 + 实际利息 - 现金流入。",
                "票面利率和实际利率可填小数（0.05）或百分数（5）；系统统一按小数存储。",
                "导入后写入 G6-6-interest-data（嵌套）并双写 G6-6-rows（扁平）。",
                "所有金额列以元为单位。",
            ],
        )
        return workbook_to_response(wb, "G6-6_利息测算表_模板.xlsx")
    elif sheet == "G6-9":
        wb = build_workbook_template(
            "G6-9",
            _G6_9_HEADERS,
            title="G6-9 有价证券盘点表",
            guidance=[
                "G6-9 有价证券盘点表 编制说明",
                "",
                "每行一项证券盘点记录。",
                "差异 = 盘点数量 - 账面数量（前端自动计算，无需填写）。",
                "面值以元为单位。",
            ],
        )
        return workbook_to_response(wb, "G6-9_有价证券盘点表_模板.xlsx")
    else:  # G6-10
        wb = _build_g6_10_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G6-10_盘点倒轧表_模板.xlsx")


# ═══════════════════════════════════════════════════════════════════════════════
# 端点: export-data
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g6-sppi/export-data")
async def g6_sppi_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    item_id = _ITEM_IDS[sheet]
    rows = (
        await _load_g6_6_flat_rows(db, wp_id)
        if sheet == "G6-6"
        else await load_json_rows(db, wp_id, item_id, field="conclusion")
    )
    if sheet == "G6-5":
        wb = _build_g6_5_multi_sheet_workbook(rows)
        return workbook_to_response(wb, "G6-5_公允价值测试表_数据.xlsx")
    elif sheet == "G6-6":
        wb = build_workbook_template(
            "G6-6",
            _G6_6_HEADERS,
            title="G6-6 利息测算表",
            guidance=["按实际利率法确认利息收入。公式列前端自动重算。"],
        )
        ws = wb["G6-6"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G6_6_KEYS))
        return workbook_to_response(wb, "G6-6_利息测算表_数据.xlsx")
    elif sheet == "G6-9":
        wb = build_workbook_template(
            "G6-9",
            _G6_9_HEADERS,
            title="G6-9 有价证券盘点表",
            guidance=["每行一项证券盘点记录。差异前端自动计算。"],
        )
        ws = wb["G6-9"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G6_9_KEYS))
        return workbook_to_response(wb, "G6-9_有价证券盘点表_数据.xlsx")
    else:  # G6-10
        wb = _build_g6_10_multi_sheet_workbook(rows)
        return workbook_to_response(wb, "G6-10_盘点倒轧表_数据.xlsx")


# ═══════════════════════════════════════════════════════════════════════════════
# 端点: import-data
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g6-sppi/import-data")
async def g6_sppi_import_data(
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

    if sheet == "G6-5":
        rows, errors = _parse_g6_5_import(content)
    elif sheet == "G6-6":
        rows, errors = _parse_g6_6_import(content)
    elif sheet == "G6-9":
        rows, errors = _parse_g6_9_import(content)
    else:  # G6-10
        rows, errors = _parse_g6_10_import(content)

    if not rows and errors:
        raise HTTPException(422, detail={"message": "导入失败", "errors": errors})

    # 持久化
    item_id = _ITEM_IDS[sheet]
    if sheet == "G6-6":
        existing = await _load_g6_6_nested_payload(db, wp_id)
        nested = _nest_g6_6_flat_rows(rows, existing=existing)
        flat = _flatten_g6_6_groups(nested.get("groups") or [])
        # UI 读嵌套 G6-6-interest-data；IE/兼容读扁平 G6-6-rows — 双写
        await _upsert_dual_fields(db, wp_id, _G6_6_PRIMARY_ITEM_ID, nested)
        await _upsert_dual_fields(db, wp_id, item_id, flat)
    else:
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")

    return {
        "ok": True,
        "imported_count": len(rows),
        "errors": errors,
        "sheet": sheet,
    }
