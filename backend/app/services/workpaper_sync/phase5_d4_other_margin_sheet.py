# -*- coding: utf-8 -*-
"""D4-33 其他业务毛利率分析表双向回写 provider（批次B 第八张，矩阵首张 · limited_bidirectional）。

共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。**static-cell 矩阵**模型（无 UUID / 无动态行）。

几何（openpyxl 直读 `D/D4 收入底稿.xlsx` sheet `其他业务毛利率分析表D4-33`，A1:M31）：
  · 固定 12 月行 R12-23；固定 3 业务类型列组：出租固定资产 E-G / 出租无形资产 H-J / 销售材料 K-M。
  · 每组 收入(E/H/K)/成本(F/I/L)/毛利率(G/J/M)；合计列 B/C/D；合计/上年/变动 行 24-27 —— 全 Excel 公式。
  · 受管输入 = **前 3 个业务类型 × 12 月 × 2（收入/成本）= 72 个 static cell**（E/F/H/I/K/L × R12-23）。

🔴 **limited_bidirectional 裁决**：前端 `D4-33-data` 业务类型**动态**（可增删），模板只有 3 固定列组。
  本 provider 只受管**前 3 个业务类型**（按 store.bizTypes 顺序**位置**映射到 3 列组），第 4+ 个
  业务类型无模板列 → HTML-only。合计/毛利率/上年/变动全公式（formula_mask），不受管。
  投影/合并按「slot 位置 ↔ store.bizTypes[slot].id」翻译，契约用固定 cell（不含动态 bizId）。

前端真源：`D4TabOtherMargin.vue` + store `D4-33-data` = `{bizTypes[], months{bizId:[12]}, priorYear{}}`。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
MANAGED_SHEET_D433: Final[str] = "其他业务毛利率分析表D4-33"
TEMPLATE_ID_D433: Final[str] = "D433"
SHEET_KEY_D433: Final[str] = "d433-managed"
STORE_ITEM_ID_D433: Final[str] = "D4-33-data"
TABLE_KEY_D433: Final[str] = "d4_33_matrix"

HEADER_ROW_D433: Final[int] = 11
FIRST_MONTH_ROW_D433: Final[int] = 12   # 1 月
LAST_MONTH_ROW_D433: Final[int] = 23    # 12 月
MONTH_COUNT: Final[int] = 12

#: 3 个业务类型列组（slot 位置 → 收入列 / 成本列）。毛利率列 G/J/M 为公式，不受管。
#: slot0 出租固定资产 E/F · slot1 出租无形资产 H/I · slot2 销售材料 K/L。
BIZ_SLOTS: Final[tuple[tuple[str, str], ...]] = (("E", "F"), ("H", "I"), ("K", "L"))
BIZ_SLOT_COUNT: Final[int] = len(BIZ_SLOTS)

#: formula_mask：合计列 B/C/D + 各组毛利率 G/J/M（R12-23）+ 合计/上年/变动行 24-27（B-M）。
def _formula_mask() -> tuple[str, ...]:
    cells: list[str] = []
    for row in range(FIRST_MONTH_ROW_D433, LAST_MONTH_ROW_D433 + 1):
        for col in ("B", "C", "D", "G", "J", "M"):
            cells.append(f"{col}{row}")
    for row in (24, 25, 26, 27):
        for col in "BCDEFGHIJKLM":
            cells.append(f"{col}{row}")
    return tuple(cells)


FORMULA_MASK_D433: Final[tuple[str, ...]] = _formula_mask()


def formula_mask_cells_d433() -> tuple[str, ...]:
    return FORMULA_MASK_D433


def _stable_key(slot: int, month: int, field: str) -> str:
    return f"{TABLE_KEY_D433}/slot{slot}_m{month}/{field}"


def mapping_digest_d433() -> str:
    payload = json.dumps(
        {"sheet": MANAGED_SHEET_D433, "slots": BIZ_SLOTS, "months": MONTH_COUNT,
         "first_row": FIRST_MONTH_ROW_D433, "formula_mask": list(FORMULA_MASK_D433)},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d433() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D433}!{cell}"

    fields: list[dict[str, Any]] = []
    for slot, (rev_col, cost_col) in enumerate(BIZ_SLOTS):
        for m in range(MONTH_COUNT):
            row = FIRST_MONTH_ROW_D433 + m
            for field, col in (("revenue", rev_col), ("cost", cost_col)):
                fields.append(
                    {
                        "stable_field_key": _stable_key(slot, m, field),
                        "json_pointer": f"/slot{slot}/month{m}/{field}",
                        "column_key": f"s{slot}_m{m}_{field}",
                        "cell": {"column": col, "row_from": row},
                        "mode": "editable",
                        "value_type": "amount",
                        "source_ref": _src(f"{col}{row}"),
                        "header_source_ref": _src(f"{col}{HEADER_ROW_D433}"),
                        "store_item_id": STORE_ITEM_ID_D433,
                        "header_text": f"业务{slot + 1} {m + 1}月{'收入' if field == 'revenue' else '成本'}",
                    }
                )
    # static-cell 表：无 row_identity / delete_policy / footer_anchor（参 D4-5 fixed_table）。
    return {
        "sheet_key": SHEET_KEY_D433,
        "excel_name": MANAGED_SHEET_D433,
        "template_id": TEMPLATE_ID_D433,
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [
            {
                "table_key": TABLE_KEY_D433,
                "anchor": f"A{HEADER_ROW_D433}",
                "header_rows": 2,
                "formula_mask": list(FORMULA_MASK_D433),
                "fields": fields,
            }
        ],
    }


def _decode(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        return json.loads(payload) if payload.strip() else {}
    return payload


def _biz_ids(data: Mapping[str, Any]) -> list[str]:
    """按 store.bizTypes 顺序取前 BIZ_SLOT_COUNT 个 bizId（slot 位置映射）。"""
    biz_types = data.get("bizTypes") if isinstance(data, Mapping) else None
    ids: list[str] = []
    if isinstance(biz_types, list):
        for b in biz_types[:BIZ_SLOT_COUNT]:
            if isinstance(b, Mapping) and b.get("id"):
                ids.append(str(b["id"]))
    return ids


def build_store_projection_d433(payload: Any, *, contract, limits=None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    data = _decode(payload)
    data = data if isinstance(data, Mapping) else {}
    biz_ids = _biz_ids(data)
    months = data.get("months") if isinstance(data.get("months"), Mapping) else {}

    values: dict[str, FieldValue] = {}
    for slot in range(BIZ_SLOT_COUNT):
        biz_id = biz_ids[slot] if slot < len(biz_ids) else None
        month_arr = months.get(biz_id) if biz_id else None
        month_arr = month_arr if isinstance(month_arr, list) else []
        for m in range(MONTH_COUNT):
            entry = month_arr[m] if m < len(month_arr) and isinstance(month_arr[m], Mapping) else {}
            for field in ("revenue", "cost"):
                sk = _stable_key(slot, m, field)
                spec = contract.field_by_stable_key(sk)
                raw = entry.get(field)
                # 前端存字符串/空 → 归一为数值（amount 空 = 0，与 materialize 空格反读一致）
                if raw in (None, ""):
                    value: Any = 0
                else:
                    try:
                        value = float(raw)
                        if value == int(value):
                            value = int(value)
                    except (TypeError, ValueError):
                        value = 0
                values[sk] = FieldValue(stable_key=sk, value=value, value_type=spec.value_type, mode=spec.mode, row_key=None)
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={TABLE_KEY_D433: ()},
    )


def merge_projection_into_d433_store(*, projection, base_state):
    """把投影合并回 store（{bizTypes,months,priorYear}），只覆盖前 3 slot 的月度收入/成本。

    保留 bizTypes / priorYear / 第 4+ 业务类型；不动毛利率（前端派生）。
    dict store：返回 (merged_dict, applied, visited) 3-tuple，与 D4-9/D4-35 dict 块约定一致
    （oo_to_html 走专用 dict 块消费，**不进** merge_projection_into_all_d4_stores 的 4-tuple rows 循环）。
    """
    data = _decode(base_state)
    out = dict(data) if isinstance(data, Mapping) else {"bizTypes": [], "months": {}, "priorYear": {}}
    biz_ids = _biz_ids(out)
    months = dict(out.get("months")) if isinstance(out.get("months"), Mapping) else {}
    prefix = TABLE_KEY_D433 + "/slot"
    applied = 0
    visited = 0

    for sk in projection.stable_keys():
        s = str(sk)
        if not s.startswith(prefix):
            continue
        visited += 1
        # key 形如 d4_33_matrix/slot{S}_m{M}/{field}
        parts = s.split("/")
        if len(parts) < 3:
            continue
        mid = parts[1]  # slot{S}_m{M}
        field = parts[2]
        try:
            slot = int(mid.split("_")[0].replace("slot", ""))
            month = int(mid.split("_")[1].replace("m", ""))
        except (ValueError, IndexError):
            continue
        if slot >= len(biz_ids):
            continue  # 该 slot 无对应业务类型（<3 个），跳过（第 4+ 或 <3 张 HTML-only）
        biz_id = biz_ids[slot]
        arr = months.get(biz_id)
        if not isinstance(arr, list):
            arr = [{"revenue": "", "cost": ""} for _ in range(MONTH_COUNT)]
        else:
            arr = [dict(e) if isinstance(e, Mapping) else {"revenue": "", "cost": ""} for e in arr]
            while len(arr) < MONTH_COUNT:
                arr.append({"revenue": "", "cost": ""})
        if month < MONTH_COUNT:
            new_val = getattr(projection.get(sk), "value", None)
            if arr[month].get(field) != new_val:
                arr[month][field] = new_val
                applied += 1
        months[biz_id] = arr

    out["months"] = months
    return out, applied, visited


def merge_d433_from_projection(*, projection, base_state):
    """oo_to_html 专用 dict 块门面（同 merge_d49_from_projection / merge_d435_from_projection）。

    返回 (merged_dict, applied, visited)。merged_dict 恒为完整 {bizTypes,months,priorYear} 形态。
    """
    return merge_projection_into_d433_store(projection=projection, base_state=base_state)


def store_item_id_d433() -> str:
    return STORE_ITEM_ID_D433
