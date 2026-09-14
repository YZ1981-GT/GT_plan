"""G6 其他债权投资(SPPI组) — 导入导出端点

支持动态行表格：
  G6-5 公允价值测试表(18列→2区段Tab) / G6-6 利息测算表(扩展列，兼容旧11列)
  G6-8 SPPI合同现金流量测试(扁平行) / G6-9 有价证券盘点表(5列)
  G6-10 盘点倒轧表(18列→2区段Tab)

字段键与前端 composable 行接口严格对齐，保证 round-trip。

G6-5 按2区段分sheet导出（基础+审定 / 估值详情）。
G6-10 按2区段分sheet导出（倒轧计算 / 增减明细）。
G6-6 / G6-8 / G6-9 单sheet导出。
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
# G6-6 利息测算表（扩展列，单sheet导出；旧11列模板仍可导入）
# ═══════════════════════════════════════════════════════════════════════════════

_G6_6_HEADERS = [
    "投资项目", "跨表投资ID", "面值", "票面利率", "实际利率", "计息基准",
    "购入对价", "交易费用", "初始确认日", "初始入账价值",
    "起息日", "截止日",
    "期初摊余成本", "期初减值准备", "减值阶段",
    "实际利息收入", "现金流入", "已收回本金", "期末摊余成本",
    "计息天数", "天数手工覆盖", "期初手工覆盖",
    "备注", "索引",
]
_G6_6_KEYS = [
    "investProject", "crossSheetInvestmentId", "faceValue", "couponRate", "effectiveRate", "dayCountBasis",
    "purchasePrice", "transactionCost", "initialDate", "initialCarryingAmount",
    "periodStart", "cutoffDate",
    "openingAmortized", "openingImpairment", "stage",
    "effectiveInterest", "cashInflow", "principalRecovered", "endingAmortized",
    "days", "daysManualOverride", "openingManualOverride",
    "remark", "indexRef",
]

# 表头别名 → 标准键（兼容旧「截止日」等）
_G6_6_HEADER_ALIASES: dict[str, str] = {
    h: k for h, k in zip(_G6_6_HEADERS, _G6_6_KEYS)
}
_G6_6_HEADER_ALIASES["截止日"] = "cutoffDate"
_G6_6_HEADER_ALIASES["periodEnd"] = "cutoffDate"
_G6_6_HEADER_ALIASES["期间截止日"] = "cutoffDate"
_G6_6_HEADER_ALIASES["年天数基准"] = "dayCountBasis"
_G6_6_HEADER_ALIASES["计息年天数"] = "dayCountBasis"


def _g6_6_normalize_day_count_basis(raw: Any) -> str:
    s = safe_str(raw).strip().upper().replace(" ", "")
    if s in ("ACT/360", "ACT360", "A/360", "360"):
        return "ACT/360"
    if s in ("30/360", "30360", "30E/360", "30E360", "EUROPEAN30/360"):
        return "30/360"
    return "ACT/365"

# G6-6 数值字段
_G6_6_NUMERIC_KEYS = {
    "faceValue", "couponRate", "effectiveRate",
    "purchasePrice", "transactionCost", "initialCarryingAmount",
    "openingAmortized", "openingImpairment",
    "effectiveInterest", "cashInflow", "principalRecovered", "endingAmortized",
    "days",
}
_G6_6_BOOL_KEYS = {"daysManualOverride", "openingManualOverride"}


def _g6_6_parse_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    s = str(raw).strip().lower()
    return s in ("1", "true", "yes", "y", "是", "真", "t")


# ═══════════════════════════════════════════════════════════════════════════════
# G6-8 SPPI合同现金流量测试（扁平行：投资项目 × 检查项）
# ═══════════════════════════════════════════════════════════════════════════════

_G6_8_HEADERS = [
    "投资项目", "合同/索引", "SectionID", "Section标题", "检查项ID", "序号",
    "检查区域", "检查项目", "合同条款摘要", "是否满足SPPI", "判断依据",
    "风险等级", "索引", "备注",
]
_G6_8_KEYS = [
    "investProject", "contractRef", "sectionId", "sectionTitle", "itemId", "seq",
    "checkArea", "checkItem", "contractTermSummary", "isSPPISatisfied", "judgmentBasis",
    "riskLevel", "indexRef", "remark",
]
_G6_8_PRIMARY_ITEM_ID = "G6-8-sppi-test-data"


# ═══════════════════════════════════════════════════════════════════════════════
# G6-9 有价证券盘点表（扩展列，单sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

_G6_9_HEADERS = [
    "证券名称", "证券代码", "面值", "数量(盘点)", "数量(账面)",
    "差异原因", "差异结论", "权属主体", "受限类型", "受限说明", "证据索引", "索引",
]
_G6_9_KEYS = [
    "securitiesName", "securitiesCode", "faceValue", "countQuantity", "bookQuantity",
    "varianceReason", "varianceConclusion", "ownershipEntity", "restrictionType",
    "restrictionNote", "evidenceIndex", "indexRef",
]

# G6-9 数值字段
_G6_9_NUMERIC_KEYS = {"faceValue", "countQuantity", "bookQuantity"}


# ═══════════════════════════════════════════════════════════════════════════════
# G6-10 盘点倒轧表（18列，2区段Tab）— 多sheet导出
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 倒轧计算
_G6_10_SEG1_HEADERS = [
    "证券名称", "证券代码", "盘点日数量", "增减", "账面数量",
    "差异原因", "差异结论", "索引", "备注",
]
_G6_10_SEG1_KEYS = [
    "securitiesName", "securitiesCode", "countDateQuantity", "changeQuantity", "bookQuantity",
    "varianceReason", "varianceConclusion", "indexRef", "remark",
]

# 区段2: 增减明细
_G6_10_SEG2_HEADERS = [
    "证券名称", "证券代码", "日期", "交易类型", "数量",
    "金额", "凭证号", "经办人", "备注",
]
_G6_10_SEG2_KEYS = [
    "securitiesName", "securitiesCode", "date", "transactionType", "quantity",
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
    "G6-8": "G6-8-sppi-test-data",
    "G6-9": "G6-9-rows",
    "G6-10": "G6-10-rows",
}
_G6_6_PRIMARY_ITEM_ID = "G6-6-interest-data"
_G6_9_PRIMARY_ITEM_ID = "G6-9-securities-inventory-data"
_G6_10_PRIMARY_ITEM_ID = "G6-10-reconciliation-data"

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
                "crossSheetInvestmentId": group.get("crossSheetInvestmentId") or group.get("id") or "",
                "investProject": group.get("investProject") or "",
                "faceValue": group.get("faceValue"),
                "couponRate": _rate_to_decimal(group.get("couponRate")),
                "effectiveRate": _rate_to_decimal(group.get("effectiveRate")),
                "dayCountBasis": _g6_6_normalize_day_count_basis(group.get("dayCountBasis")),
                "purchasePrice": group.get("purchasePrice"),
                "transactionCost": group.get("transactionCost"),
                "initialDate": group.get("initialDate") or "",
                "initialCarryingAmount": group.get("initialCarryingAmount"),
                "cutoffDate": period.get("periodEnd") or period.get("cutoffDate") or "",
                "periodStart": period.get("periodStart") or "",
                "periodEnd": period.get("periodEnd") or period.get("cutoffDate") or "",
                "openingAmortized": period.get("openingAmortized"),
                "openingImpairment": period.get("openingImpairment"),
                "stage": period.get("stage") or "Stage1",
                "effectiveInterest": period.get("effectiveInterest"),
                "cashInflow": period.get("cashInflow"),
                "principalRecovered": period.get("principalRecovered"),
                "endingAmortized": period.get("endingAmortized"),
                "days": period.get("days"),
                "daysManualOverride": bool(period.get("daysManualOverride")),
                "openingManualOverride": bool(period.get("openingManualOverride")),
                "remark": period.get("remark") or "",
                "indexRef": period.get("indexRef") or "",
            })
    return flat


def _g6_6_blank(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


def _merge_g6_6_group_from_existing(group: dict, existing_group: dict | None) -> None:
    """旧 Excel 缺列时，从已有嵌套组补齐初始确认等字段。"""
    if not isinstance(existing_group, dict):
        return
    for key in (
        "crossSheetInvestmentId",
        "purchasePrice",
        "transactionCost",
        "initialDate",
        "initialCarryingAmount",
        "faceValue",
        "couponRate",
        "effectiveRate",
        "dayCountBasis",
    ):
        if _g6_6_blank(group.get(key)) or (
            key in ("purchasePrice", "transactionCost", "initialCarryingAmount", "faceValue", "couponRate", "effectiveRate")
            and safe_float(group.get(key)) == 0
            and safe_float(existing_group.get(key)) != 0
        ):
            if existing_group.get(key) is not None and not _g6_6_blank(existing_group.get(key)):
                group[key] = existing_group[key]
    if group.get("dayCountBasis"):
        group["dayCountBasis"] = _g6_6_normalize_day_count_basis(group.get("dayCountBasis"))
    elif existing_group.get("dayCountBasis"):
        group["dayCountBasis"] = _g6_6_normalize_day_count_basis(existing_group.get("dayCountBasis"))


def _merge_g6_6_period_from_existing(period: dict, existing_period: dict | None) -> None:
    """旧 Excel 缺列时，从已有期间补齐 stage/减值/起息日等。"""
    if not isinstance(existing_period, dict):
        return
    fill_if_blank = (
        "periodStart",
        "stage",
        "remark",
        "indexRef",
    )
    for key in fill_if_blank:
        if _g6_6_blank(period.get(key)) and not _g6_6_blank(existing_period.get(key)):
            period[key] = existing_period[key]
    for key in ("openingImpairment", "principalRecovered"):
        if safe_float(period.get(key)) == 0 and safe_float(existing_period.get(key)) != 0:
            period[key] = existing_period[key]
    if not period.get("daysManualOverride") and existing_period.get("daysManualOverride"):
        period["daysManualOverride"] = True
    if not period.get("openingManualOverride") and existing_period.get("openingManualOverride"):
        period["openingManualOverride"] = True
    # 旧模板无 stage 时默认 Stage1，若已有非 Stage1 则保留
    if period.get("stage") in (None, "", "Stage1") and existing_period.get("stage") in ("Stage2", "Stage3"):
        period["stage"] = existing_period["stage"]


def _nest_g6_6_flat_rows(rows: list[dict], *, existing: dict | None = None) -> dict:
    """扁平导出行 → 嵌套 InterestCalculationData。

    保留已有 conclusion / crossValidation 元数据，避免导入清空审计结论与勾稽基准。
    优先复用 periodId；缺省时按 项目+截止日 匹配旧期间 id。
    旧 11 列 Excel 缺字段时，按 periodId / (项目+截止日) 从 existing 合并。
    """
    prev = existing if isinstance(existing, dict) else {}
    # (normName, periodEnd) → period id / full period / group
    prev_period_ids: dict[tuple[str, str], str] = {}
    prev_periods_by_id: dict[str, dict] = {}
    prev_periods_by_key: dict[tuple[str, str], dict] = {}
    prev_group_ids: dict[str, str] = {}
    prev_groups_by_key: dict[str, dict] = {}
    for g in prev.get("groups") or []:
        if not isinstance(g, dict):
            continue
        name_key = "".join(safe_str(g.get("investProject")).split())
        if name_key and g.get("id"):
            prev_group_ids[name_key] = safe_str(g.get("id"))
        if name_key:
            prev_groups_by_key[name_key] = g
        for p in g.get("periods") or []:
            if not isinstance(p, dict):
                continue
            pend = safe_str(p.get("periodEnd") or p.get("cutoffDate"))
            pid = safe_str(p.get("id"))
            if pid:
                prev_periods_by_id[pid] = p
            if name_key and pend and pid:
                prev_period_ids[(name_key, pend)] = pid
            if name_key and pend:
                prev_periods_by_key[(name_key, pend)] = p

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
                "crossSheetInvestmentId": safe_str(row.get("crossSheetInvestmentId"))
                    or safe_str((prev_groups_by_key.get(key) or {}).get("crossSheetInvestmentId"))
                    or prev_group_ids.get(key)
                    or "",
                "investProject": name,
                "faceValue": safe_float(row.get("faceValue")),
                "couponRate": _rate_to_decimal(row.get("couponRate")),
                "effectiveRate": _rate_to_decimal(row.get("effectiveRate")),
                # 缺列时先留空，便于从 existing 合并；合并后再归一化默认 ACT/365
                "dayCountBasis": (
                    _g6_6_normalize_day_count_basis(row.get("dayCountBasis"))
                    if not _g6_6_blank(row.get("dayCountBasis"))
                    else ""
                ),
                "purchasePrice": safe_float(row.get("purchasePrice")),
                "transactionCost": safe_float(row.get("transactionCost")),
                "initialDate": safe_str(row.get("initialDate")),
                "initialCarryingAmount": safe_float(row.get("initialCarryingAmount")),
                "periods": [],
            }
            _merge_g6_6_group_from_existing(grouped[key], prev_groups_by_key.get(key))
            grouped[key]["dayCountBasis"] = _g6_6_normalize_day_count_basis(
                grouped[key].get("dayCountBasis"),
            )
            order.append(key)
        g = grouped[key]
        if not g.get("crossSheetInvestmentId") and row.get("crossSheetInvestmentId"):
            g["crossSheetInvestmentId"] = safe_str(row.get("crossSheetInvestmentId"))
        if not g.get("faceValue") and safe_float(row.get("faceValue")):
            g["faceValue"] = safe_float(row.get("faceValue"))
        if not g.get("couponRate") and safe_float(row.get("couponRate")):
            g["couponRate"] = _rate_to_decimal(row.get("couponRate"))
        if not g.get("effectiveRate") and safe_float(row.get("effectiveRate")):
            g["effectiveRate"] = _rate_to_decimal(row.get("effectiveRate"))
        if not _g6_6_blank(row.get("dayCountBasis")):
            g["dayCountBasis"] = _g6_6_normalize_day_count_basis(row.get("dayCountBasis"))
        if not g.get("purchasePrice") and safe_float(row.get("purchasePrice")):
            g["purchasePrice"] = safe_float(row.get("purchasePrice"))
        if not g.get("transactionCost") and safe_float(row.get("transactionCost")):
            g["transactionCost"] = safe_float(row.get("transactionCost"))
        if not g.get("initialDate") and row.get("initialDate"):
            g["initialDate"] = safe_str(row.get("initialDate"))
        if not g.get("initialCarryingAmount") and safe_float(row.get("initialCarryingAmount")):
            g["initialCarryingAmount"] = safe_float(row.get("initialCarryingAmount"))
        period_end = safe_str(row.get("periodEnd") or row.get("cutoffDate"))
        period_id = (
            safe_str(row.get("periodId"))
            or prev_period_ids.get((key, period_end))
            or str(uuid4())
        )
        stage = safe_str(row.get("stage")) or "Stage1"
        if stage not in ("Stage1", "Stage2", "Stage3"):
            stage = "Stage1"
        period = {
            "id": period_id,
            "periodStart": safe_str(row.get("periodStart")),
            "periodEnd": period_end,
            "openingAmortized": safe_float(row.get("openingAmortized")),
            "openingImpairment": safe_float(row.get("openingImpairment")),
            "stage": stage,
            "effectiveInterest": safe_float(row.get("effectiveInterest")),
            "cashInflow": safe_float(row.get("cashInflow")),
            "principalRecovered": safe_float(row.get("principalRecovered")),
            "endingAmortized": safe_float(row.get("endingAmortized")),
            "days": safe_float(row.get("days")) or 180,
            "daysManualOverride": _g6_6_parse_bool(row.get("daysManualOverride")),
            "openingManualOverride": _g6_6_parse_bool(row.get("openingManualOverride")),
            "remark": safe_str(row.get("remark")),
            "indexRef": safe_str(row.get("indexRef")),
        }
        existing_period = (
            prev_periods_by_id.get(period_id)
            or prev_periods_by_key.get((key, period_end))
        )
        _merge_g6_6_period_from_existing(period, existing_period)
        g["periods"].append(period)

    prev_cv = prev.get("crossValidation") if isinstance(prev.get("crossValidation"), dict) else {}
    book_income = safe_float(prev_cv.get("bookInterestIncome"))
    adj_change = safe_float(
        prev_cv.get("interestAdjPeriodChange", prev_cv.get("auditedInterest")),
    )
    book_set = prev_cv.get("bookInterestIncomeSet")
    return {
        "groups": [grouped[k] for k in order],
        "conclusion": safe_str(prev.get("conclusion")) if prev.get("conclusion") is not None else "",
        "crossValidation": {
            "totalInterest": 0,
            "totalCashInflow": 0,
            "totalAmortization": 0,
            "bookInterestIncome": book_income,
            "bookInterestIncomeSet": bool(book_set) if book_set is not None else abs(book_income) >= 0.01,
            "interestAdjPeriodChange": adj_change,
            "incomeDiff": 0,
            "amortizationDiff": 0,
            "varianceReason": safe_str(prev_cv.get("varianceReason")),
            "performanceMateriality": safe_float(prev_cv.get("performanceMateriality")),
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


def _norm_sec_key(name: str = "", code: str = "") -> str:
    code_key = "".join(safe_str(code).split()).upper()
    if code_key:
        return f"code:{code_key}"
    return f"name:{''.join(safe_str(name).split())}"


def _nest_g6_9_flat_rows(rows: list[dict], *, existing: dict | None = None) -> dict:
    """扁平导出行 → 嵌套 SecuritiesInventoryData，保留已有结论与差异追查字段。"""
    prev = existing if isinstance(existing, dict) else {}
    prev_map: dict[str, dict] = {}
    for item in prev.get("items") or []:
        if not isinstance(item, dict):
            continue
        key = _norm_sec_key(item.get("securitiesName") or "", item.get("securitiesCode") or "")
        if key and key not in ("code:", "name:"):
            prev_map[key] = item

    nested_items: list[dict] = []
    for idx, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        key = _norm_sec_key(row.get("securitiesName") or "", row.get("securitiesCode") or "")
        old = prev_map.get(key) or {}
        nested_items.append({
            "id": safe_str(row.get("id")) or safe_str(old.get("id")) or str(uuid4()),
            "seq": idx + 1,
            "securitiesName": safe_str(row.get("securitiesName")),
            "securitiesCode": safe_str(row.get("securitiesCode")),
            "faceValue": safe_float(row.get("faceValue")),
            "countQuantity": safe_float(row.get("countQuantity")),
            "bookQuantity": safe_float(row.get("bookQuantity")),
            "varianceReason": safe_str(row.get("varianceReason") or old.get("varianceReason")),
            "varianceConclusion": safe_str(row.get("varianceConclusion") or old.get("varianceConclusion")),
            "indexRef": safe_str(row.get("indexRef") or old.get("indexRef")),
            "ownershipEntity": safe_str(row.get("ownershipEntity") or old.get("ownershipEntity")),
            "restrictionType": safe_str(row.get("restrictionType") or old.get("restrictionType")),
            "restrictionNote": safe_str(row.get("restrictionNote") or old.get("restrictionNote")),
            "evidenceIndex": safe_str(row.get("evidenceIndex") or old.get("evidenceIndex")),
        })
    prev_meta = prev.get("meta") if isinstance(prev.get("meta"), dict) else {}
    return {
        "items": nested_items,
        "auditConclusion": safe_str(prev.get("auditConclusion")) if prev.get("auditConclusion") is not None else "",
        "meta": prev_meta,
    }


def _flatten_g6_9_items(items: list[dict]) -> list[dict]:
    flat: list[dict] = []
    for idx, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        flat.append({
            "id": safe_str(item.get("id")) or str(uuid4()),
            "seq": idx + 1,
            "securitiesName": safe_str(item.get("securitiesName")),
            "securitiesCode": safe_str(item.get("securitiesCode")),
            "faceValue": safe_float(item.get("faceValue")),
            "countQuantity": safe_float(item.get("countQuantity")),
            "bookQuantity": safe_float(item.get("bookQuantity")),
            "varianceReason": safe_str(item.get("varianceReason")),
            "varianceConclusion": safe_str(item.get("varianceConclusion")),
            "indexRef": safe_str(item.get("indexRef")),
            "ownershipEntity": safe_str(item.get("ownershipEntity")),
            "restrictionType": safe_str(item.get("restrictionType")),
            "restrictionNote": safe_str(item.get("restrictionNote")),
            "evidenceIndex": safe_str(item.get("evidenceIndex")),
        })
    return flat


async def _load_g6_9_nested_payload(db: AsyncSession, wp_id: str) -> dict | None:
    for item_id in (_G6_9_PRIMARY_ITEM_ID, _ITEM_IDS["G6-9"]):
        payload = await load_json_payload(db, wp_id, item_id, field="conclusion")
        if payload is None:
            payload = await load_json_payload(db, wp_id, item_id, field="remark")
        if isinstance(payload, dict) and "items" in payload:
            return payload
        if isinstance(payload, list):
            return _nest_g6_9_flat_rows(payload)
    return None


async def _load_g6_9_flat_rows(db: AsyncSession, wp_id: str) -> list[dict]:
    for item_id in (_G6_9_PRIMARY_ITEM_ID, _ITEM_IDS["G6-9"]):
        payload = await load_json_payload(db, wp_id, item_id, field="conclusion")
        if payload is None:
            payload = await load_json_payload(db, wp_id, item_id, field="remark")
        if payload is None:
            continue
        if isinstance(payload, dict) and "items" in payload:
            return _flatten_g6_9_items(payload.get("items") or [])
        if isinstance(payload, list):
            return _flatten_g6_9_items(payload)
    return []


def _normalize_g6_10_tx_type(raw: Any) -> str:
    text = safe_str(raw).strip()
    mapping = {
        "买入": "buy", "buy": "buy",
        "卖出": "sell", "sell": "sell",
        "到期": "mature", "mature": "mature",
        "转让": "transfer", "transfer": "transfer",
        "转入": "transfer_in", "transfer_in": "transfer_in",
        "转出": "transfer_out", "transfer_out": "transfer_out",
        "转让(转出)": "transfer",
    }
    return mapping.get(text, text)


_G6_10_VALID_TX = {
    "buy", "sell", "mature", "transfer", "transfer_in", "transfer_out", "",
}


def _validate_g6_10_nested(nested: dict) -> list[dict]:
    """导入落库前校验：空名称、非法交易类型、空表覆盖、明细孤儿行。"""
    errors: list[dict] = []
    items = nested.get("items") if isinstance(nested, dict) else []
    details = nested.get("changeDetails") if isinstance(nested, dict) else []
    if not items and not details:
        errors.append({"row_number": 0, "field": "", "reason": "导入结果为空，已拒绝覆盖现有数据"})
        return errors

    names: set[str] = set()
    for idx, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        name = safe_str(item.get("securitiesName")).strip()
        if not name:
            errors.append({"row_number": idx + 1, "field": "securitiesName", "reason": "倒轧行证券名称不能为空"})
        elif name in names:
            errors.append({"row_number": idx + 1, "field": "securitiesName", "reason": f"倒轧行证券名称重复: {name}"})
        else:
            names.add(name)

    item_name_keys = {"".join(n.split()) for n in names}
    for idx, detail in enumerate(details or []):
        if not isinstance(detail, dict):
            continue
        name = safe_str(detail.get("securitiesName")).strip()
        tx = _normalize_g6_10_tx_type(detail.get("transactionType"))
        if not name:
            errors.append({"row_number": idx + 1, "field": "securitiesName", "reason": "增减明细证券名称不能为空"})
        if tx not in _G6_10_VALID_TX:
            errors.append({
                "row_number": idx + 1,
                "field": "transactionType",
                "reason": f"非法交易类型: {detail.get('transactionType')}（允许：买入/卖出/到期/转入/转出/转让）",
            })
        if name and item_name_keys and "".join(name.split()) not in item_name_keys:
            errors.append({
                "row_number": idx + 1,
                "field": "securitiesName",
                "reason": f"增减明细证券未出现在倒轧计算表: {name}",
            })
    return errors


def _g6_10_seg_rows(payload: dict | None, seg_name: str) -> list[dict]:
    """按区段取出导出行。"""
    data = payload if isinstance(payload, dict) else {}
    if seg_name == "倒轧计算":
        return [r for r in (data.get("items") or []) if isinstance(r, dict)]
    return [r for r in (data.get("changeDetails") or []) if isinstance(r, dict)]


def _nest_g6_10_flat_rows(rows: list[dict], *, existing: dict | None = None) -> dict:
    """扁平导出行 → ReconciliationData。"""
    prev = existing if isinstance(existing, dict) else {}
    items: list[dict] = []
    change_details: list[dict] = []
    seen_names: set[str] = set()

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = safe_str(row.get("securitiesName")).strip()
        has_roll = (
            row.get("countDateQuantity") is not None
            or row.get("changeQuantity") is not None
            or row.get("bookQuantity") is not None
            or bool(safe_str(row.get("varianceReason")))
            or bool(safe_str(row.get("varianceConclusion")))
            or bool(safe_str(row.get("indexRef")))
        )
        has_detail = (
            bool(safe_str(row.get("date")))
            or bool(safe_str(row.get("transactionType")))
            or bool(safe_str(row.get("voucherNo")))
            or bool(safe_str(row.get("handler")))
            or (row.get("quantity") is not None and safe_float(row.get("quantity")) != 0)
        )

        if name and has_roll and name not in seen_names:
            seen_names.add(name)
            items.append({
                "id": safe_str(row.get("id")) or str(uuid4()),
                "seq": len(items) + 1,
                "securitiesName": name,
                "securitiesCode": safe_str(row.get("securitiesCode")),
                "sourceItemId": safe_str(row.get("sourceItemId") or row.get("linkedItemId")),
                "countDateQuantity": safe_float(row.get("countDateQuantity")),
                "changeQuantity": safe_float(row.get("changeQuantity")),
                "bookQuantity": safe_float(row.get("bookQuantity")),
                "varianceReason": safe_str(row.get("varianceReason")),
                "varianceConclusion": safe_str(row.get("varianceConclusion")),
                "indexRef": safe_str(row.get("indexRef")),
                "remark": safe_str(row.get("remark")),
            })

        if name and has_detail:
            if has_roll and not safe_str(row.get("transactionType")) and not safe_str(row.get("date")):
                continue
            change_details.append({
                "id": str(uuid4()),
                "securitiesName": name,
                "securitiesCode": safe_str(row.get("securitiesCode")),
                "linkedItemId": safe_str(row.get("linkedItemId") or row.get("sourceItemId")),
                "date": safe_str(row.get("date")),
                "transactionType": _normalize_g6_10_tx_type(row.get("transactionType")),
                "quantity": safe_float(row.get("quantity")),
                "amount": safe_float(row.get("amount")),
                "voucherNo": safe_str(row.get("voucherNo")),
                "handler": safe_str(row.get("handler")),
                "remark": "" if has_roll else safe_str(row.get("remark")),
            })

    if not change_details and isinstance(prev.get("changeDetails"), list):
        change_details = list(prev.get("changeDetails") or [])

    return {
        "activeTab": prev.get("activeTab") or "rollForward",
        "selectedRowIndex": int(prev.get("selectedRowIndex") or 0),
        "items": items,
        "changeDetails": change_details,
        "header": prev.get("header") if isinstance(prev.get("header"), dict) else {"countDate": "", "balanceSheetDate": ""},
        "formulaVersion": int(prev.get("formulaVersion") or 2),
        "changeConvention": safe_str(prev.get("changeConvention")) or "period_net_increase",
    }


def _flatten_g6_10_items(payload: dict) -> list[dict]:
    """倒轧行 + 增减明细扁平列表（兼容旧导出/双写）。"""
    items = payload.get("items") if isinstance(payload, dict) else []
    change_details = payload.get("changeDetails") if isinstance(payload, dict) else []
    flat: list[dict] = []
    for idx, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        flat.append({
            "id": safe_str(item.get("id")) or str(uuid4()),
            "seq": idx + 1,
            "securitiesName": safe_str(item.get("securitiesName")),
            "securitiesCode": safe_str(item.get("securitiesCode")),
            "sourceItemId": safe_str(item.get("sourceItemId")),
            "countDateQuantity": safe_float(item.get("countDateQuantity")),
            "changeQuantity": safe_float(item.get("changeQuantity")),
            "bookQuantity": safe_float(item.get("bookQuantity")),
            "varianceReason": safe_str(item.get("varianceReason")),
            "varianceConclusion": safe_str(item.get("varianceConclusion")),
            "indexRef": safe_str(item.get("indexRef")),
            "remark": safe_str(item.get("remark")),
        })
    for detail in change_details or []:
        if not isinstance(detail, dict):
            continue
        flat.append({
            "id": safe_str(detail.get("id")) or str(uuid4()),
            "securitiesName": safe_str(detail.get("securitiesName")),
            "securitiesCode": safe_str(detail.get("securitiesCode")),
            "linkedItemId": safe_str(detail.get("linkedItemId")),
            "date": safe_str(detail.get("date")),
            "transactionType": safe_str(detail.get("transactionType")),
            "quantity": safe_float(detail.get("quantity")),
            "amount": safe_float(detail.get("amount")),
            "voucherNo": safe_str(detail.get("voucherNo")),
            "handler": safe_str(detail.get("handler")),
            "remark": safe_str(detail.get("remark")),
        })
    return flat


async def _load_g6_10_nested_payload(db: AsyncSession, wp_id: str) -> dict | None:
    for item_id in (_G6_10_PRIMARY_ITEM_ID, _ITEM_IDS["G6-10"]):
        payload = await load_json_payload(db, wp_id, item_id, field="conclusion")
        if payload is None:
            payload = await load_json_payload(db, wp_id, item_id, field="remark")
        if isinstance(payload, dict) and ("items" in payload or "changeDetails" in payload):
            return payload
        if isinstance(payload, list):
            return _nest_g6_10_flat_rows(payload)
    return None


async def _load_g6_10_flat_rows(db: AsyncSession, wp_id: str) -> list[dict]:
    nested = await _load_g6_10_nested_payload(db, wp_id)
    if nested:
        return _flatten_g6_10_items(nested)
    return []


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
    """解析G6-6导入文件（单sheet；按表头映射，兼容旧11列）。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows: list[dict] = []

    ws = wb.active
    if ws is None:
        wb.close()
        return [], [{"row_number": 0, "field": "", "reason": "xlsx文件中无活动工作表"}]

    # 找表头行
    header_row_idx = 1
    actual_headers: list[str] = []
    for r in range(1, min(5, (ws.max_row or 1) + 1)):
        row_cells = list(ws.iter_rows(min_row=r, max_row=r))
        if not row_cells:
            continue
        test_row = [str(c.value).strip() if c.value else "" for c in row_cells[0]]
        if "投资项目" in test_row or "面值" in test_row or "票面利率" in test_row:
            header_row_idx = r
            actual_headers = test_row
            break
    if not actual_headers:
        header_cells = list(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        if header_cells:
            actual_headers = [str(c.value).strip() if c.value else "" for c in header_cells[0]]

    # 按表头名映射列；若无法识别则回退为固定列序（兼容无表头旧文件）
    col_key_map: list[str | None] = [
        _G6_6_HEADER_ALIASES.get(h) for h in actual_headers
    ]
    use_positional = not any(col_key_map)

    for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
        if all(v is None for v in row):
            continue
        if row_idx >= ROW_LIMIT:
            errors.append({"row_number": row_idx, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
            break
        values = list(row)
        parsed: dict[str, Any] = {"id": str(uuid4())}
        if use_positional:
            values = values + [None] * max(0, len(_G6_6_KEYS) - len(values))
            for col_i, key in enumerate(_G6_6_KEYS):
                if col_i >= len(values):
                    break
                raw = values[col_i]
                if key in _G6_6_NUMERIC_KEYS:
                    if key in ("couponRate", "effectiveRate"):
                        parsed[key] = _rate_to_decimal(raw)
                    else:
                        parsed[key] = safe_float(raw)
                elif key in _G6_6_BOOL_KEYS:
                    parsed[key] = _g6_6_parse_bool(raw)
                else:
                    parsed[key] = safe_str(raw)
        else:
            for col_i, key in enumerate(col_key_map):
                if not key or col_i >= len(values):
                    continue
                raw = values[col_i]
                if key in _G6_6_NUMERIC_KEYS:
                    if key in ("couponRate", "effectiveRate"):
                        parsed[key] = _rate_to_decimal(raw)
                    else:
                        parsed[key] = safe_float(raw)
                elif key in _G6_6_BOOL_KEYS:
                    parsed[key] = _g6_6_parse_bool(raw)
                else:
                    parsed[key] = safe_str(raw)
            # 统一 periodEnd
            if parsed.get("cutoffDate") and not parsed.get("periodEnd"):
                parsed["periodEnd"] = parsed["cutoffDate"]
        rows.append(parsed)

    wb.close()
    return rows, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G6-8 SPPI 扁平行 ↔ 嵌套 instruments
# ═══════════════════════════════════════════════════════════════════════════════

def _flatten_g6_8_payload(payload: Any) -> list[dict]:
    """嵌套 SppiTestData → 扁平行。"""
    if not isinstance(payload, dict):
        return []
    instruments = payload.get("instruments")
    if not isinstance(instruments, list) or not instruments:
        # 兼容旧单问卷
        sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
        instruments = [{
            "id": "legacy",
            "name": "综合问卷（历史）",
            "contractRef": "",
            "sections": sections,
        }]
    flat: list[dict] = []
    for inst in instruments:
        if not isinstance(inst, dict):
            continue
        name = safe_str(inst.get("name") or inst.get("investProject") or "未命名投资项目")
        contract_ref = safe_str(inst.get("contractRef") or "")
        inst_id = safe_str(inst.get("id") or str(uuid4()))
        for section in inst.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_id = safe_str(section.get("id"))
            section_title = safe_str(section.get("title"))
            for item in section.get("items") or []:
                if not isinstance(item, dict):
                    continue
                flat.append({
                    "instrumentId": inst_id,
                    "investProject": name,
                    "contractRef": contract_ref,
                    "sectionId": section_id,
                    "sectionTitle": section_title,
                    "itemId": safe_str(item.get("id")),
                    "seq": item.get("seq") or 0,
                    "checkArea": safe_str(item.get("checkArea")),
                    "checkItem": safe_str(item.get("checkItem")),
                    "contractTermSummary": safe_str(item.get("contractTermSummary")),
                    "isSPPISatisfied": safe_str(item.get("isSPPISatisfied")),
                    "judgmentBasis": safe_str(item.get("judgmentBasis")),
                    "riskLevel": safe_str(item.get("riskLevel")),
                    "indexRef": safe_str(item.get("indexRef")),
                    "remark": safe_str(item.get("remark")),
                })
    return flat


def _nest_g6_8_flat_rows(rows: list[dict], *, existing: dict | None = None) -> dict:
    """扁平行 → 嵌套 SppiTestData（按投资项目分组；保留审计无关元数据最少）。"""
    prev = existing if isinstance(existing, dict) else {}
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for row in rows or []:
        name = safe_str(row.get("investProject") or row.get("instrumentName")) or "未命名投资项目"
        key = "".join(name.split())
        if key not in grouped:
            grouped[key] = {
                "id": safe_str(row.get("instrumentId")) or str(uuid4()),
                "name": name,
                "contractRef": safe_str(row.get("contractRef")),
                "remark": "",
                "sections": {},  # sectionId -> section dict
                "overallConclusion": None,
                "hasFailedSection": False,
            }
            order.append(key)
        inst = grouped[key]
        if row.get("contractRef"):
            inst["contractRef"] = safe_str(row.get("contractRef"))
        sid = safe_str(row.get("sectionId")) or "unknown"
        if sid not in inst["sections"]:
            inst["sections"][sid] = {
                "id": sid,
                "title": safe_str(row.get("sectionTitle")) or sid,
                "items": [],
                "sectionConclusion": None,
            }
        sat = safe_str(row.get("isSPPISatisfied")).lower()
        if sat in ("是", "yes"):
            sat_val = "yes"
        elif sat in ("否", "no"):
            sat_val = "no"
        elif sat in ("不适用", "na", "n/a"):
            sat_val = "na"
        else:
            sat_val = sat if sat in ("yes", "no", "na") else ""
        risk = safe_str(row.get("riskLevel")).lower()
        if risk in ("高", "high"):
            risk_val = "high"
        elif risk in ("中", "medium"):
            risk_val = "medium"
        elif risk in ("低", "low"):
            risk_val = "low"
        else:
            risk_val = risk if risk in ("high", "medium", "low") else ""
        inst["sections"][sid]["items"].append({
            "id": safe_str(row.get("itemId")) or str(uuid4()),
            "seq": int(safe_float(row.get("seq")) or len(inst["sections"][sid]["items"]) + 1),
            "checkArea": safe_str(row.get("checkArea")),
            "checkItem": safe_str(row.get("checkItem")),
            "casRequirement": "",
            "contractTermSummary": safe_str(row.get("contractTermSummary")),
            "isSPPISatisfied": sat_val or None,
            "judgmentBasis": safe_str(row.get("judgmentBasis")),
            "riskLevel": risk_val or None,
            "indexRef": safe_str(row.get("indexRef")),
            "remark": safe_str(row.get("remark")),
        })

    instruments: list[dict] = []
    for key in order:
        inst = grouped[key]
        sections = list(inst["sections"].values())
        for sec in sections:
            items = sec["items"]
            has_no = any(i.get("isSPPISatisfied") == "no" for i in items)
            has_null = any(i.get("isSPPISatisfied") in (None, "") for i in items)
            has_yes = any(i.get("isSPPISatisfied") == "yes" for i in items)
            if has_no:
                sec["sectionConclusion"] = "fail"
            elif has_null:
                sec["sectionConclusion"] = None
            elif not has_yes:
                sec["sectionConclusion"] = "na"
            else:
                sec["sectionConclusion"] = "pass"
        has_fail = any(s.get("sectionConclusion") == "fail" for s in sections)
        has_incomplete = any(s.get("sectionConclusion") is None for s in sections)
        has_pass = any(s.get("sectionConclusion") == "pass" for s in sections)
        if has_fail:
            overall = "fail"
        elif has_incomplete or not has_pass:
            overall = None
        else:
            overall = "pass"
        instruments.append({
            "id": inst["id"],
            "name": inst["name"],
            "sections": sections,
            "overallConclusion": overall,
            "hasFailedSection": has_fail,
        })

    agg_fail = any(i.get("overallConclusion") == "fail" for i in instruments)
    agg_null = any(i.get("overallConclusion") is None for i in instruments)
    agg_pass = any(i.get("overallConclusion") == "pass" for i in instruments)
    if agg_fail:
        agg = "fail"
    elif agg_null or not agg_pass:
        agg = None
    else:
        agg = "pass"

    active_id = instruments[0]["id"] if instruments else None
    return {
        "instruments": instruments,
        "activeInstrumentId": active_id,
        "overallConclusion": agg,
        "hasFailedSection": agg_fail,
        "sections": instruments[0]["sections"] if instruments else (prev.get("sections") or []),
    }


async def _load_g6_8_payload(db: AsyncSession, wp_id: str) -> dict | None:
    payload = await load_json_payload(db, wp_id, _G6_8_PRIMARY_ITEM_ID, field="conclusion")
    if payload is None:
        payload = await load_json_payload(db, wp_id, _G6_8_PRIMARY_ITEM_ID, field="remark")
    return payload if isinstance(payload, dict) else None


async def _load_g6_8_flat_rows(db: AsyncSession, wp_id: str) -> list[dict]:
    payload = await _load_g6_8_payload(db, wp_id)
    return _flatten_g6_8_payload(payload or {})


def _parse_g6_8_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-8导入文件（单sheet，14列）。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows: list[dict] = []

    ws = wb.active
    if ws is None:
        wb.close()
        return [], [{"row_number": 0, "field": "", "reason": "xlsx文件中无活动工作表"}]

    header_row_idx = 1
    for r in range(1, min(6, (ws.max_row or 1) + 1)):
        row_cells = list(ws.iter_rows(min_row=r, max_row=r))
        if not row_cells:
            continue
        test_row = [str(c.value).strip() if c.value else "" for c in row_cells[0]]
        if "投资项目" in test_row and ("检查项目" in test_row or "是否满足SPPI" in test_row):
            header_row_idx = r
            break

    for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
        if all(v is None for v in row):
            continue
        if row_idx >= ROW_LIMIT:
            errors.append({"row_number": row_idx, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
            break
        values = list(row) + [None] * max(0, len(_G6_8_KEYS) - len(row))
        parsed: dict[str, Any] = {"instrumentId": str(uuid4())}
        for col_i, key in enumerate(_G6_8_KEYS):
            if col_i >= len(values):
                break
            raw = values[col_i]
            if key == "seq":
                parsed[key] = int(safe_float(raw) or 0)
            else:
                parsed[key] = safe_str(raw)
        if not parsed.get("investProject") and not parsed.get("checkItem"):
            continue
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

def _build_g6_10_multi_sheet_workbook(
    payload: dict | list | None = None,
    *,
    template_only: bool = False,
) -> Workbook:
    """G6-10 按2区段分sheet导出；倒轧计算与增减明细使用各自数据源。"""
    wb = Workbook()
    wb.remove(wb.active)

    nested: dict
    if isinstance(payload, dict) and ("items" in payload or "changeDetails" in payload):
        nested = payload
    elif isinstance(payload, list):
        nested = _nest_g6_10_flat_rows(payload)
    else:
        nested = {"items": [], "changeDetails": []}

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
            for row_data in _g6_10_seg_rows(nested, seg_name):
                # 交易类型导出为中文标签，便于人工填写
                export_row = dict(row_data)
                if seg_name == "增减明细":
                    tx = safe_str(export_row.get("transactionType"))
                    label_map = {
                        "buy": "买入", "sell": "卖出",
                        "mature": "到期", "transfer": "转让(转出)",
                        "transfer_in": "转入", "transfer_out": "转出",
                    }
                    export_row["transactionType"] = label_map.get(tx, tx)
                ws.append(export_row_by_keys(export_row, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G6-10 盘点倒轧表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "2区段分sheet：倒轧计算 / 增减明细（含证券代码列）。",
        "基准日数量：期后盘点=盘点−增减净增加；期前盘点=盘点+净增加；同日=盘点（前端按日期方向自动计算）。",
        "增减净增加：买入/转入为正，卖出/到期/转出/转让为负；可由增减明细按证券代码或名称自动汇总。",
        "差异 = 基准日数量 − 账面数量（前端自动计算）。",
        "交易类型填：买入 / 卖出 / 到期 / 转入 / 转出 / 转让。",
        "差异不为零时，差异原因与差异结论均必填。",
        "空文件或无有效行将拒绝覆盖现有数据；增减明细须对应倒轧计算表中的证券。",
        "导入后写入 G6-10-reconciliation-data（嵌套）并双写 G6-10-rows。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g6_10_sheet_rows(
    ws: Any,
    seg_keys: list[str],
    *,
    header_hint_row: int = 2,
) -> list[dict]:
    """解析单个 G6-10 区段 sheet 为行列表。"""
    rows: list[dict] = []
    header_row_idx = header_hint_row
    for r in range(1, min(5, (ws.max_row or 1) + 1)):
        row_cells = list(ws.iter_rows(min_row=r, max_row=r))
        if not row_cells:
            continue
        test_row = [str(c.value).strip() if c.value else "" for c in row_cells[0]]
        if "证券名称" in test_row:
            header_row_idx = r
            break

    for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
        if all(v is None for v in row):
            continue
        if row_idx >= ROW_LIMIT:
            break
        values = list(row) + [None] * max(0, len(seg_keys) - len(row))
        parsed: dict[str, Any] = {"id": str(uuid4())}
        for col_i, key in enumerate(seg_keys):
            if col_i >= len(values):
                break
            raw = values[col_i]
            if key in _G6_10_NUMERIC_KEYS:
                parsed[key] = safe_float(raw)
            elif key == "transactionType":
                parsed[key] = _normalize_g6_10_tx_type(raw)
            else:
                parsed[key] = safe_str(raw)
        rows.append(parsed)
    return rows


def _parse_g6_10_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-10导入文件，返回扁平行（随后 nest 为嵌套结构）。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    flat_rows: list[dict] = []

    # 策略1: 多sheet格式（2区段分sheet）— 各自独立解析后合并
    multi_sheet = len(wb.sheetnames) >= 2 and any(
        ("倒轧" in s) or ("增减" in s) for s in wb.sheetnames
    )

    if multi_sheet:
        for seg_name, _seg_headers, seg_keys in _G6_10_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append({"row_number": 0, "field": "", "reason": f"缺少工作表: {seg_name}"})
                continue
            seg_rows = _parse_g6_10_sheet_rows(ws, seg_keys)
            if seg_name == "增减明细":
                # 标记为明细行：确保 nest 时进入 changeDetails
                for r in seg_rows:
                    if not r.get("transactionType") and not r.get("date"):
                        r["transactionType"] = r.get("transactionType") or ""
                    # 清除倒轧字段，避免误判为倒轧行
                    r.pop("countDateQuantity", None)
                    r.pop("changeQuantity", None)
                    r.pop("bookQuantity", None)
                    r.pop("varianceReason", None)
                    r.pop("varianceConclusion", None)
                    r.pop("indexRef", None)
                    if not r.get("date") and not r.get("transactionType") and not r.get("voucherNo"):
                        # 空行跳过
                        continue
                    flat_rows.append(r)
            else:
                flat_rows.extend(seg_rows)
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
        all_headers = _G6_10_SEG1_HEADERS + _G6_10_SEG2_HEADERS[2:]  # 去重证券名称/证券代码
        all_keys = _G6_10_SEG1_KEYS + _G6_10_SEG2_KEYS[2:]
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
                    elif key == "transactionType":
                        parsed[key] = _normalize_g6_10_tx_type(raw)
                    else:
                        parsed[key] = safe_str(raw)
            flat_rows.append(parsed)

    wb.close()
    if len(flat_rows) > ROW_LIMIT:
        flat_rows = flat_rows[:ROW_LIMIT]
        errors.append({"row_number": ROW_LIMIT, "field": "", "reason": f"超过{ROW_LIMIT}行限制"})
    return flat_rows, errors


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
                "实际利息 = 计息基础 × 实际利率 × 计息天数/年天数（计息基准 ACT/365 或 ACT/360）。",
                "现金流入 = 剩余面值 × 票面利率 × 计息天数/年天数（剩余面值=面值−此前收回本金）。",
                "期末摊余 = 期初摊余 + 实际利息 - 现金流入 - 已收回本金。",
                "票面利率和实际利率可填小数（0.05）或百分数（5）；系统统一按小数存储。",
                "计息基准填：ACT/365（默认）、ACT/360 或 30/360。",
                "减值阶段填：Stage1 / Stage2 / Stage3。",
                "天数手工覆盖、期初手工覆盖填：是/否（或 true/false）。",
                "旧版 11 列模板仍可导入；缺列字段将从底稿已有数据按项目+截止日合并保留。",
                "导入后写入 G6-6-interest-data（嵌套）并双写 G6-6-rows（扁平）。",
                "所有金额列以元为单位。",
            ],
        )
        return workbook_to_response(wb, "G6-6_利息测算表_模板.xlsx")
    elif sheet == "G6-8":
        wb = build_workbook_template(
            "G6-8",
            _G6_8_HEADERS,
            title="G6-8 SPPI合同现金流量测试",
            guidance=[
                "G6-8 SPPI 测试 编制说明",
                "",
                "每行 = 投资项目 × 检查项。",
                "是否满足SPPI 填：是/否/不适用（或 yes/no/na）。",
                "风险等级填：高/中/低（或 high/medium/low）。",
                "导入后写入 G6-8-sppi-test-data（嵌套 instruments）。",
                "建议先导出模板，按项目复制默认检查项行后填写。",
            ],
        )
        return workbook_to_response(wb, "G6-8_SPPI合同现金流量测试_模板.xlsx")
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
                "可选填：差异原因、差异结论、权属主体、受限类型(none/pledge/freeze/restricted/other)、受限说明、证据索引、索引。",
                "面值以元为单位。",
                "导入后写入 G6-9-securities-inventory-data（嵌套，保留 meta）并双写 G6-9-rows（扁平）。",
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
    if sheet == "G6-6":
        rows = await _load_g6_6_flat_rows(db, wp_id)
    elif sheet == "G6-8":
        rows = await _load_g6_8_flat_rows(db, wp_id)
    elif sheet == "G6-9":
        rows = await _load_g6_9_flat_rows(db, wp_id)
    elif sheet == "G6-10":
        rows = await _load_g6_10_flat_rows(db, wp_id)
    else:
        item_id = _ITEM_IDS[sheet]
        rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
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
    elif sheet == "G6-8":
        wb = build_workbook_template(
            "G6-8",
            _G6_8_HEADERS,
            title="G6-8 SPPI合同现金流量测试",
            guidance=["每行=投资项目×检查项。是否满足SPPI填是/否/不适用。"],
        )
        ws = wb["G6-8"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G6_8_KEYS))
        return workbook_to_response(wb, "G6-8_SPPI合同现金流量测试_数据.xlsx")
    elif sheet == "G6-9":
        wb = build_workbook_template(
            "G6-9",
            _G6_9_HEADERS,
            title="G6-9 有价证券盘点表",
            guidance=[
                "每行一项证券盘点记录。差异前端自动计算。",
                "导出优先读取 G6-9-securities-inventory-data，兼容 G6-9-rows。",
            ],
        )
        ws = wb["G6-9"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G6_9_KEYS))
        return workbook_to_response(wb, "G6-9_有价证券盘点表_数据.xlsx")
    else:  # G6-10
        nested = await _load_g6_10_nested_payload(db, wp_id) or {"items": [], "changeDetails": []}
        wb = _build_g6_10_multi_sheet_workbook(nested, template_only=False)
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
    elif sheet == "G6-8":
        rows, errors = _parse_g6_8_import(content)
    elif sheet == "G6-9":
        rows, errors = _parse_g6_9_import(content)
    else:  # G6-10
        rows, errors = _parse_g6_10_import(content)
        if not rows:
            raise HTTPException(
                422,
                detail={
                    "message": "导入校验失败",
                    "errors": errors or [{"row_number": 0, "field": "", "reason": "导入结果为空，已拒绝覆盖现有数据"}],
                },
            )

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
    elif sheet == "G6-8":
        existing = await _load_g6_8_payload(db, wp_id)
        nested = _nest_g6_8_flat_rows(rows, existing=existing)
        await _upsert_dual_fields(db, wp_id, _G6_8_PRIMARY_ITEM_ID, nested)
    elif sheet == "G6-9":
        existing = await _load_g6_9_nested_payload(db, wp_id)
        nested = _nest_g6_9_flat_rows(rows, existing=existing)
        flat = _flatten_g6_9_items(nested.get("items") or [])
        # UI 读嵌套 G6-9-securities-inventory-data；IE 读扁平 G6-9-rows — 双写
        await _upsert_dual_fields(db, wp_id, _G6_9_PRIMARY_ITEM_ID, nested)
        await _upsert_dual_fields(db, wp_id, item_id, flat)
    elif sheet == "G6-10":
        existing = await _load_g6_10_nested_payload(db, wp_id)
        nested = _nest_g6_10_flat_rows(rows, existing=existing)
        validation_errors = _validate_g6_10_nested(nested)
        if validation_errors:
            raise HTTPException(422, detail={"message": "导入校验失败", "errors": validation_errors})
        # UI 与 IE 均存嵌套结构，便于前端直接 loadData；rows 键保持兼容
        await _upsert_dual_fields(db, wp_id, _G6_10_PRIMARY_ITEM_ID, nested)
        await _upsert_dual_fields(db, wp_id, item_id, nested)
        return {
            "ok": True,
            "imported_count": len(nested.get("items") or []) + len(nested.get("changeDetails") or []),
            "errors": errors,
            "sheet": sheet,
        }
    else:
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")

    return {
        "ok": True,
        "imported_count": len(rows),
        "errors": errors,
        "sheet": sheet,
    }
