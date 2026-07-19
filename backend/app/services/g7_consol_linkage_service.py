"""G7 长期股权投资到合并工作底稿的受控联动服务。

只把 G7 审定基础数据转换为合并侧输入，不自动生成正式抵消分录。
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


SOURCE_KEYS = (
    "G7-2-rows",
    "G7-3-rows",
    "G7-4-rows",
    "G7-5-rows",
    "G7-6-rows",
    "G7-8-rows",
    "G7-9-rows",
    "G7-10-rows",
    "G7-12-rows",
    "G7-13-rows",
    "G7-14-equity-method-calc",
    "G7-14-rows",
    "G7-15-rows",
    "G7-15-internal-transaction",
    "G7-16-rows",
    "G7-17-rows",
    "G7-17-impairment-test",
)
TARGET_SHEETS = ("info", "cost", "equity_inv", "net_asset")

# 合并净资产表权益项目（与 ConsolWorksheetTabs.EQUITY_ITEMS 对齐）
EQUITY_ITEMS = (
    "实收资本（或股本）",
    "其他权益工具",
    "资本公积",
    "减：库存股",
    "其他综合收益",
    "专项储备",
    "盈余公积",
    "△一般风险准备",
    "未分配利润",
)

# G7-14 净资产调整字段 → 合并净资产表项目
G714_TO_NET_ASSET = {
    "shareCapital": "实收资本（或股本）",
    "capitalReserve": "资本公积",
    "treasuryStock": "减：库存股",
    "oci": "其他综合收益",
    "specialReserve": "专项储备",
    "surplusReserve": "盈余公积",
    "retainedEarnings": "未分配利润",
}

# 无无损目标行：不并入未分配利润，仅回报跳过
G714_UNMAPPED_FIELDS = {
    "nonControllingInterest": "少数股东权益（展示项，不计入归母净资产）",
    "fvDiffAtAcquisition": "取得投资时公允价值差额（无对应行）",
    "otherProfitAdj": "其他需调整损益的项目（无对应行）",
    "openingFvDiffCumulative": "期初累计公允价值调整（无对应行）",
    "unrealizedInternalElim": "未实现内部交易损益（无对应行）",
}

# 表格型目标：按 company_code 行合并；net_asset 为矩阵
ROW_SHEETS = ("info", "cost", "equity_inv")
DIFF_SKIP_PREFIXES = ("_g7_", "_source")

# G7 各表比例口径（与前端模型一致）：
# - G7-4：百分数 0~100（旧版可能带 ratioScale=fraction）
# - G7-2 / G7-8~G7-17：小数 0~1
RATIO_SCALE_BY_ITEM: dict[str, Literal["percent", "fraction"]] = {
    "G7-4-rows": "percent",
    "G7-2-rows": "fraction",
    "G7-8-rows": "fraction",
    "G7-9-rows": "fraction",
    "G7-10-rows": "fraction",
    "G7-12-rows": "fraction",
    "G7-13-rows": "fraction",
    "G7-14-rows": "fraction",
    "G7-14-equity-method-calc": "fraction",
    "G7-15-rows": "fraction",
    "G7-15-internal-transaction": "fraction",
    "G7-16-rows": "fraction",
    "G7-17-rows": "fraction",
    "G7-17-impairment-test": "fraction",
}


class G7LinkageConflictError(Exception):
    """源版本与预览不一致，需重新预览。"""

    def __init__(self, message: str, *, stale_keys: list[str] | None = None):
        super().__init__(message)
        self.stale_keys = stale_keys or []


class G7LinkageConfigError(Exception):
    """G7 实例配置错误（缺失或重复）。"""


def _json_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _rows(value: Any) -> list[dict[str, Any]]:
    parsed = _json_value(value)
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    if not isinstance(parsed, dict):
        return []
    for key in ("rows", "data", "items"):
        candidate = parsed.get(key)
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
    groups = parsed.get("groups")
    if isinstance(groups, list):
        result: list[dict[str, Any]] = []
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("rows"), list):
                result.extend(row for row in group["rows"] if isinstance(row, dict))
        return result
    return []


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not result.is_finite():
        return None
    return result


def _money(value: Any) -> float | None:
    """对外 JSON 仍用 float，内部计算用 Decimal 再量化到分。"""
    result = _decimal(value)
    if result is None:
        return None
    return float(result.quantize(Decimal("0.01")))


def _ratio_to_percent(
    value: Any,
    *,
    scale: Literal["percent", "fraction"],
) -> float | None:
    """统一输出合并 UI 百分数（0~100）。"""
    result = _decimal(value)
    if result is None:
        return None
    if scale == "fraction":
        result = result * Decimal("100")
    return float(result.quantize(Decimal("0.000001")))


def _name(row: dict[str, Any]) -> str:
    return str(
        row.get("investeeName")
        or row.get("companyName")
        or row.get("company_name")
        or row.get("sub_name")
        or ""
    ).strip()


def _normal_name(value: str) -> str:
    return re.sub(r"[\s（）()]+", "", value or "").casefold()


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def _merge_non_empty(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def _g7_4_ratio_scale(payload: Any) -> Literal["percent", "fraction"]:
    """G7-4 默认百分数；payload.ratioScale=fraction 时按小数。"""
    if isinstance(payload, dict):
        scale = str(payload.get("ratioScale") or "").strip().lower()
        if scale == "fraction":
            return "fraction"
        if scale == "percent":
            return "percent"
    return "percent"


def build_company_lookup(
    companies: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], set[str]]:
    """按规范化名称建索引；同名多代码记入 ambiguous。"""
    by_code = {
        str(company.get("company_code") or ""): company
        for company in companies
        if company.get("company_code")
    }
    by_name: dict[str, list[dict[str, Any]]] = {}
    for company in companies:
        name = _normal_name(str(company.get("company_name") or ""))
        if not name or not company.get("company_code"):
            continue
        by_name.setdefault(name, []).append(company)
    ambiguous = {name for name, items in by_name.items() if len(items) > 1}
    unique_by_name = {
        name: items[0]
        for name, items in by_name.items()
        if len(items) == 1
    }
    return by_code, unique_by_name, ambiguous


def build_default_net_asset_rows() -> list[dict[str, Any]]:
    """对齐前端 buildNetAsset() 完整结构；权益滚存行带 section 便于定位。"""
    rows: list[dict[str, Any]] = []

    def mk(seq: str, item: str, **extra: Any) -> dict[str, Any]:
        return {
            "seq": seq,
            "item": item,
            "total": None,
            "parent": None,
            "values": [],
            **extra,
        }

    rows.append(mk("1", "所有者权益/股东权益", isHeader=True, bold=True))
    rows.append(mk("", "期初合计：", bold=True, isComputed=True, section="opening_total"))
    for item in EQUITY_ITEMS:
        rows.append(mk("", item, indent=1, section="opening"))
    rows.append(mk("", "本期增加", bold=True, isComputed=True, section="increase_total"))
    for item in EQUITY_ITEMS:
        rows.append(mk("", item, indent=1, section="increase"))
    rows.append(mk("", "本期减少", bold=True, isComputed=True, section="decrease_total"))
    for item in EQUITY_ITEMS:
        rows.append(mk("", item, indent=1, section="decrease"))
    rows.append(mk("", "期末金额", bold=True, isComputed=True, section="closing_total"))
    for item in EQUITY_ITEMS:
        rows.append(mk("", item, indent=1, isComputed=True, section="closing"))

    # 与前端 buildNetAsset() 后续区段保持一致，避免覆盖后丢失结构
    rows.append(mk("2", "利润及利润分配表", isHeader=True, bold=True))
    rows.append(mk("", "一、期初金额", bold=True))
    rows.append(mk("", "二、本年增减变动金额", bold=True, isComputed=True))
    rows.append(mk("", "（一）综合收益总额", indent=1))
    rows.append(mk("", "其中：当期归母净利润", indent=2))
    rows.append(mk("", "（二）所有者投入和减少资本", indent=1, isComputed=True))
    for item in (
        "2-1所有者投入的普通股",
        "2-2其他权益工具持有者投入资本",
        "2-3股份支付计入所有者权益的金额",
        "2-4其他",
    ):
        rows.append(mk("", item, indent=2))
    rows.append(mk("", "（三）专项储备提取和使用", indent=1, isComputed=True))
    for item in ("3-1提取专项储备", "3-2使用专项储备"):
        rows.append(mk("", item, indent=2))
    rows.append(mk("", "（四）利润分配", indent=1, isComputed=True))
    for item in (
        "4-1提取盈余公积",
        "4-1-1法定公积金",
        "4-1-2任意公积金",
        "4-1-3#储备基金",
        "4-1-4#企业发展基金",
        "4-1-5#利润归还投资",
        "4-2△提取一般风险准备",
        "4-3对所有者（或股东）的分配",
        "4-4其他",
    ):
        rows.append(mk("", item, indent=2))
    rows.append(mk("", "（五）所有者权益内部结转", indent=1, isComputed=True))
    for item in (
        "5-1资本公积转增资本（或股本）",
        "5-2盈余公积转增资本（或股本）",
        "5-3弥补亏损",
        "5-4 设定受益计划变动额结转留存收益",
        "5-5其他综合收益结转留存收益",
        "5-6其他",
    ):
        rows.append(mk("", item, indent=2))
    rows.append(mk("", "三、本年年末余额", bold=True, isComputed=True))
    rows.append(mk("3", "资本公积变动表", isHeader=True, bold=True))
    rows.append(mk("", "期初金额"))
    rows.append(mk("", "其中：国有独享资本公积", indent=1))
    rows.append(mk("", "本期变动", isComputed=True))
    for item in ("其中：资本溢价", "其他资本公积", "国有独享资本公积"):
        rows.append(mk("", item, indent=1))
    rows.append(mk("", "期末金额", bold=True, isComputed=True))
    rows.append(mk("", "其中：国有独享资本公积", indent=1, isComputed=True))
    return rows


def index_net_asset_equity_rows(rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    """定位 (section, equity_item) → 行下标；兼容无 section 的旧前端结构。"""
    mapping: dict[tuple[str, str], int] = {}
    section: str | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        item = str(row.get("item") or "")
        tagged = str(row.get("section") or "")
        if tagged in {"opening", "increase", "decrease", "closing"} and item in EQUITY_ITEMS:
            mapping[(tagged, item)] = index
            continue
        if "期初合计" in item:
            section = "opening"
            continue
        if item == "本期增加":
            section = "increase"
            continue
        if item == "本期减少":
            section = "decrease"
            continue
        if item == "期末金额":
            section = "closing"
            continue
        if item in {"利润及利润分配表", "资本公积变动表"}:
            section = None
            continue
        if section and item in EQUITY_ITEMS:
            mapping[(section, item)] = index
    return mapping


def _rollforward_value(item: Any, phase: str) -> float | None:
    if not isinstance(item, dict):
        return None
    begin = _money(item.get("begin") or item.get("opening"))
    increase = _money(item.get("increase"))
    decrease = _money(item.get("decrease"))
    if phase == "opening":
        return begin
    if phase == "increase":
        return increase
    if phase == "decrease":
        return decrease
    if phase == "closing":
        if begin is None and increase is None and decrease is None:
            return None
        return float(
            (
                Decimal(str(begin or 0))
                + Decimal(str(increase or 0))
                - Decimal(str(decrease or 0))
            ).quantize(Decimal("0.01"))
        )
    return None


def extract_net_asset_adjustments(payloads: dict[str, Any]) -> list[dict[str, Any]]:
    """从 G7-14 页面 payload 提取 netAssetAdjustments。"""
    page = payloads.get("G7-14-equity-method-calc")
    if isinstance(page, dict):
        raw = page.get("netAssetAdjustments") or page.get("net_asset_adjustments")
        if isinstance(raw, list):
            return [row for row in raw if isinstance(row, dict)]
    return []


def build_net_asset_payload(
    adjustments: list[dict[str, Any]],
    resolve_company: Any,
) -> dict[str, Any]:
    """将多公司净资产调整 pivot 为合并 net_asset 矩阵。

    库存股在 G7 合计中为减项，合并表 values 直接求和，故写入负数。
    无目标行的调整项记入 skipped_fields，不静默并入其他权益项目。
    """
    company_order: list[str] = []
    company_names: dict[str, str] = {}
    cells: dict[tuple[str, str, str], float] = {}  # (section, item, code) -> amount
    skipped_fields: list[dict[str, str]] = []

    def _has_rollforward(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        return any(
            _money(item.get(k)) is not None
            for k in ("begin", "opening", "increase", "decrease")
        )

    for adj in adjustments:
        name = _name(adj)
        if not name:
            continue
        company = resolve_company(name)
        if not company or not company.get("company_code"):
            continue
        code = str(company["company_code"])
        if code not in company_order:
            company_order.append(code)
            company_names[code] = name
        for field, label in G714_TO_NET_ASSET.items():
            rf = adj.get(field)
            for section in ("opening", "increase", "decrease", "closing"):
                amount = _rollforward_value(rf, section)
                if amount is None:
                    continue
                # 合并表对「减：库存股」行直接求和，需反号才能与 G7 合计口径一致
                if field == "treasuryStock":
                    amount = float((-Decimal(str(amount))).quantize(Decimal("0.01")))
                cells[(section, label, code)] = amount
        for field, reason in G714_UNMAPPED_FIELDS.items():
            if _has_rollforward(adj.get(field)):
                skipped_fields.append({
                    "investee_name": name,
                    "company_code": code,
                    "field": field,
                    "reason": reason,
                })

    rows = build_default_net_asset_rows()
    n = len(company_order)
    for row in rows:
        section = str(row.get("section") or "")
        item = str(row.get("item") or "")
        values: list[float | None] = [None] * n
        if section in {"opening", "increase", "decrease", "closing"} and item in EQUITY_ITEMS:
            for index, code in enumerate(company_order):
                values[index] = cells.get((section, item, code))
        row["values"] = values

    return {
        "company_order": company_order,
        "company_names": company_names,
        "rows": rows,
        "skipped_fields": skipped_fields,
        "_source": {"sheet": "G7-14", "kind": "netAssetAdjustments"},
    }


def build_g79_suggestions(
    payloads: dict[str, Any],
    resolve_company: Any,
) -> list[dict[str, Any]]:
    """G7-9 商誉/少数股东建议草稿（默认不自动入账）。"""
    suggestions: list[dict[str, Any]] = []
    for row in _rows(payloads.get("G7-9-rows")):
        if str(row.get("section") or "merger") != "merger":
            continue
        name = _name(row)
        company = resolve_company(name) if name else None
        if not company or not company.get("company_code"):
            continue
        ratio = _ratio_to_percent(row.get("ownershipRatio"), scale="fraction")
        suggestions.append({
            "id": f"g7-9-{row.get('id') or company['company_code']}",
            "type": "goodwill_nci",
            "source_sheet": "G7-9",
            "company_code": company["company_code"],
            "company_name": name,
            "acquisition_date": row.get("acquisitionDate") or None,
            "acquisition_cost": _money(row.get("initialInvestmentCost")),
            "identifiable_net_assets_fv": _money(
                row.get("acquireeIdentifiableNetAssetsFV")
            ),
            "parent_share_ratio": ratio,
            "goodwill_amount": _money(row.get("goodwill")),
            "non_controlling_interest_share": _money(
                row.get("nonControllingInterestShare")
            ),
            "selected_default": False,
            "note": "建议草稿：确认后才写入商誉/少数股东结构化表",
        })
    return suggestions


def enrich_info_from_g710(
    info_by_name: dict[str, dict[str, Any]],
    payloads: dict[str, Any],
    resolve_company: Any,
    unresolved: set[str],
    ambiguous: set[str],
) -> None:
    """用 G7-10 购买少数/部分处置标记基本信息股比变动（不写复杂 share_change 矩阵）。"""
    for row in _rows(payloads.get("G7-10-rows")):
        section = str(row.get("section") or "")
        if section not in {"nci", "partialDisposal"}:
            continue
        name = _name(row)
        if not name:
            continue
        company = resolve_company(name)
        if not company or not company.get("company_code"):
            if name not in ambiguous:
                unresolved.add(name)
            continue
        code = str(company["company_code"])
        info = info_by_name.get(name)
        if not info:
            info = {
                "company_code": code,
                "company_name": name,
                "parent_code": company.get("parent_code") or "",
                "_source": {"sheet": "G7-10", "kind": section},
            }
            info_by_name[name] = info
        info["share_changed"] = "是"
        times = int(info.get("change_times") or 0)
        info["change_times"] = max(times, 1)
        before = _ratio_to_percent(row.get("originalRatio"), scale="fraction")
        if section == "nci":
            added = _ratio_to_percent(row.get("addedRatio"), scale="fraction")
            after = (
                None
                if before is None and added is None
                else float(
                    (Decimal(str(before or 0)) + Decimal(str(added or 0))).quantize(
                        Decimal("0.000001")
                    )
                )
            )
            info["_g7_share_change_type"] = "购买少数股权"
        else:
            reduced = _ratio_to_percent(row.get("reducedRatio"), scale="fraction")
            after = (
                None
                if before is None and reduced is None
                else float(
                    (Decimal(str(before or 0)) - Decimal(str(reduced or 0))).quantize(
                        Decimal("0.000001")
                    )
                )
            )
            info["_g7_share_change_type"] = "不丧失控制权处置"
        if before is not None:
            info["_g7_ratio_before"] = before
        if after is not None:
            info["_g7_ratio_after"] = after
            # 非同一控制持股比例空值时补填变动后比例
            if info.get("non_common_ratio") in (None, ""):
                info["non_common_ratio"] = after
        info["_g7_g7_10_change"] = {
            "section": section,
            "equity_adjustment": _money(
                row.get("equityAdjustment") or row.get("consolEquityAdj")
            ),
            "adj_capital_reserve": _money(row.get("adjCapitalReserve")),
            "adj_surplus_reserve": _money(row.get("adjSurplusReserve")),
            "adj_retained_earnings": _money(row.get("adjRetainedEarnings")),
        }


def build_g710_suggestions(
    payloads: dict[str, Any],
    resolve_company: Any,
) -> list[dict[str, Any]]:
    """G7-10 股比变动/资本公积权益调整建议（不自动写 share_change 复杂矩阵）。"""
    suggestions: list[dict[str, Any]] = []
    for row in _rows(payloads.get("G7-10-rows")):
        section = str(row.get("section") or "")
        if section not in {"nci", "partialDisposal"}:
            continue
        name = _name(row)
        company = resolve_company(name) if name else None
        if not company or not company.get("company_code"):
            continue
        before = _ratio_to_percent(row.get("originalRatio"), scale="fraction")
        if section == "nci":
            delta = _ratio_to_percent(row.get("addedRatio"), scale="fraction")
            after = (
                None
                if before is None and delta is None
                else float(
                    (Decimal(str(before or 0)) + Decimal(str(delta or 0))).quantize(
                        Decimal("0.000001")
                    )
                )
            )
            equity_adj = _money(row.get("equityAdjustment"))
            change_type = "购买少数股权"
            amount = _money(row.get("purchaseCost"))
        else:
            delta = _ratio_to_percent(row.get("reducedRatio"), scale="fraction")
            after = (
                None
                if before is None and delta is None
                else float(
                    (Decimal(str(before or 0)) - Decimal(str(delta or 0))).quantize(
                        Decimal("0.000001")
                    )
                )
            )
            equity_adj = _money(row.get("consolEquityAdj"))
            change_type = "不丧失控制权处置"
            amount = _money(row.get("consideration"))
        suggestions.append({
            "id": f"g7-10-{row.get('id') or company['company_code']}-{section}",
            "type": "share_change_capital",
            "source_sheet": "G7-10",
            "company_code": company["company_code"],
            "company_name": name,
            "change_type": change_type,
            "before_ratio": before,
            "after_ratio": after,
            "amount": amount,
            "equity_adjustment": equity_adj,
            "adj_capital_reserve": _money(row.get("adjCapitalReserve")),
            "adj_surplus_reserve": _money(row.get("adjSurplusReserve")),
            "adj_retained_earnings": _money(row.get("adjRetainedEarnings")),
            "target_hint": "share_change / capital",
            "selected_default": False,
            "note": "建议草稿：股比变动与资本公积权益调整需人工复核后入正式表，不自动生成抵消分录",
        })
    return suggestions


def build_g73_suggestions(
    payloads: dict[str, Any],
) -> list[dict[str, Any]]:
    """G7-3 AJE/RJE → 合并调整建议草稿（绝不写入正式抵消分录）。"""
    suggestions: list[dict[str, Any]] = []
    for index, row in enumerate(_rows(payloads.get("G7-3-rows"))):
        debit = _money(row.get("debitAmount"))
        credit = _money(row.get("creditAmount"))
        if debit in (None, 0) and credit in (None, 0):
            continue
        suggestions.append({
            "id": f"g7-3-{row.get('id') or index}",
            "type": "consol_adjustment_draft",
            "source_sheet": "G7-3",
            "company_code": row.get("companyCode") or row.get("company_code") or "",
            "company_name": (
                row.get("companyName")
                or row.get("investeeName")
                or row.get("reportItem")
                or ""
            ),
            "entry_type": row.get("entryType") or "AJE",
            "account_code": row.get("accountCode") or "",
            "account_name": row.get("accountName") or "",
            "debit_amount": debit,
            "credit_amount": credit,
            "description": row.get("description") or row.get("summary") or "",
            "index_ref": row.get("indexRef") or "",
            "source_kind": row.get("sourceKind") or "",
            "selected_default": False,
            "note": "建议草稿：仅可进入合并调整草稿，不得直接当作抵消分录",
        })
    return suggestions


def collect_all_suggestions(
    payloads: dict[str, Any],
    resolve_company: Any,
) -> list[dict[str, Any]]:
    suggestions = build_g79_suggestions(payloads, resolve_company)
    suggestions.extend(build_g710_suggestions(payloads, resolve_company))
    suggestions.extend(build_g73_suggestions(payloads))
    return suggestions


def build_field_diffs(
    existing_sheets: dict[str, list[dict[str, Any]]],
    importable: dict[str, list[dict[str, Any]]],
    *,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    """生成表格型底稿的字段级差异。"""
    diffs: list[dict[str, Any]] = []
    for sheet in ROW_SHEETS:
        existing_map = {
            str(row.get("company_code")): row
            for row in existing_sheets.get(sheet, [])
            if isinstance(row, dict) and row.get("company_code")
        }
        for incoming in importable.get(sheet, []):
            code = str(incoming.get("company_code") or "")
            if not code:
                continue
            old_row = existing_map.get(code)
            for field, new_value in incoming.items():
                if field.startswith(DIFF_SKIP_PREFIXES) or field == "company_code":
                    continue
                if new_value in (None, ""):
                    continue
                old_value = old_row.get(field) if old_row else None
                if old_row is None:
                    status = "added"
                elif old_value in (None, ""):
                    status = "changed"
                elif old_value == new_value:
                    status = "unchanged"
                else:
                    status = "conflict"
                selected = status in {"added", "changed"} or (
                    overwrite and status == "conflict"
                )
                if status == "unchanged":
                    selected = False
                diffs.append({
                    "sheet_key": sheet,
                    "identity": code,
                    "company_name": incoming.get("company_name") or "",
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "status": status,
                    "selected": selected,
                })
    return diffs


def apply_selected_diffs(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    selected: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    """按勾选字段合并；selected 为 (company_code, field)。空集合表示不写入业务字段。"""
    result = deepcopy(existing)
    positions = {
        str(row.get("company_code")): index
        for index, row in enumerate(result)
        if isinstance(row, dict) and row.get("company_code")
    }
    for source in incoming:
        code = str(source.get("company_code") or "")
        if not code:
            continue
        selected_fields = {field for c, field in selected if c == code}
        if not selected_fields:
            continue
        if code not in positions:
            new_row: dict[str, Any] = {
                "company_code": code,
                "company_name": source.get("company_name") or "",
            }
            for key, value in source.items():
                if key in {"company_code", "company_name"}:
                    continue
                if key.startswith(DIFF_SKIP_PREFIXES):
                    new_row[key] = deepcopy(value)
                elif key in selected_fields and value not in (None, ""):
                    new_row[key] = deepcopy(value)
            positions[code] = len(result)
            result.append(new_row)
            continue
        target = result[positions[code]]
        for key, value in source.items():
            if key.startswith(DIFF_SKIP_PREFIXES):
                target[key] = deepcopy(value)
            elif key in selected_fields and value not in (None, ""):
                target[key] = deepcopy(value)
    return result


def merge_net_asset_rows(
    existing_rows: list[dict[str, Any]],
    incoming: dict[str, Any],
    company_order: list[str],
    *,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    """按 company_order 写入 values[]；默认只填空。兼容无 section 的旧表。"""
    base = deepcopy(existing_rows) if existing_rows else build_default_net_asset_rows()
    n = len(company_order)
    if n == 0:
        return base

    for row in base:
        values = row.get("values")
        if not isinstance(values, list):
            values = []
        while len(values) < n:
            values.append(None)
        row["values"] = values[:n]

    src_order = [str(c) for c in (incoming.get("company_order") or [])]
    src_index = {code: i for i, code in enumerate(src_order)}
    src_rows = incoming.get("rows") if isinstance(incoming.get("rows"), list) else []
    src_map = index_net_asset_equity_rows(
        [row for row in src_rows if isinstance(row, dict)]
    )
    dst_map = index_net_asset_equity_rows(base)

    for key, dst_i in dst_map.items():
        src_i = src_map.get(key)
        if src_i is None:
            continue
        src_values = src_rows[src_i].get("values")
        if not isinstance(src_values, list):
            continue
        dst_values = base[dst_i]["values"]
        for ci, code in enumerate(company_order):
            si = src_index.get(code)
            if si is None or si >= len(src_values):
                continue
            new_value = src_values[si]
            if new_value in (None, ""):
                continue
            if overwrite or dst_values[ci] in (None, ""):
                dst_values[ci] = new_value
        # 回写 section，便于下次精确定位
        section, item = key
        base[dst_i]["section"] = section
        base[dst_i]["item"] = item
    return base


def build_linkage_candidates(
    payloads: dict[str, Any],
    company_lookup: dict[str, dict[str, Any]],
    explicit_mappings: dict[str, str] | None = None,
    *,
    companies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """把各 G7 payload 转成合并表候选行；无稳定 company_code 的行只预览、不导入。"""
    explicit_mappings = explicit_mappings or {}
    if companies is not None:
        by_code, unique_by_name, ambiguous_names = build_company_lookup(companies)
    else:
        # 兼容旧测试：传入唯一名称→公司映射
        by_code = {
            str(company.get("company_code") or ""): company
            for company in company_lookup.values()
            if company.get("company_code")
        }
        unique_by_name = dict(company_lookup)
        ambiguous_names = set()

    unresolved: set[str] = set()
    ambiguous: set[str] = set()
    info_by_name: dict[str, dict[str, Any]] = {}
    cost_by_name: dict[str, dict[str, Any]] = {}
    equity_by_name: dict[str, dict[str, Any]] = {}
    sources_used: set[str] = set()

    def resolve(name: str) -> dict[str, Any] | None:
        explicit_code = explicit_mappings.get(name) or explicit_mappings.get(
            _normal_name(name)
        )
        if explicit_code and explicit_code in by_code:
            return by_code[explicit_code]
        key = _normal_name(name)
        if key in ambiguous_names and not explicit_code:
            ambiguous.add(name)
            return None
        return unique_by_name.get(key)

    def identity(row: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        name = _name(row)
        company = resolve(name) if name else None
        if name and not company and name not in ambiguous:
            unresolved.add(name)
        return name, company

    g74_scale = _g7_4_ratio_scale(payloads.get("G7-4-rows"))
    for row in _rows(payloads.get("G7-4-rows")):
        name, company = identity(row)
        if not name:
            continue
        sources_used.add("G7-4")
        direct = _ratio_to_percent(row.get("directHoldingRatio"), scale=g74_scale)
        indirect = _ratio_to_percent(row.get("indirectHoldingRatio"), scale=g74_scale)
        total_ratio = (
            None
            if direct is None and indirect is None
            else float(
                (Decimal(str(direct or 0)) + Decimal(str(indirect or 0))).quantize(
                    Decimal("0.000001")
                )
            )
        )
        group = str(row.get("groupType") or "")
        merge_type = str(row.get("acquisitionMethod") or "")
        info_by_name[name] = {
            "company_name": name,
            "company_code": company.get("company_code", "") if company else "",
            "parent_code": company.get("parent_code", "") if company else "",
            "accounting_method": row.get("accountingMethod") or (
                "成本法" if group == "subsidiary" else "权益法"
            ),
            "holding_type": (
                "直接+间接" if direct and indirect else ("间接" if indirect else "直接")
            ),
            "non_common_ratio": total_ratio if "非同" in merge_type else None,
            "common_ratio": (
                total_ratio
                if "同一控制" in merge_type and "非同" not in merge_type
                else None
            ),
            "merge_type": merge_type,
            "first_consol_date": row.get("acquisitionDate") or "",
            "_g7_group_type": group,
            "_g7_newly_consolidated": row.get("newlyConsolidated") or "",
            "_g7_ending_net_assets": _money(row.get("endingNetAssets")),
            "_g7_current_net_profit": _money(row.get("currentNetProfit")),
            "_source": {"sheet": "G7-4", "row_id": row.get("id")},
        }

    for row in _rows(payloads.get("G7-2-rows")):
        name, company = identity(row)
        section = str(row.get("section") or "")
        if not name or section not in {"cost", "equity"}:
            continue
        sources_used.add("G7-2")
        common = {
            "company_name": name,
            "company_code": company.get("company_code", "") if company else "",
            "_source": {"sheet": "G7-2", "row_id": row.get("id")},
        }
        if section == "cost":
            cost_by_name[name] = _merge_non_empty(common, {
                "current_dividend": _money(row.get("cashDividend")),
                "open_ratio": _ratio_to_percent(
                    _first(row, "auditedOpeningRatio", "openingRatio"),
                    scale="fraction",
                ),
                "open_cost": _money(_first(row, "auditedOpeningAmount", "openingAmount")),
                "add_ratio": _ratio_to_percent(
                    _first(row, "auditedIncreaseRatio", "increaseRatio"),
                    scale="fraction",
                ),
                "add_cost": _money(_first(row, "auditedIncreaseAmount", "increaseAmount")),
                "reduce_ratio": _ratio_to_percent(
                    _first(row, "auditedDecreaseRatio", "decreaseRatio"),
                    scale="fraction",
                ),
                "reduce_cost": _money(
                    _first(row, "auditedDecreaseAmount", "decreaseAmount")
                ),
                "_g7_closing_cost": _money(
                    _first(row, "auditedClosingAmount", "closingAmount")
                ),
            })
        else:
            equity_by_name[name] = _merge_non_empty(common, {
                "open_ratio": _ratio_to_percent(
                    _first(row, "auditedOpeningRatio", "openingRatio"),
                    scale="fraction",
                ),
                "open_amount": _money(
                    _first(row, "auditedOpeningAmount", "openingAmount")
                ),
                "add_ratio": _ratio_to_percent(
                    _first(row, "auditedIncreaseRatio", "increaseRatio"),
                    scale="fraction",
                ),
                "add_cost": _money(_first(row, "auditedCostIncrease", "costIncrease")),
                "add_income_adj": _money(
                    _first(row, "auditedProfitLoss", "profitLossAdjustment")
                ),
                "add_oci": _money(
                    _first(row, "auditedOci", "otherComprehensiveIncome")
                ),
                "add_other_equity": _money(
                    _first(row, "auditedOtherEquity", "otherEquityChange")
                ),
                "reduce_ratio": _ratio_to_percent(
                    _first(row, "auditedDecreaseRatio", "decreaseRatio"),
                    scale="fraction",
                ),
                "reduce_cost": _money(
                    _first(row, "auditedCostDecrease", "costDecrease")
                ),
                "reduce_dividend": _money(
                    _first(row, "auditedDividend", "dividendReceived")
                ),
                "_g7_closing_amount": _money(
                    _first(row, "auditedClosingAmount", "closingAmount")
                ),
            })

    enrichments = (
        ("G7-8-rows", "G7-8"),
        ("G7-9-rows", "G7-9"),
        ("G7-10-rows", "G7-10"),
        ("G7-12-rows", "G7-12"),
        ("G7-13-rows", "G7-13"),
        ("G7-14-equity-method-calc", "G7-14"),
        ("G7-14-rows", "G7-14"),
        ("G7-15-rows", "G7-15"),
        ("G7-15-internal-transaction", "G7-15"),
        ("G7-16-rows", "G7-16"),
        ("G7-17-rows", "G7-17"),
        ("G7-17-impairment-test", "G7-17"),
        ("G7-5-rows", "G7-5"),
        ("G7-6-rows", "G7-6"),
    )
    for key, source_sheet in enrichments:
        for row in _rows(payloads.get(key)):
            name = _name(row)
            if not name:
                continue
            target = equity_by_name.get(name) or cost_by_name.get(name)
            if not target:
                continue
            sources_used.add(source_sheet)
            if source_sheet in {"G7-8", "G7-9", "G7-13"}:
                initial_cost = _money(_first(
                    row, "initialInvestmentCost", "initialCost", "consideration"
                ))
                if initial_cost is not None:
                    target["add_cost"] = target.get("add_cost") or initial_cost
                target[f"_g7_{source_sheet.lower().replace('-', '_')}"] = deepcopy(row)
            elif source_sheet == "G7-10":
                section = str(row.get("section") or "")
                if section == "dividend":
                    # 实际入账优先；否则应享股利（新模型字段）
                    dividend = _money(_first(
                        row,
                        "recordedDividend",
                        "entitledDividend",
                        "income",
                        "dividendIncome",
                        "cashDividend",
                        "declaredDividend",
                    ))
                    if dividend is not None:
                        if target is cost_by_name.get(name):
                            target["current_dividend"] = dividend
                        else:
                            target["reduce_dividend"] = dividend
                target["_g7_g7_10"] = deepcopy(row)
            elif source_sheet == "G7-12":
                info = info_by_name.get(name)
                if info:
                    info.update({
                        "disposal_date": row.get("disposalDate") or "",
                        "disposal_amount": _money(
                            _first(row, "consideration", "disposalPrice")
                        ),
                        "disposal_ratio": _ratio_to_percent(
                            row.get("disposalRatio"), scale="fraction"
                        ),
                        "_g7_g7_12": deepcopy(row),
                    })
            elif source_sheet == "G7-14":
                target.update({
                    "add_income_adj": _money(
                        _first(row, "equityShare", "confirmedIncome")
                    ),
                    "add_oci": _money(_first(row, "ociShare", "confirmedOci")),
                    "add_other_equity": _money(
                        _first(row, "otherEquityShare", "confirmedOtherEquity")
                    ),
                    "reduce_dividend": _money(row.get("dividendDistributed")),
                    "_g7_adjusted_net_profit": _money(row.get("adjustedNetProfit")),
                    "_g7_audited_net_assets": _money(row.get("auditedNetAssets")),
                    "_g7_goodwill": _money(row.get("goodwill")),
                    "_g7_unexplained_variance": _money(row.get("unexplainedVariance")),
                })
            elif source_sheet == "G7-17":
                # 减值金额作为本期增加减值（期初/期末累计需人工确认，不自动拆分）
                impairment = _money(row.get("impairmentAmount"))
                if impairment is not None:
                    target["add_impairment"] = impairment
                target["_g7_recoverable_amount"] = _money(row.get("recoverableAmount"))
                target["_g7_impairment_note"] = "本期增加减值（来自G7-17，未拆期初/累计）"
            else:
                target[f"_g7_{source_sheet.lower().replace('-', '_')}"] = deepcopy(row)

    # G7-10 股比变动 → 基本信息标记（复杂 share_change 矩阵仅出建议）
    enrich_info_from_g710(info_by_name, payloads, resolve, unresolved, ambiguous)
    if any(
        str(r.get("section") or "") in {"nci", "partialDisposal"}
        for r in _rows(payloads.get("G7-10-rows"))
    ):
        sources_used.add("G7-10")

    # G7-14 净资产调整 → net_asset 矩阵
    na_adjustments = extract_net_asset_adjustments(payloads)
    if na_adjustments:
        sources_used.add("G7-14")
    net_asset_payload = build_net_asset_payload(na_adjustments, resolve)
    suggestions = collect_all_suggestions(payloads, resolve)
    for sheet in {s.get("source_sheet") for s in suggestions if s.get("source_sheet")}:
        sources_used.add(str(sheet))

    targets = {
        "info": list(info_by_name.values()),
        "cost": list(cost_by_name.values()),
        "equity_inv": list(equity_by_name.values()),
        "net_asset": [net_asset_payload] if net_asset_payload.get("company_order") else [],
    }
    importable = {
        sheet: (
            [row for row in rows if row.get("company_code")]
            if sheet in ROW_SHEETS
            else list(rows)
        )
        for sheet, rows in targets.items()
    }
    return {
        "targets": targets,
        "importable": importable,
        "suggestions": suggestions,
        "skipped_net_asset_fields": net_asset_payload.get("skipped_fields") or [],
        "unresolved_companies": sorted(unresolved),
        "ambiguous_companies": sorted(ambiguous),
        "sources_used": sorted(sources_used),
        "counts": {
            sheet: {
                "candidate": (
                    len(net_asset_payload.get("company_order") or [])
                    if sheet == "net_asset"
                    else len(targets[sheet])
                ),
                "importable": (
                    len(net_asset_payload.get("company_order") or [])
                    if sheet == "net_asset"
                    else len(importable[sheet])
                ),
            }
            for sheet in TARGET_SHEETS
        },
    }


def merge_target_rows(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    """按 company_code 幂等合并；默认只填空值并刷新 G7 provenance。"""
    result = deepcopy(existing)
    positions = {
        str(row.get("company_code")): index
        for index, row in enumerate(result)
        if isinstance(row, dict) and row.get("company_code")
    }
    for source in incoming:
        code = str(source.get("company_code") or "")
        if not code:
            continue
        if code not in positions:
            positions[code] = len(result)
            result.append(deepcopy(source))
            continue
        target = result[positions[code]]
        for key, value in source.items():
            if key == "_source" or key.startswith("_g7_"):
                target[key] = deepcopy(value)
            elif overwrite or target.get(key) in (None, ""):
                if value not in (None, ""):
                    target[key] = deepcopy(value)
    return result


async def load_g7_linkage_context(
    db: AsyncSession, project_id: UUID, year: int
) -> dict[str, Any]:
    project_result = await db.execute(
        text("SELECT audit_year FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )
    project = project_result.fetchone()
    if not project:
        raise ValueError("项目不存在")
    if project.audit_year and int(project.audit_year) != year:
        raise ValueError(f"G7 项目年度为 {project.audit_year}，与合并年度 {year} 不一致")

    wp_result = await db.execute(
        text("""
            SELECT wp.id
            FROM working_paper wp
            JOIN wp_index wi ON wi.id = wp.wp_index_id
            WHERE wp.project_id = :pid
              AND wi.wp_code = 'G7'
              AND COALESCE(wp.is_deleted, false) = false
              AND COALESCE(wi.is_deleted, false) = false
            ORDER BY wp.updated_at DESC NULLS LAST, wp.id
        """),
        {"pid": str(project_id)},
    )
    wp_rows = wp_result.fetchall()
    if len(wp_rows) > 1:
        raise G7LinkageConfigError(
            f"项目存在 {len(wp_rows)} 个 G7 工作底稿实例，请保留唯一实例后再联动"
        )
    if not wp_rows:
        return {
            "wp_id": None,
            "payloads": {},
            "item_versions": {},
            "updated_at": None,
            "companies": [],
        }

    wp = wp_rows[0]
    response_result = await db.execute(
        text("""
            SELECT item_id, conclusion, remark, updated_at
            FROM checklist_responses
            WHERE wp_id = :wp_id AND item_id LIKE 'G7-%'
        """),
        {"wp_id": str(wp.id)},
    )
    payloads: dict[str, Any] = {}
    item_versions: dict[str, str] = {}
    latest = None
    for row in response_result.fetchall():
        if row.item_id not in SOURCE_KEYS:
            continue
        payloads[row.item_id] = _json_value(row.conclusion) or _json_value(row.remark)
        if row.updated_at:
            item_versions[row.item_id] = row.updated_at.isoformat()
            if latest is None or row.updated_at > latest:
                latest = row.updated_at

    company_result = await db.execute(
        text("""
            SELECT company_code, company_name, parent_code
            FROM companies
            WHERE project_id = :pid AND COALESCE(is_active, true) = true
            UNION
            SELECT company_code, client_name, parent_company_code
            FROM projects
            WHERE (id = :pid OR parent_project_id = :pid OR ultimate_company_code = (
                SELECT company_code FROM projects WHERE id = :pid
            )) AND company_code IS NOT NULL
        """),
        {"pid": str(project_id)},
    )
    companies = [
        {
            "company_code": row.company_code,
            "company_name": row.company_name,
            "parent_code": row.parent_code,
        }
        for row in company_result.fetchall()
        if row.company_code
    ]
    return {
        "wp_id": str(wp.id),
        "payloads": payloads,
        "item_versions": item_versions,
        "updated_at": latest.isoformat() if latest else None,
        "companies": companies,
    }


def assert_expected_versions(
    current: dict[str, str],
    expected: dict[str, str] | None,
) -> None:
    """导入前校验源 checklist 版本；不一致则要求重新预览。"""
    if not expected:
        return
    stale = [
        key
        for key, version in expected.items()
        if current.get(key) != version
    ]
    if stale:
        raise G7LinkageConflictError(
            "G7 源数据已变更，请重新预览后再导入",
            stale_keys=sorted(stale),
        )


async def _load_existing_sheet_rows(
    db: AsyncSession, project_id: UUID, year: int, sheet_key: str
) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT data FROM consol_worksheet_data
            WHERE project_id = :pid AND year = :year AND sheet_key = :sheet
        """),
        {"pid": str(project_id), "year": year, "sheet": sheet_key},
    )
    row = result.fetchone()
    if not row or not isinstance(row.data, dict):
        return []
    rows = row.data.get("rows")
    return rows if isinstance(rows, list) else []


async def _load_scope_company_order(
    db: AsyncSession, project_id: UUID, year: int
) -> list[str]:
    result = await db.execute(
        text("""
            SELECT company_code FROM consol_scope
            WHERE project_id = :pid AND year = :year
              AND COALESCE(is_deleted, false) = false
              AND COALESCE(is_included, true) = true
              AND company_code IS NOT NULL
            ORDER BY company_name NULLS LAST, company_code
        """),
        {"pid": str(project_id), "year": year},
    )
    return [str(r.company_code) for r in result.fetchall() if r.company_code]


async def mark_consol_linkage_stale_from_g7(
    db: AsyncSession,
    project_id: UUID,
    *,
    year: int | None = None,
    touched_keys: list[str] | None = None,
) -> int:
    """G7 源 checklist 变更后，标记已联动过的合并底稿为过期。"""
    keys = [k for k in (touched_keys or []) if k in SOURCE_KEYS]
    if touched_keys is not None and not keys:
        return 0
    params: dict[str, Any] = {"pid": str(project_id), "now": datetime.now(timezone.utc)}
    year_clause = ""
    if year is not None:
        year_clause = "AND year = :year"
        params["year"] = int(year)
    result = await db.execute(
        text(f"""
            UPDATE consol_worksheet_data
            SET data = jsonb_set(data, '{{_g7_linkage,stale}}', 'true'::jsonb, true),
                updated_at = :now
            WHERE project_id = :pid
              {year_clause}
              AND data ? '_g7_linkage'
        """),
        params,
    )
    return int(result.rowcount or 0)


async def load_linkage_stale_state(
    db: AsyncSession, project_id: UUID, year: int
) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT sheet_key, data
            FROM consol_worksheet_data
            WHERE project_id = :pid AND year = :year
              AND data ? '_g7_linkage'
        """),
        {"pid": str(project_id), "year": year},
    )
    stale_sheets: list[str] = []
    for row in result.fetchall():
        meta = row.data.get("_g7_linkage") if isinstance(row.data, dict) else None
        if isinstance(meta, dict) and meta.get("stale") is True:
            stale_sheets.append(str(row.sheet_key))
    return {
        "linkage_stale": bool(stale_sheets),
        "stale_sheets": sorted(stale_sheets),
    }


async def preview_g7_linkage(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    explicit_mappings: dict[str, str] | None = None,
) -> dict[str, Any]:
    context = await load_g7_linkage_context(db, project_id, year)
    result = build_linkage_candidates(
        context["payloads"],
        {},
        explicit_mappings,
        companies=context["companies"],
    )
    existing_sheets: dict[str, list[dict[str, Any]]] = {}
    for sheet in ROW_SHEETS:
        existing_sheets[sheet] = await _load_existing_sheet_rows(
            db, project_id, year, sheet
        )
    field_diffs = build_field_diffs(
        existing_sheets, result["importable"], overwrite=False
    )
    stale_state = await load_linkage_stale_state(db, project_id, year)
    result.update({
        "source_wp_id": context["wp_id"],
        "source_updated_at": context["updated_at"],
        "item_versions": context["item_versions"],
        "available_companies": context["companies"],
        "field_diffs": field_diffs,
        "diff_summary": {
            "added": sum(1 for d in field_diffs if d["status"] == "added"),
            "changed": sum(1 for d in field_diffs if d["status"] == "changed"),
            "conflict": sum(1 for d in field_diffs if d["status"] == "conflict"),
            "unchanged": sum(1 for d in field_diffs if d["status"] == "unchanged"),
        },
        **stale_state,
    })
    return result


async def import_g7_linkage(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    explicit_mappings: dict[str, str] | None = None,
    sheet_keys: list[str] | None = None,
    overwrite: bool = False,
    expected_versions: dict[str, str] | None = None,
    selected_diffs: list[dict[str, str]] | None = None,
    apply_suggestion_ids: list[str] | None = None,
) -> dict[str, Any]:
    context = await load_g7_linkage_context(db, project_id, year)
    assert_expected_versions(context["item_versions"], expected_versions)

    preview = build_linkage_candidates(
        context["payloads"],
        {},
        explicit_mappings,
        companies=context["companies"],
    )
    preview.update({
        "source_wp_id": context["wp_id"],
        "source_updated_at": context["updated_at"],
        "item_versions": context["item_versions"],
    })

    selected = [key for key in (sheet_keys or list(ROW_SHEETS)) if key in TARGET_SHEETS]
    now = datetime.now(timezone.utc)
    imported: dict[str, int] = {}
    scope_synced = 0
    suggestions_applied = 0

    # selected_diffs 为 None：整表填空合并；为 list：仅写入勾选字段
    selected_by_sheet: dict[str, set[tuple[str, str]]] | None = None
    if selected_diffs is not None:
        selected_by_sheet = {}
        for item in selected_diffs:
            sheet = str(item.get("sheet_key") or "")
            identity = str(item.get("identity") or "")
            field = str(item.get("field") or "")
            if not sheet or not identity or not field:
                continue
            selected_by_sheet.setdefault(sheet, set()).add((identity, field))

    scope_order = await _load_scope_company_order(db, project_id, year)

    for sheet_key in selected:
        current_result = await db.execute(
            text("""
                SELECT data FROM consol_worksheet_data
                WHERE project_id = :pid AND year = :year AND sheet_key = :sheet
            """),
            {"pid": str(project_id), "year": year, "sheet": sheet_key},
        )
        current_row = current_result.fetchone()
        current_data = (
            current_row.data
            if current_row and isinstance(current_row.data, dict)
            else {}
        )
        current_rows = (
            current_data.get("rows")
            if isinstance(current_data.get("rows"), list)
            else []
        )

        company_order_meta: list[str] | None = None
        if sheet_key == "net_asset":
            incoming_list = preview["importable"].get("net_asset") or []
            if not incoming_list:
                imported[sheet_key] = 0
                continue
            incoming = incoming_list[0]
            # 有合并范围时严格按范围列序写入，不自动新增联营/合营列
            if scope_order:
                company_order = list(scope_order)
            else:
                company_order = [str(c) for c in (incoming.get("company_order") or [])]
            merged = merge_net_asset_rows(
                current_rows, incoming, company_order, overwrite=overwrite
            )
            company_order_meta = company_order
            imported[sheet_key] = sum(
                1
                for code in (incoming.get("company_order") or [])
                if str(code) in set(company_order)
            )
        else:
            incoming_rows = preview["importable"].get(sheet_key) or []
            if selected_by_sheet is not None:
                merged = apply_selected_diffs(
                    current_rows,
                    incoming_rows,
                    selected_by_sheet.get(sheet_key, set()),
                )
            else:
                merged = merge_target_rows(
                    current_rows, incoming_rows, overwrite=overwrite
                )
            imported[sheet_key] = len(incoming_rows)

        next_data = {
            **current_data,
            "rows": merged,
            "_g7_linkage": {
                "source_wp_id": preview["source_wp_id"],
                "source_updated_at": preview["source_updated_at"],
                "item_versions": preview["item_versions"],
                "imported_at": now.isoformat(),
                "overwrite": overwrite,
                "sources": preview["sources_used"],
                "stale": False,
            },
        }
        if company_order_meta is not None:
            next_data["company_order"] = company_order_meta
        await db.execute(
            text("""
                INSERT INTO consol_worksheet_data
                    (id, project_id, year, sheet_key, data, created_at, updated_at)
                VALUES
                    (:id, :pid, :year, :sheet, CAST(:data AS jsonb), :now, :now)
                ON CONFLICT (project_id, year, sheet_key)
                DO UPDATE SET data = CAST(:data AS jsonb), updated_at = :now
            """),
            {
                "id": str(uuid4()),
                "pid": str(project_id),
                "year": year,
                "sheet": sheet_key,
                "data": json.dumps(next_data, ensure_ascii=False),
                "now": now,
            },
        )

    # 仅在用户勾选基本信息表时同步合并范围；已有记录不覆盖 is_included。
    if "info" in selected:
        for row in preview["importable"]["info"]:
            group = row.get("_g7_group_type")
            if group not in {"subsidiary", "associate", "joint_venture"}:
                continue
            ownership = row.get("common_ratio") or row.get("non_common_ratio")
            scope_values = {
                "pid": str(project_id),
                "year": year,
                "code": row["company_code"],
                "name": row["company_name"],
                "ctype": group,
                "ratio": ownership,
                "included": group == "subsidiary",
                "reason": group,
                "change": (
                    "new_inclusion"
                    if row.get("_g7_newly_consolidated") == "是"
                    else "none"
                ),
                "now": now,
            }
            scope_result = await db.execute(
                text("""
                    SELECT id, is_included FROM consol_scope
                    WHERE project_id = :pid AND year = :year AND company_code = :code
                      AND COALESCE(is_deleted, false) = false
                    ORDER BY updated_at DESC LIMIT 1
                """),
                scope_values,
            )
            scope = scope_result.fetchone()
            if scope:
                await db.execute(
                    text("""
                        UPDATE consol_scope SET
                            company_name = COALESCE(NULLIF(company_name, ''), :name),
                            company_type = COALESCE(company_type, :ctype),
                            ownership_ratio = COALESCE(ownership_ratio, :ratio),
                            inclusion_reason = COALESCE(inclusion_reason, :reason),
                            updated_at = :now,
                            is_deleted = false
                        WHERE id = :scope_id
                    """),
                    {**scope_values, "scope_id": str(scope.id)},
                )
            else:
                await db.execute(
                    text("""
                        INSERT INTO consol_scope
                            (id, project_id, year, company_code, company_name, company_type,
                             ownership_ratio, is_included, inclusion_reason, scope_change_type,
                             created_at, updated_at, is_deleted)
                        VALUES
                            (:id, :pid, :year, :code, :name, :ctype,
                             :ratio, :included, :reason, :change, :now, :now, false)
                    """),
                    {**scope_values, "id": str(uuid4())},
                )
            scope_synced += 1

    # 商誉/少数股东建议：仅当用户勾选 suggestion id 时写入草稿表
    apply_ids = set(apply_suggestion_ids or [])
    applied_suggestions = [
        s for s in preview.get("suggestions") or [] if s.get("id") in apply_ids
    ]
    if applied_suggestions:
        await db.execute(
            text("""
                INSERT INTO consol_worksheet_data
                    (id, project_id, year, sheet_key, data, created_at, updated_at)
                VALUES
                    (:id, :pid, :year, :sheet, CAST(:data AS jsonb), :now, :now)
                ON CONFLICT (project_id, year, sheet_key)
                DO UPDATE SET data = CAST(:data AS jsonb), updated_at = :now
            """),
            {
                "id": str(uuid4()),
                "pid": str(project_id),
                "year": year,
                "sheet": "g7_suggestions",
                "data": json.dumps({
                    "rows": applied_suggestions,
                    "status": "draft",
                    "note": "G7 建议草稿（商誉/股比变动/调整分录），需人工复核后写入正式表；不得直接当抵消分录",
                    "imported_at": now.isoformat(),
                }, ensure_ascii=False),
                "now": now,
            },
        )
        suggestions_applied = len(applied_suggestions)

    await db.commit()
    return {
        "imported": imported,
        "scope_synced": scope_synced,
        "suggestions_applied": suggestions_applied,
        "unresolved_companies": preview["unresolved_companies"],
        "ambiguous_companies": preview["ambiguous_companies"],
        "source_wp_id": preview["source_wp_id"],
        "source_updated_at": preview["source_updated_at"],
        "item_versions": preview["item_versions"],
    }
