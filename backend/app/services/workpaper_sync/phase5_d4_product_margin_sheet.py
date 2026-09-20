# -*- coding: utf-8 -*-
"""D4-8 重要产品毛利分析表双向回写 provider（静态受管区，spec workpaper-sync-static-cell-sheet-writeback）。

共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。**static-cell 块矩阵**模型（无 UUID / 无动态行 /
无 Excel Table），与 D4-33 同分类，靠 workbook-scope definedName 锚定（instrumentation 注入）。

几何（openpyxl census 实读 `D/D4 收入底稿.xlsx` sheet `重要产品毛利分析D4-8`，A1:X40）：
  · 固定产品块（产品A R12-31，产品B「（略）」占位 R32），每块：header R13-15（3 行两级表头）+
    固定 12 月行 R16-27 + 合计 R28 + 同行业A/B/行业平均 R29-31。
  · 月行 R16-27 输入 12 列：本期 B销量/C单价/D金额/E成本销量/F单位成本/G成本金额 + 上期 J/K/L/M/N/O；
    公式列 H/I/P/Q/R/S/T/U/V/W（毛利/毛利率/上期毛利/变动分析）→ formula_mask。
  · 同行业 R29-31 输入同 12 列（对比数据，人工录入）。
  · 受管输入 = 产品A（slot0）：12 月 × 12 列（R16-27）+ 3 同行业行 × 12 列（R29-31）= 180 static cell。

🔴 **限制**：模板只预画 1 个完整产品块（产品A）。前端 `D4-8-products` 产品**动态计数**（逐产品切换
  视图 activeProductIdx），本 provider 只受管**第 1 个产品（slot0）**位置映射到产品A块；第 2+ 产品
  无模板块 → HTML-only（同 D4-33 第 4+ 业务类型）。

前端真源：`D4TabProductMargin.vue` + store `D4-8-products` = `ProductData[]`，每 product =
  `{name, months[12], priorMonths[12], industry[3]}`，month/industry = {revQty,revPrice,revAmt,
  costQty,costPrice,costAmt}。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
MANAGED_SHEET_D48: Final[str] = "重要产品毛利分析D4-8"
TEMPLATE_ID_D48: Final[str] = "D48"
SHEET_KEY_D48: Final[str] = "d48-managed"
STORE_ITEM_ID_D48: Final[str] = "D4-8-products"
TABLE_KEY_D48: Final[str] = "d4_8_matrix"

HEADER_ROW_D48: Final[int] = 13
FIRST_MONTH_ROW_D48: Final[int] = 16   # 1 月
LAST_MONTH_ROW_D48: Final[int] = 27    # 12 月
MONTH_COUNT: Final[int] = 12
#: 同行业对比 3 行（同 6+6 输入列）。
INDUSTRY_ROWS: Final[tuple[int, ...]] = (29, 30, 31)
TOTAL_ROW_D48: Final[int] = 28

#: 6 个输入字段 → (store 驼峰键, 契约小写键, 本期列, 上期列)。census R15 表头实证映射。
#: revQty B/J · revPrice C/K · revAmt D/L · costQty E/M · costPrice F/N · costAmt G/O
#: 🔴 stable_field_key 只允许小写/数字/_-./{}（contracts.assert_stable_key），故契约键必须小写化；
#:    但 json_pointer / store 写回仍用前端 store 的驼峰字段名（前端真源 ProductData 键），二者分离。
FIELD_COLS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("revQty", "rev_qty", "B", "J"),
    ("revPrice", "rev_price", "C", "K"),
    ("revAmt", "rev_amt", "D", "L"),
    ("costQty", "cost_qty", "E", "M"),
    ("costPrice", "cost_price", "F", "N"),
    ("costAmt", "cost_amt", "G", "O"),
)

#: 契约小写键 → store 驼峰键 反查（merge 侧从 stable_field_key 解析出契约键，回写 store 需驼峰键）。
_CONTRACT_TO_STORE_FIELD: Final[dict[str, str]] = {
    contract_field: store_field for store_field, contract_field, _c, _p in FIELD_COLS
}

#: 静态受管区 workbook-scope definedName 锚点（instrumentation 注入，模板无既有 definedName）。
#: ref 覆盖产品A块 B16:W31（含公式列，受管 cell 由 fields 精确声明）。
DEFINED_NAME_D48: Final[str] = "GT_MANAGED_REGION_D48"
MANAGED_REF_D48: Final[str] = "$B$16:$W$31"


#: formula_mask：公式列 H/I/P/Q/R/S/T/U/V/W（R16-27 + R29-31）+ 合计行 R28 全列 B-W。
def _formula_mask() -> tuple[str, ...]:
    cells: list[str] = []
    formula_cols = ("H", "I", "P", "Q", "R", "S", "T", "U", "V", "W")
    for row in list(range(FIRST_MONTH_ROW_D48, LAST_MONTH_ROW_D48 + 1)) + list(INDUSTRY_ROWS):
        for col in formula_cols:
            cells.append(f"{col}{row}")
    for col in "BCDEFGHIJKLMNOPQRSTUVW":
        cells.append(f"{col}{TOTAL_ROW_D48}")
    return tuple(cells)


FORMULA_MASK_D48: Final[tuple[str, ...]] = _formula_mask()


def formula_mask_cells_d48() -> tuple[str, ...]:
    return FORMULA_MASK_D48


def _month_key(month: int, loc: str, field: str) -> str:
    # loc ∈ {cur, prior}；month 0-11；field ∈ FIELD_COLS keys
    return f"{TABLE_KEY_D48}/m{month}_{loc}/{field}"


def _industry_key(idx: int, loc: str, field: str) -> str:
    # idx 0-2（同行业A/B/平均）；loc ∈ {cur, prior}
    return f"{TABLE_KEY_D48}/ind{idx}_{loc}/{field}"


def mapping_digest_d48() -> str:
    payload = json.dumps(
        {
            "sheet": MANAGED_SHEET_D48,
            "field_cols": FIELD_COLS,
            "months": MONTH_COUNT,
            "first_row": FIRST_MONTH_ROW_D48,
            "industry_rows": INDUSTRY_ROWS,
            "formula_mask": list(FORMULA_MASK_D48),
        },
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fields() -> list[dict[str, Any]]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D48}!{cell}"

    fields: list[dict[str, Any]] = []
    # 月度 12 行 × 本期/上期 × 6 输入字段
    for m in range(MONTH_COUNT):
        row = FIRST_MONTH_ROW_D48 + m
        for store_field, contract_field, cur_col, prior_col in FIELD_COLS:
            for loc, col in (("cur", cur_col), ("prior", prior_col)):
                fields.append(
                    {
                        "stable_field_key": _month_key(m, loc, contract_field),
                        "json_pointer": f"/months/{m}/{loc}/{store_field}",
                        "column_key": f"m{m}_{loc}_{contract_field}",
                        "cell": {"column": col, "row_from": row},
                        "mode": "editable",
                        "value_type": "amount",
                        "source_ref": _src(f"{col}{row}"),
                        "header_source_ref": _src(f"{col}{HEADER_ROW_D48}"),
                        "store_item_id": STORE_ITEM_ID_D48,
                        "header_text": f"{m + 1}月{'本期' if loc == 'cur' else '上期'}{store_field}",
                    }
                )
    # 同行业 3 行 × 本期/上期 × 6 输入字段
    for idx, row in enumerate(INDUSTRY_ROWS):
        for store_field, contract_field, cur_col, prior_col in FIELD_COLS:
            for loc, col in (("cur", cur_col), ("prior", prior_col)):
                fields.append(
                    {
                        "stable_field_key": _industry_key(idx, loc, contract_field),
                        "json_pointer": f"/industry/{idx}/{loc}/{store_field}",
                        "column_key": f"ind{idx}_{loc}_{contract_field}",
                        "cell": {"column": col, "row_from": row},
                        "mode": "editable",
                        "value_type": "amount",
                        "source_ref": _src(f"{col}{row}"),
                        "header_source_ref": _src(f"{col}{HEADER_ROW_D48}"),
                        "store_item_id": STORE_ITEM_ID_D48,
                        "header_text": f"同行业{idx}{'本期' if loc == 'cur' else '上期'}{store_field}",
                    }
                )
    return fields


def sheet_payload_d48() -> dict[str, Any]:
    return {
        "sheet_key": SHEET_KEY_D48,
        "excel_name": MANAGED_SHEET_D48,
        "template_id": TEMPLATE_ID_D48,
        "locator": {"anchor": "defined_name_ref", "defined_name": DEFINED_NAME_D48},
        "region_boundary_locator": {
            "anchor": "defined_name_ref",
            "defined_name": DEFINED_NAME_D48,
            "range": MANAGED_REF_D48,
            "region_kind": "static",
        },
        "tables": [
            {
                "table_key": TABLE_KEY_D48,
                "anchor": f"A{HEADER_ROW_D48}",
                "header_rows": 3,
                "formula_mask": list(FORMULA_MASK_D48),
                "fields": _fields(),
            }
        ],
    }


def static_sheet_payload_d48() -> dict[str, Any]:
    """instrumentation static_sheets 元素（寄生在动态 primary spec 上）。"""
    return {
        "sheet_key": SHEET_KEY_D48,
        "excel_name": MANAGED_SHEET_D48,
        "template_id": TEMPLATE_ID_D48,
        "region_boundary_locator": {
            "anchor": "defined_name_ref",
            "defined_name": DEFINED_NAME_D48,
            "range": MANAGED_REF_D48,
            "region_kind": "static",
        },
        "tables": [{"table_key": TABLE_KEY_D48}],
    }


def static_binding_d48():
    from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME
    from app.services.workpaper_sync.excel_extract import ExcelIdentityBinding

    return ExcelIdentityBinding(
        table_key=TABLE_KEY_D48,
        defined_name=DEFINED_NAME_D48,
        metadata_sheet=GT_SYNC_SHEET_NAME,
    )


def store_item_id_d48() -> str:
    return STORE_ITEM_ID_D48


def _decode(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        return json.loads(payload) if payload.strip() else []
    return payload


def _num(raw: Any) -> Any:
    if raw in (None, ""):
        return 0
    try:
        v = float(raw)
        return int(v) if v == int(v) else v
    except (TypeError, ValueError):
        return 0


def _product0(data: Any) -> Mapping[str, Any] | None:
    """取第 1 个产品（slot0 映射产品A块）；无则 None（第 2+ 产品/空 → HTML-only）。"""
    products = data if isinstance(data, list) else None
    if products and isinstance(products[0], Mapping):
        return products[0]
    return None


def build_store_projection_d48(payload: Any, *, contract, limits=None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    p0 = _product0(_decode(payload))
    months = (p0.get("months") if p0 else None) or []
    prior_months = (p0.get("priorMonths") if p0 else None) or []
    industry = (p0.get("industry") if p0 else None) or []

    def _cell(arr: Any, i: int, field: str) -> Any:
        e = arr[i] if isinstance(arr, list) and i < len(arr) and isinstance(arr[i], Mapping) else {}
        return _num(e.get(field))

    values: dict[str, Any] = {}
    for m in range(MONTH_COUNT):
        for store_field, contract_field, _c, _p in FIELD_COLS:
            for loc, arr in (("cur", months), ("prior", prior_months)):
                sk = _month_key(m, loc, contract_field)
                spec = contract.field_by_stable_key(sk)
                values[sk] = FieldValue(stable_key=sk, value=_cell(arr, m, store_field),
                                        value_type=spec.value_type, mode=spec.mode, row_key=None)
    for idx in range(len(INDUSTRY_ROWS)):
        for store_field, contract_field, _c, _p in FIELD_COLS:
            # 前端 industry 单组（无 cur/prior 区分）→ cur 映射到 industry[idx][store_field]，prior 填 0（模板列存在前端无源）
            for loc in ("cur", "prior"):
                sk = _industry_key(idx, loc, contract_field)
                spec = contract.field_by_stable_key(sk)
                val = _cell(industry, idx, store_field) if loc == "cur" else 0
                values[sk] = FieldValue(stable_key=sk, value=val,
                                        value_type=spec.value_type, mode=spec.mode, row_key=None)
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={TABLE_KEY_D48: ()},
    )


def merge_projection_into_d48_store(*, projection, base_state):
    """把投影合并回 store（ProductData[]），只覆盖第 1 个产品（slot0）的月度/上期/同行业。

    dict/list store：返回 (merged_list, applied, visited) 3-tuple，oo_to_html 走专用块消费
    （不进 rows 4-tuple 循环）。保留第 2+ 产品；industry prior 不回写（前端无字段）。
    """
    data = _decode(base_state)
    products = list(data) if isinstance(data, list) else []
    if not products or not isinstance(products[0], Mapping):
        # 无产品 → 建一个空产品A承接（同前端 defaultProduct 结构，用 store 驼峰键）
        products = [{
            "name": "",
            "months": [{sf: 0 for sf, _cf, _c, _p in FIELD_COLS} for _ in range(MONTH_COUNT)],
            "priorMonths": [{sf: 0 for sf, _cf, _c, _p in FIELD_COLS} for _ in range(MONTH_COUNT)],
            "industry": [{"name": n, **{sf: 0 for sf, _cf, _c, _p in FIELD_COLS}} for n in ("同行业A企业", "同行业B企业", "行业平均水平")],
        }] + products[1:]
    p0 = dict(products[0])
    months = [dict(e) if isinstance(e, Mapping) else {} for e in (p0.get("months") or [])]
    prior = [dict(e) if isinstance(e, Mapping) else {} for e in (p0.get("priorMonths") or [])]
    industry = [dict(e) if isinstance(e, Mapping) else {} for e in (p0.get("industry") or [])]
    while len(months) < MONTH_COUNT:
        months.append({})
    while len(prior) < MONTH_COUNT:
        prior.append({})
    while len(industry) < len(INDUSTRY_ROWS):
        industry.append({})

    applied = 0
    visited = 0
    prefix = TABLE_KEY_D48 + "/"
    for sk in projection.stable_keys():
        s = str(sk)
        if not s.startswith(prefix):
            continue
        visited += 1
        parts = s.split("/")
        if len(parts) < 3:
            continue
        mid, contract_field = parts[1], parts[2]
        # stable_field_key 用契约小写键 → 反查回 store 驼峰键写回（前端 ProductData 键）
        field = _CONTRACT_TO_STORE_FIELD.get(contract_field)
        if field is None:
            continue
        new_val = getattr(projection.get(sk), "value", None)
        if mid.startswith("m"):
            # m{month}_{loc}
            try:
                month = int(mid.split("_")[0].replace("m", ""))
                loc = mid.split("_")[1]
            except (ValueError, IndexError):
                continue
            arr = months if loc == "cur" else prior
            if month < MONTH_COUNT and arr[month].get(field) != new_val:
                arr[month][field] = new_val
                applied += 1
        elif mid.startswith("ind"):
            # ind{idx}_{loc} —— 只回写 cur（前端 industry 无 prior 字段）
            try:
                idx = int(mid.split("_")[0].replace("ind", ""))
                loc = mid.split("_")[1]
            except (ValueError, IndexError):
                continue
            if loc == "cur" and idx < len(industry) and industry[idx].get(field) != new_val:
                industry[idx][field] = new_val
                applied += 1

    p0["months"] = months
    p0["priorMonths"] = prior
    p0["industry"] = industry
    products[0] = p0
    return products, applied, visited


def merge_d48_from_projection(*, projection, base_state):
    """oo_to_html 专用块门面（3-tuple）。"""
    return merge_projection_into_d48_store(projection=projection, base_state=base_state)
