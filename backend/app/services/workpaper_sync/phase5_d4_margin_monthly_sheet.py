# -*- coding: utf-8 -*-
"""D4-7 毛利率分析表双向回写 provider（批次B，同 sheet：动态产品区 + 静态月度区）。

共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。同一受管 sheet 上 **1 dynamic + 1 static** 两区，
正好 D4-9「动态区当 Excel-Table 载体、静态区寄生」架构（静态区无 row_identity，靠固定坐标定位，
被 binding 的受管坐标纳入，不需自己的 Table 锚点）：

  · §二 按产品毛利分析（dynamic，header R18-19 / 数据 R20-25 种子 6 行 / 合计 R26）：
    输入列 A 产品名 / B 数量(本期) / D 收入(本期) / G 成本(本期) / J 数量(上期) / L 收入(上期) /
    O 成本(上期) / W 备注（8 列）；formula 列 C/E/F/H/I(本期派生) + K/M/N/P/Q(上期派生) +
    R/S/T/U/V(变动派生)（15 列 → formula_mask）。行身份 = rowId（前端本轮补 + backfill）。UUID 列 **X**。
    footer marker = `合计`（R26，本区数据正下方）。store `D4-7-products`（行数组）。
  · §一 月度毛利分析（static，R11-15）：唯一输入 = R12 主营收入 B-M(12月) + O12 上期收入 +
    R13 主营成本 B-M(12月) + O13 上期成本 = **26 static cell**；毛利 R14 / 毛利率 R15 / 合计 N /
    变动 P 全 Excel 公式。store `D4-7-monthly` = `{revenue[12],cost[12],priorRevenue,priorCost}`（标量对象）。
  · 审计说明 R27 / 审计结论 R30 / audit-process HTML-only，不入契约。

前端真源：`D4TabMarginMonthly.vue`。§二 ProductRow = {rowId, name, curQty, curRevenue, curCost,
priorQty, priorRevenue, priorCost, remark}；§一 MonthlyData = {revenue[12], cost[12], priorRevenue, priorCost}。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
MANAGED_SHEET_D47: Final[str] = "毛利率分析表D4-7"
SHEET_KEY_D47: Final[str] = "d47-managed"

# ── §二 产品动态区 ──────────────────────────────────────────────────────────
STORE_ITEM_ID_D47_PRODUCTS: Final[str] = "D4-7-products"
TABLE_KEY_PRODUCTS: Final[str] = "d4_7_products"
TEMPLATE_ID_PRODUCTS: Final[str] = "D47PROD"
HEADER_ROW_PRODUCTS: Final[int] = 19
FIRST_ROW_PRODUCTS: Final[int] = 20
LAST_ROW_PRODUCTS: Final[int] = 25
FOOTER_ROW_PRODUCTS: Final[int] = 26
UUID_COL_PRODUCTS: Final[str] = "X"
MANAGED_LAST_COL_PRODUCTS: Final[str] = "W"
FOOTER_MARKER_PRODUCTS: Final[str] = "合计"
#: (store 字段, 列标, value_type, 表头文本)。仅输入列入契约；派生列进 formula_mask。
FIELDS_PRODUCTS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("name", "A", "text", "产品名称"),
    ("curQty", "B", "amount", "本期数量"),
    # C 平均单价 = D/B（formula）
    ("curRevenue", "D", "amount", "本期主营业务收入"),
    # E 结构比 / F 单位成本 / H 毛利 / I 毛利率（formula）
    ("curCost", "G", "amount", "本期主营业务成本"),
    ("priorQty", "J", "amount", "上期数量"),
    # K 平均单价（formula）
    ("priorRevenue", "L", "amount", "上期主营业务收入"),
    # M 结构比 / N 单位成本（formula）
    ("priorCost", "O", "amount", "上期主营业务成本"),
    # P 毛利 / Q 毛利率 / R-V 变动（formula）
    ("remark", "W", "text", "备注"),
)
#: 派生列（本区数据行 R20-25 + 合计行 R26）为 Excel 内部公式，投影不覆盖。
_FORMULA_COLS: Final[tuple[str, ...]] = (
    "C", "E", "F", "H", "I", "K", "M", "N", "P", "Q", "R", "S", "T", "U", "V",
)
FORMULA_MASK_PRODUCTS: Final[tuple[str, ...]] = tuple(
    f"{col}{r}"
    for r in range(FIRST_ROW_PRODUCTS, FOOTER_ROW_PRODUCTS + 1)
    for col in _FORMULA_COLS
) + tuple(f"{col}{FOOTER_ROW_PRODUCTS}" for col in ("B", "D", "G", "J", "L", "O"))  # 合计行 SUM

# ── §一 月度静态区 ──────────────────────────────────────────────────────────
STORE_ITEM_ID_D47_MONTHLY: Final[str] = "D4-7-monthly"
TABLE_KEY_MONTHLY: Final[str] = "d4_7_monthly"
REVENUE_ROW: Final[int] = 12
COST_ROW: Final[int] = 13
PRIOR_COL: Final[str] = "O"
#: 12 月列 B..M。
_MONTH_COLS: Final[tuple[str, ...]] = ("B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M")
#: §一 合计 N / 变动 P / 毛利 R14 全行 / 毛利率 R15 全行为 Excel 公式。
FORMULA_MASK_MONTHLY: Final[tuple[str, ...]] = (
    (f"N{REVENUE_ROW}", f"P{REVENUE_ROW}", f"N{COST_ROW}", f"P{COST_ROW}")
    + tuple(f"{c}14" for c in (*_MONTH_COLS, "N", "O", "P"))
    + tuple(f"{c}15" for c in (*_MONTH_COLS, "N", "O"))
)


def _snake(field: str) -> str:
    import re

    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET_D47}!{cell}"


# ═══════════════════════════════════════════════════════════════════════════
# §二 产品动态区
# ═══════════════════════════════════════════════════════════════════════════
def _prod_stable_key(field: str, identity: str = "{row_uuid}") -> str:
    return f"{TABLE_KEY_PRODUCTS}/{identity}/{_snake(field)}"


def _products_table_payload() -> dict[str, Any]:
    field_specs = [
        {
            "stable_field_key": _prod_stable_key(f[0]),
            "json_pointer": f"/{{row_uuid}}/{f[0]}",
            "column_key": _snake(f[0]),
            "cell": {"column": f[1], "row_from": "row_identity"},
            "mode": "editable",
            "value_type": f[2],
            "source_ref": _src(f"{f[1]}{FIRST_ROW_PRODUCTS}"),
            "header_source_ref": _src(f"{f[1]}{HEADER_ROW_PRODUCTS}"),
            "store_item_id": STORE_ITEM_ID_D47_PRODUCTS,
            "header_text": f[3],
        }
        for f in FIELDS_PRODUCTS
    ]
    return {
        "table_key": TABLE_KEY_PRODUCTS,
        "anchor": f"A{FIRST_ROW_PRODUCTS - 1}",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": "/*/rowId"},
        "delete_policy": "tombstone",
        "uuid_col": UUID_COL_PRODUCTS,
        "footer_anchor": {"marker": FOOTER_MARKER_PRODUCTS, "search_column": "A", "carries_total_formula": True},
        "formula_mask": list(FORMULA_MASK_PRODUCTS),
        "fields": field_specs,
    }


def _decode(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        return json.loads(payload) if payload.strip() else []
    return payload


def _prod_rows(payload: Any) -> list[tuple[str, Mapping[str, Any]]]:
    value = _decode(payload)
    if not isinstance(value, list):
        return []  # legacy 容差：非数组视为空，不打挂全 entry
    out: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{STORE_ITEM_ID_D47_PRODUCTS}[{ordinal}] 不是对象")
        rid = str(row.get("rowId") or "").strip()
        if not rid:
            raise ValueError(f"{STORE_ITEM_ID_D47_PRODUCTS}[{ordinal}] 缺少 rowId")
        if rid in seen:
            raise ValueError(f"{STORE_ITEM_ID_D47_PRODUCTS} 行身份 {rid!r} 重复")
        seen.add(rid)
        out.append((rid, row))
    return out


def build_products_projection(payload: Any, *, contract, limits=None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _prod_rows(payload):
        row_keys.append(identity)
        for field, _col, _vt, _label in FIELDS_PRODUCTS:
            sk = _prod_stable_key(field, identity)
            spec = contract.field_by_stable_key(_prod_stable_key(field))
            values[sk] = FieldValue(stable_key=sk, value=row.get(field), value_type=spec.value_type, mode=spec.mode, row_key=identity)
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={TABLE_KEY_PRODUCTS: tuple(row_keys)},
    )


def merge_projection_into_products(*, projection, base_payload) -> list[dict[str, Any]]:
    base = _decode(base_payload)
    container = base if isinstance(base, list) else []
    rows = [(str(r.get("rowId")), dict(r)) for r in container if isinstance(r, Mapping) and r.get("rowId")]
    by_id = {i: r for i, r in rows}
    order = [i for i, _ in rows]
    snake_to_field = {_snake(f[0]): f[0] for f in FIELDS_PRODUCTS}
    prefix = TABLE_KEY_PRODUCTS + "/"
    for sk in projection.stable_keys():
        s = str(sk)
        if not s.startswith(prefix):
            continue
        fv = projection.get(sk)
        identity = getattr(fv, "row_key", None)
        if not identity:
            continue
        parts = s.split("/")
        if len(parts) < 3:
            continue
        field = snake_to_field.get(parts[2])
        target = by_id.get(identity)
        if field is None or target is None:
            continue
        target[field] = getattr(fv, "value", None)
    return [by_id[i] for i in order]


# ═══════════════════════════════════════════════════════════════════════════
# §一 月度静态区（无 row_identity，固定坐标；随产品区 binding 一起被纳入受管坐标）
# ═══════════════════════════════════════════════════════════════════════════
def _monthly_stable_key(field: str) -> str:
    return f"{TABLE_KEY_MONTHLY}/{field}"


#: (stable 字段, 列标, 静态行号, json_pointer)。revenue[0..11]/cost[0..11] + priorRevenue/priorCost。
def _monthly_field_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for idx, col in enumerate(_MONTH_COLS):
        specs.append({"field": f"revenue_{idx}", "column": col, "static_row": REVENUE_ROW, "ptr": f"/revenue/{idx}"})
        specs.append({"field": f"cost_{idx}", "column": col, "static_row": COST_ROW, "ptr": f"/cost/{idx}"})
    specs.append({"field": "prior_revenue", "column": PRIOR_COL, "static_row": REVENUE_ROW, "ptr": "/priorRevenue"})
    specs.append({"field": "prior_cost", "column": PRIOR_COL, "static_row": COST_ROW, "ptr": "/priorCost"})
    return specs


_MONTHLY_SPECS: Final[list[dict[str, Any]]] = _monthly_field_specs()


def _monthly_table_payload() -> dict[str, Any]:
    fields = []
    for s in _MONTHLY_SPECS:
        fields.append({
            "stable_field_key": _monthly_stable_key(s["field"]),
            "json_pointer": s["ptr"],
            "column_key": s["field"],
            "cell": {"column": s["column"], "row_from": s["static_row"]},
            "mode": "editable",
            "value_type": "amount",
            "source_ref": _src(f"{s['column']}{s['static_row']}"),
            "header_source_ref": _src(f"{s['column']}11"),
            "store_item_id": STORE_ITEM_ID_D47_MONTHLY,
            "header_text": "月度",
        })
    # static 表：无 row_identity / delete_policy / footer_anchor（参 D4-9 totals / D4-20 summary）。
    return {
        "table_key": TABLE_KEY_MONTHLY,
        "anchor": "A11",
        "header_rows": 1,
        "formula_mask": list(FORMULA_MASK_MONTHLY),
        "fields": fields,
    }


def _decode_obj(payload: Any) -> dict[str, Any]:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload) if payload.strip() else {}
    return payload if isinstance(payload, Mapping) else {}


def _monthly_value(data: Mapping[str, Any], field: str) -> Any:
    if field.startswith("revenue_"):
        arr = data.get("revenue")
        idx = int(field.split("_")[1])
        return arr[idx] if isinstance(arr, list) and idx < len(arr) else 0
    if field.startswith("cost_"):
        arr = data.get("cost")
        idx = int(field.split("_")[1])
        return arr[idx] if isinstance(arr, list) and idx < len(arr) else 0
    if field == "prior_revenue":
        return data.get("priorRevenue")
    if field == "prior_cost":
        return data.get("priorCost")
    return None


def build_monthly_projection(payload: Any, *, contract, limits=None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    data = _decode_obj(payload)
    values: dict[str, FieldValue] = {}
    for s in _MONTHLY_SPECS:
        sk = _monthly_stable_key(s["field"])
        spec = contract.field_by_stable_key(sk)
        value = _monthly_value(data, s["field"])
        # amount 缺失归一为 0（与 materialize 空金额格反读一致，防 RoundtripEquivalenceError）
        if value is None:
            value = 0
        values[sk] = FieldValue(stable_key=sk, value=value, value_type=spec.value_type, mode=spec.mode, row_key=None)
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={TABLE_KEY_MONTHLY: ()},
    )


def merge_projection_into_monthly(*, projection, base_payload) -> dict[str, Any]:
    data = _decode_obj(base_payload)
    out = dict(data)
    revenue = list(out.get("revenue")) if isinstance(out.get("revenue"), list) else [0] * 12
    cost = list(out.get("cost")) if isinstance(out.get("cost"), list) else [0] * 12
    while len(revenue) < 12:
        revenue.append(0)
    while len(cost) < 12:
        cost.append(0)
    prefix = TABLE_KEY_MONTHLY + "/"
    for sk in projection.stable_keys():
        s = str(sk)
        if not s.startswith(prefix):
            continue
        field = s[len(prefix):]
        val = getattr(projection.get(sk), "value", None)
        if field.startswith("revenue_"):
            revenue[int(field.split("_")[1])] = val
        elif field.startswith("cost_"):
            cost[int(field.split("_")[1])] = val
        elif field == "prior_revenue":
            out["priorRevenue"] = val
        elif field == "prior_cost":
            out["priorCost"] = val
    out["revenue"] = revenue
    out["cost"] = cost
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 对外 API
# ═══════════════════════════════════════════════════════════════════════════
def mapping_digest_d47() -> str:
    payload = json.dumps(
        {
            "sheet": MANAGED_SHEET_D47,
            "products": [f[0] for f in FIELDS_PRODUCTS],
            "products_uuid": UUID_COL_PRODUCTS,
            "monthly": [s["field"] for s in _MONTHLY_SPECS],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d47() -> dict[str, Any]:
    return {
        "sheet_key": SHEET_KEY_D47,
        "excel_name": MANAGED_SHEET_D47,
        "template_id": "D47",
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [_products_table_payload(), _monthly_table_payload()],
    }


def instrumentation_specs_d47(*, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH) -> tuple[Any, ...]:
    """仅 dynamic 区需要 instrumentation（static 区无 row identity，随本 sheet binding 纳入受管坐标）。"""
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return (
        ExcelInstrumentationSpec(
            entry_id=entry_id,
            template_id=TEMPLATE_ID_PRODUCTS,
            template_relative_path=template_relative_path,
            managed_sheet=MANAGED_SHEET_D47,
            first_data_row=FIRST_ROW_PRODUCTS,
            last_data_row=LAST_ROW_PRODUCTS,
            footer_row=FOOTER_ROW_PRODUCTS,
            managed_last_col=MANAGED_LAST_COL_PRODUCTS,
            uuid_col=UUID_COL_PRODUCTS,
            table_name=f"GT_{TEMPLATE_ID_PRODUCTS}_ROWS",
            sheet_key=SHEET_KEY_D47,
        ),
    )


def build_store_projection_d47(payloads: Mapping[str, Any], *, contract, limits=None):
    """两区合并投影。payloads = {store_item_id: payload}。"""
    from app.services.workpaper_sync.adapters.base import Projection

    prod = build_products_projection(payloads.get(STORE_ITEM_ID_D47_PRODUCTS, []), contract=contract, limits=limits)
    monthly = build_monthly_projection(payloads.get(STORE_ITEM_ID_D47_MONTHLY, {}), contract=contract, limits=limits)
    values = dict(prod.values)
    values.update(monthly.values)
    row_keys = {**dict(prod.row_keys), **dict(monthly.row_keys)}
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys=row_keys,
    )


def merge_projection_into_d47_stores(*, projection, base_by_item: Mapping[str, Any]) -> dict[str, Any]:
    """把投影合并回 2 个 store item。返回 {store_item_id: 新载荷}。"""
    return {
        STORE_ITEM_ID_D47_PRODUCTS: merge_projection_into_products(
            projection=projection, base_payload=base_by_item.get(STORE_ITEM_ID_D47_PRODUCTS, [])
        ),
        STORE_ITEM_ID_D47_MONTHLY: merge_projection_into_monthly(
            projection=projection, base_payload=base_by_item.get(STORE_ITEM_ID_D47_MONTHLY, {})
        ),
    }


def store_item_ids_d47() -> tuple[str, ...]:
    return (STORE_ITEM_ID_D47_PRODUCTS, STORE_ITEM_ID_D47_MONTHLY)
