# -*- coding: utf-8 -*-
"""D4-1「营业收入审定表」契约结构守卫 —— `parse_contract` 真跑。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io · Task 2
Requirements 1.1 / 2.3 / 5.4 · Property 5（双区几何与 fail-closed）

判据先行（judge-first）：本测试断言 D4-1 受管 sheet `d41-managed` 一旦被
`phase5_d4_revenue_detail.build_contract_payload()` 纳入 sheets[]，经 `parse_contract`
强校验后必须得到**同 sheet 双区动态行**结构（参照 D4-9 单 sheet 多 table）：

  · sheet `d41-managed`（excel_name=`营业收入审定表D4-1`）含 **2 张 row table**：
      - `adjudication_main_rows`（section main-revenue，主营段 R8 起）
      - `adjudication_other_rows`（section other-revenue，其他段 R14 起）
  · 两张 table 各有 `row_identity`（kind=field）+ `delete_policy`；
  · 两区 **UUID 列不同**（geometry: 主营 W / 其他 X）；
  · 受管字段 = A(label)+B/C/D(本期未审/账项/重分类)+F/G/H(上期三输入)，共 7 列 × 2 区；
  · E/I(审定数 =SUM) + 小计/合计/差异行(12/18/19/21) 的 B–I 落 `formula_mask`，
    受管列(B/C/D/F/G/H) 绝不落 formula_mask。

反向自检（同一份 payload 变异 → parse 失败或几何守卫红）：
  M1 把两区合并成一张 table → sheet 只剩 1 table，双区几何守卫红；
  M2 去掉 formula_mask → E/I/小计/合计/差异不再受保护，formula_mask 守卫红。

🔴 RED 前提：Task 4/5 的 provider `phase5_d4_adjudication_sheet.py` + 6 点集成尚未落地，
`d41-managed` 不在 `build_contract_payload()` 的 sheets[] 里 —— 本测试**应当失败**
（`_d41_sheet_payload()` 抛 `AssertionError: d41-managed 未接入`）。只有真契约正确接入后
才转 GREEN。禁止把 sheet 缺失当通过（不 xfail/skip 掩盖），也禁止在测试里自造 payload
伪造双区（那样即使 provider 断裂也 GREEN）。
"""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.contracts import (  # noqa: E402
    ContractError,
    DeletePolicy,
    RowIdentityKind,
    ValueType,
    parse_contract,
)

# ── 从 Task 1 冻结的几何证据派生的期望常量（evidence/d41-geometry.json） ──────────
D41_SHEET_KEY = "d41-managed"
D41_EXCEL_NAME = "营业收入审定表D4-1"
D41_TABLE_KEY_MAIN = "adjudication_main_rows"
D41_TABLE_KEY_OTHER = "adjudication_other_rows"
D41_SECTION_MAIN = "main-revenue"
D41_SECTION_OTHER = "other-revenue"
#: 受管列（label + 6 金额）。E/I 审定数与小计/合计/差异行不在此列表。
D41_MANAGED_COLUMNS = ("A", "B", "C", "D", "F", "G", "H")
#: 受管字段的 store_key（与前端 useD4Adjudication 六金额字段逐项对齐）。
D41_MANAGED_STORE_KEYS = {
    "label",
    "currentUnadjusted",
    "currentAje",
    "currentRje",
    "priorUnadjusted",
    "priorAje",
    "priorRje",
}
#: formula_mask 必须覆盖的代表格（E/I 数据行 + 小计/合计/差异行 B–I）。
D41_MASK_MUST_INCLUDE_COLUMNS = ("E", "I")
D41_MASK_FORMULA_ROWS = (12, 18, 19, 21)


# ═══════════════════════════════════════════════════════════════════════════
# helpers —— 都从**真实** build_contract_payload() 取，不自造 payload
# ═══════════════════════════════════════════════════════════════════════════


def _contract_payload() -> dict[str, Any]:
    return D4.build_contract_payload()


def _sheet_by_key(payload: Mapping[str, Any], sheet_key: str) -> dict[str, Any] | None:
    for sheet in payload.get("sheets") or ():
        if sheet.get("sheet_key") == sheet_key:
            return dict(sheet)
    return None


def _d41_sheet_payload() -> dict[str, Any]:
    """取真实契约里的 D4-1 sheet；未接入则 fail（判据先行的 RED 触点）。"""
    sheet = _sheet_by_key(_contract_payload(), D41_SHEET_KEY)
    assert sheet is not None, (
        f"{D41_SHEET_KEY} 未接入 build_contract_payload().sheets —— "
        "Task 4/5 provider + 6 点集成尚未落地（判据先行，此为预期 RED）"
    )
    return sheet


def _column_in_mask(column: str, mask: list[str]) -> bool:
    """列是否落在任一 A1 区域/单格的列跨度内。"""
    from app.services.workpaper_sync.contracts import column_in_ranges

    if not mask:
        return False
    return column_in_ranges(column, mask)


def _mask_covers_cell(cell: str, mask: list[str]) -> bool:
    """单格 `E8` 是否被 mask 的任一区域覆盖（列 + 行都要落进区间）。"""
    from app.services.workpaper_sync.contracts import parse_a1_range

    import re as _re

    m = _re.match(r"^([A-Z]{1,3})([1-9][0-9]*)$", cell)
    assert m is not None, f"cell {cell!r} 形态非法"
    col, row = m.group(1), int(m.group(2))

    def _col_idx(c: str) -> int:
        idx = 0
        for ch in c:
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
        return idx

    tgt_col = _col_idx(col)
    for raw in mask:
        c1, r1, c2, r2 = parse_a1_range(raw, location="formula_mask")
        lo_c, hi_c = sorted((_col_idx(c1), _col_idx(c2)))
        lo_r, hi_r = sorted((r1, r2))
        if lo_c <= tgt_col <= hi_c and lo_r <= row <= hi_r:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# 1. parse_contract 真跑：整份契约含 D4-1 后仍强校验通过
# ═══════════════════════════════════════════════════════════════════════════


def test_full_contract_parses_with_d41_sheet() -> None:
    """整份 payload（含 D4-1）经 parse_contract 强校验通过，且 d41-managed 在结果里。"""
    payload = _contract_payload()
    # 先确认已接入（RED 触点）。
    assert _sheet_by_key(payload, D41_SHEET_KEY) is not None, (
        f"{D41_SHEET_KEY} 未接入 —— Task 4/5 未落地（预期 RED）"
    )
    contract = parse_contract(payload, adapter_id=D4.ADAPTER_ID)
    keys = {s.sheet_key for s in contract.sheets}
    assert D41_SHEET_KEY in keys
    d41 = next(s for s in contract.sheets if s.sheet_key == D41_SHEET_KEY)
    assert d41.excel_name == D41_EXCEL_NAME


# ═══════════════════════════════════════════════════════════════════════════
# 2. 双区结构：2 张 row table（main/other），各有 row_identity + delete_policy
# ═══════════════════════════════════════════════════════════════════════════


def test_d41_sheet_has_two_row_tables_main_and_other() -> None:
    contract = parse_contract(_contract_payload(), adapter_id=D4.ADAPTER_ID)
    d41 = next(s for s in contract.sheets if s.sheet_key == D41_SHEET_KEY)
    table_keys = [t.table_key for t in d41.tables]
    assert len(d41.tables) == 2, (
        f"D4-1 必须是同 sheet 双区（2 张 row table），实得 {len(d41.tables)}: {table_keys}"
    )
    assert D41_TABLE_KEY_MAIN in table_keys
    assert D41_TABLE_KEY_OTHER in table_keys


def test_both_tables_are_dynamic_rows_with_delete_policy() -> None:
    contract = parse_contract(_contract_payload(), adapter_id=D4.ADAPTER_ID)
    d41 = next(s for s in contract.sheets if s.sheet_key == D41_SHEET_KEY)
    for table in d41.tables:
        assert table.row_identity is not None, (
            f"{table.table_key} 缺 row_identity —— 双区都是动态增删行（CS-14）"
        )
        assert table.row_identity.kind is RowIdentityKind.field, (
            f"{table.table_key} row_identity.kind 必须是 field（禁下标/序号身份）"
        )
        assert table.delete_policy is not None, (
            f"{table.table_key} 缺 delete_policy（动态行删除策略必须裁决，CS-14）"
        )
        assert table.delete_policy in (DeletePolicy.tombstone, DeletePolicy.reject)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 两区 UUID 列不同（geometry: 主营 W / 其他 X）
# ═══════════════════════════════════════════════════════════════════════════


def test_two_regions_use_distinct_uuid_columns() -> None:
    """两区 UUID 列必须互不相同（同 D4-9 W/X 思路），否则同 sheet 双区身份串区。"""
    sheet = _d41_sheet_payload()
    tables = {t["table_key"]: t for t in sheet["tables"]}
    assert D41_TABLE_KEY_MAIN in tables and D41_TABLE_KEY_OTHER in tables
    main = tables[D41_TABLE_KEY_MAIN]
    other = tables[D41_TABLE_KEY_OTHER]
    main_uuid = main.get("uuid_col") or main.get("uuid_column")
    other_uuid = other.get("uuid_col") or other.get("uuid_column")
    assert main_uuid, f"{D41_TABLE_KEY_MAIN} 缺 uuid 列声明"
    assert other_uuid, f"{D41_TABLE_KEY_OTHER} 缺 uuid 列声明"
    assert main_uuid != other_uuid, (
        f"两区 UUID 列相同（{main_uuid}）—— 同 sheet 双区必须用不同空列（geometry 主营 W / 其他 X）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 受管字段 = A/B/C/D/F/G/H（label + 6 金额），两区一致
# ═══════════════════════════════════════════════════════════════════════════


def test_each_table_manages_label_plus_six_amounts() -> None:
    contract = parse_contract(_contract_payload(), adapter_id=D4.ADAPTER_ID)
    d41 = next(s for s in contract.sheets if s.sheet_key == D41_SHEET_KEY)
    for table in d41.tables:
        columns = {f.cell.column for f in table.fields if f.cell is not None}
        assert columns == set(D41_MANAGED_COLUMNS), (
            f"{table.table_key} 受管列={sorted(columns)} 与核定 {list(D41_MANAGED_COLUMNS)} 不符"
        )
        # label 是 text，其余六列是 amount。
        by_col = {f.cell.column: f for f in table.fields if f.cell is not None}
        assert by_col["A"].value_type is ValueType.text
        for col in ("B", "C", "D", "F", "G", "H"):
            assert by_col[col].value_type is ValueType.amount, (
                f"{table.table_key}.{col} value_type 必须是 amount"
            )


def test_managed_store_keys_align_with_frontend_six_fields() -> None:
    """受管字段的 store_key 必须与前端 useD4Adjudication 六金额字段 + label 对齐。"""
    sheet = _d41_sheet_payload()
    for table in sheet["tables"]:
        store_keys = set()
        for field in table["fields"]:
            sk = field.get("store_key") or field.get("column_key")
            if sk:
                store_keys.add(sk)
        assert D41_MANAGED_STORE_KEYS <= store_keys, (
            f"{table['table_key']} store_key 缺失前端字段: "
            f"{sorted(D41_MANAGED_STORE_KEYS - store_keys)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. formula_mask：E/I + 小计/合计/差异行(12/18/19/21) 的 B–I；受管列不入 mask
# ═══════════════════════════════════════════════════════════════════════════


def test_formula_mask_protects_audited_and_footer_formula_cells() -> None:
    sheet = _d41_sheet_payload()
    # 合并两区 mask（也接受 sheet 级 mask，若 provider 那样声明）。
    mask: list[str] = list(sheet.get("formula_mask") or ())
    for table in sheet["tables"]:
        mask.extend(table.get("formula_mask") or ())
    assert mask, "D4-1 必须声明 formula_mask（E/I 审定数 + 小计/合计/差异行公式）"

    # E/I 审定数数据行代表格必须受保护。
    for cell in ("E8", "I8", "E14", "I14"):
        assert _mask_covers_cell(cell, mask), (
            f"审定数格 {cell} 未落 formula_mask —— =SUM 公式字节会被普通值投影覆盖"
        )
    # 小计/合计/差异行(12/18/19/21) 的 B–I 必须受保护。
    for row in D41_MASK_FORMULA_ROWS:
        for col in ("B", "E", "I"):
            assert _mask_covers_cell(f"{col}{row}", mask), (
                f"小计/合计/差异格 {col}{row} 未落 formula_mask"
            )


def test_managed_columns_are_not_in_formula_mask() -> None:
    """受管列(B/C/D/F/G/H) 的数据行不得落 formula_mask（否则普通值投影被误挡）。"""
    sheet = _d41_sheet_payload()
    mask: list[str] = list(sheet.get("formula_mask") or ())
    for table in sheet["tables"]:
        mask.extend(table.get("formula_mask") or ())
    # 主营数据行 8、其他数据行 14 的受管金额列不得被 mask 覆盖。
    for row in (8, 14):
        for col in ("B", "C", "D", "F", "G", "H"):
            assert not _mask_covers_cell(f"{col}{row}", mask), (
                f"受管金额格 {col}{row} 被 formula_mask 覆盖 —— 会挡住正常双向回写"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 反向自检（变异 → parse 失败或几何守卫红）
# ═══════════════════════════════════════════════════════════════════════════


def _merge_two_tables_into_one(payload: dict[str, Any]) -> dict[str, Any]:
    """M1：把 D4-1 两区合并成一张 table（其他区字段并进主区）。"""
    mutated = copy.deepcopy(payload)
    sheet = _sheet_by_key(mutated, D41_SHEET_KEY)
    assert sheet is not None
    idx = next(i for i, s in enumerate(mutated["sheets"]) if s["sheet_key"] == D41_SHEET_KEY)
    tables = sheet["tables"]
    assert len(tables) == 2
    main, other = tables[0], tables[1]
    merged = copy.deepcopy(main)
    merged["fields"] = list(main["fields"]) + list(other["fields"])
    sheet = dict(sheet)
    sheet["tables"] = [merged]
    mutated["sheets"][idx] = sheet
    return mutated


def _strip_formula_mask(payload: dict[str, Any]) -> dict[str, Any]:
    """M2：抹掉 D4-1 两区 + sheet 级 formula_mask。"""
    mutated = copy.deepcopy(payload)
    sheet = _sheet_by_key(mutated, D41_SHEET_KEY)
    assert sheet is not None
    idx = next(i for i, s in enumerate(mutated["sheets"]) if s["sheet_key"] == D41_SHEET_KEY)
    sheet = dict(sheet)
    sheet.pop("formula_mask", None)
    new_tables = []
    for table in sheet["tables"]:
        t = dict(table)
        t.pop("formula_mask", None)
        new_tables.append(t)
    sheet["tables"] = new_tables
    mutated["sheets"][idx] = sheet
    return mutated


def test_mutation_merge_two_tables_breaks_dual_region_guard() -> None:
    """M1：两区合并成一 table → 双区几何守卫（须 2 张 table）红。"""
    mutated = _merge_two_tables_into_one(_contract_payload())
    # parse 本身可能仍通过（单 table 合法），但双区几何断言必须红。
    try:
        contract = parse_contract(mutated, adapter_id=D4.ADAPTER_ID)
    except ContractError:
        return  # parse 直接拒绝也算守卫生效
    d41 = next(s for s in contract.sheets if s.sheet_key == D41_SHEET_KEY)
    assert len(d41.tables) != 2, "变异后仍是 2 张 table —— 合并变异未生效"
    with pytest.raises(AssertionError):
        assert len(d41.tables) == 2, "双区几何守卫应对合并变异报红"


def test_mutation_strip_formula_mask_breaks_mask_guard() -> None:
    """M2：去掉 formula_mask → mask 守卫红（E/I/小计/合计/差异不再受保护）。"""
    mutated = _strip_formula_mask(_contract_payload())
    sheet = _sheet_by_key(mutated, D41_SHEET_KEY)
    assert sheet is not None
    mask: list[str] = list(sheet.get("formula_mask") or ())
    for table in sheet["tables"]:
        mask.extend(table.get("formula_mask") or ())
    # 变异后 mask 应为空 → 审定数格不再被覆盖 → 守卫断言必红。
    with pytest.raises(AssertionError):
        assert _mask_covers_cell("E8", mask), "去 mask 后审定数守卫应报红"
