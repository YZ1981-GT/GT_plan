# -*- coding: utf-8 -*-
"""行表引擎与七家 provider 原实现的等价判据（D1-P2 / D1-P3 / D1-P4）。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 6/7/8
Requirements 1.1 / 1.2 / 1.3

═══ 判据面 ═══

* **D1-P2**（Req 1.2）：`RowTableSheetSpec.formula_mask` 输出 ≡ provider 原手写 `FORMULA_MASK`
  字面量，**逐元素相等**。变异：改 formula_columns 顺序 ⇒ 必红。
* **D1-P3**（Req 1.3）：`managed_field_specs(spec)` 输出（投影掉第 7 位 group_header_cell）
  ≡ 原 `MANAGED_FIELD_SPECS`，**逐元组相等含顺序**。变异：账龄段展开顺序错乱 ⇒ 必红。
* **D1-P4**（Req 1.3）：nested（D3/D7）与 flat（D6）两种 key 派生各自等于原写法。
  变异（反证式）：把 flat 走 nested 派生 ⇒ D6 必红。

覆盖三家代表：D1（无账龄，15 列）/ D3（nested 账龄，19 标量 + 8 账龄 = 27 列）/
D6（flat 账龄，22 标量 + 8 账龄 = 30 列）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d1_notes_receivable as D1
from app.services.workpaper_sync import phase5_d3_prepaid_receipts as D3
from app.services.workpaper_sync import phase5_d6_contract_assets as D6
from app.services.workpaper_sync.phase5_row_table_sheet import (
    AgingGroupSpec,
    AgingLayout,
    RowTableSheetSpec,
    expand_aging_fields,
    managed_field_specs,
)
from app.services.workpaper_sync.sheet_geometry import col_index


def _spec_d1() -> RowTableSheetSpec:
    """按 D1 provider 实测常量构造引擎 spec（无账龄，field_specs 补第 7 位空 group）。"""
    return RowTableSheetSpec(
        managed_sheet=D1.MANAGED_SHEET,
        sheet_key=D1.SHEET_KEY,
        table_key=D1.ROWS_TABLE_KEY,
        template_id=D1.TEMPLATE_ID,
        table_name=D1.TABLE_NAME,
        uuid_col=D1.UUID_COL,
        first_data_row=D1.FIRST_DATA_ROW,
        last_data_row=D1.LAST_DATA_ROW,
        footer_row=D1.FOOTER_ROW,
        header_row=D1.HEADER_ROW,
        store_item_id=D1.STORE_ITEM_ID,
        row_identity_key=D1.ROW_IDENTITY_STORE_KEY,
        field_specs=tuple((*row, "") for row in D1.MANAGED_FIELD_SPECS),
        formula_columns=("G", "J", "L", "O"),
        formula_templates=dict(D1.FORMULA_TEMPLATES),
        footer_marker=D1.FOOTER_MARKER,
    )


def _spec_d3() -> RowTableSheetSpec:
    """按 D3 provider 实测常量构造引擎 spec（nested 账龄两组）。"""
    groups = tuple(
        AgingGroupSpec(
            json_prefix=json_prefix,
            group_header_cell=group_cell.replace("源xlsx!", ""),
            segments=tuple(
                (seg_key, column)
                for column, (seg_key, _leaf) in zip(columns, D3.AGING_SEGMENTS)
            ),
            leaf_labels=tuple(leaf for _seg, leaf in D3.AGING_SEGMENTS),
        )
        for json_prefix, group_cell, columns in D3.AGING_GROUPS
    )
    return RowTableSheetSpec(
        managed_sheet=D3.MANAGED_SHEET,
        sheet_key=D3.SHEET_KEY,
        table_key=D3.ROWS_TABLE_KEY,
        template_id=D3.TEMPLATE_ID,
        table_name=D3.TABLE_NAME,
        uuid_col=D3.UUID_COL,
        first_data_row=D3.FIRST_DATA_ROW,
        last_data_row=D3.LAST_DATA_ROW,
        footer_row=D3.FOOTER_ROW,
        header_group_row=D3.HEADER_GROUP_ROW,
        header_leaf_row=D3.HEADER_LEAF_ROW,
        store_item_id=D3.STORE_ITEM_ID,
        row_identity_key=D3.ROW_IDENTITY_STORE_KEY,
        field_specs=tuple((*row, "") for row in D3.SCALAR_FIELD_SPECS),
        formula_columns=("H", "O", "Q", "T"),
        aging_layout=AgingLayout.nested,
        aging_groups=groups,
        footer_marker=D3.FOOTER_MARKER,
    )


def _spec_d6() -> RowTableSheetSpec:
    """按 D6 provider 实测常量构造引擎 spec（flat 账龄两组，segments 三元）。"""
    groups = tuple(
        AgingGroupSpec(
            json_prefix="",  # flat 无 nested 前缀
            group_header_cell=group_cell,
            segments=tuple(cols),
        )
        for group_cell, cols in D6.AGING_GROUPS
    )
    return RowTableSheetSpec(
        managed_sheet=D6.MANAGED_SHEET,
        sheet_key=D6.SHEET_KEY,
        table_key=D6.ROWS_TABLE_KEY,
        template_id=D6.TEMPLATE_ID,
        table_name=D6.TABLE_NAME,
        uuid_col=D6.UUID_COL,
        first_data_row=D6.FIRST_DATA_ROW,
        last_data_row=D6.LAST_DATA_ROW,
        footer_row=D6.FOOTER_ROW,
        header_group_row=D6.HEADER_GROUP_ROW,
        store_item_id=D6.STORE_ITEM_ID,
        row_identity_key=D6.ROW_IDENTITY_STORE_KEY,
        field_specs=tuple((*row, "") for row in D6.SCALAR_FIELD_SPECS),
        formula_columns=("J", "Q", "T"),
        aging_layout=AgingLayout.flat,
        aging_groups=groups,
        footer_marker=D6.FOOTER_MARKER,
    )


# ═══════════════════════════════════════════════════════════════════════════
# D1-P2：formula_mask ≡ 原手写 FORMULA_MASK
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "spec_fn,original",
    [
        (_spec_d1, D1.FORMULA_MASK),
        (_spec_d3, D3.FORMULA_MASK),
        (_spec_d6, D6.FORMULA_MASK),
    ],
    ids=["d1", "d3", "d6"],
)
def test_p2_formula_mask_equals_original(spec_fn, original) -> None:
    """D1-P2：引擎现算 mask 逐元素等于 provider 原手写字面量。"""
    assert spec_fn().formula_mask == tuple(original)


def test_p2_mutation_reordered_columns_breaks_equality() -> None:
    """变异：改 formula_columns 顺序 ⇒ mask 顺序变 ⇒ 与原字面量不等（判据非空转）。"""
    base = _spec_d1()
    mutated = RowTableSheetSpec(
        **{
            **{f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()},
            "formula_columns": ("O", "L", "J", "G"),
        }
    )
    assert mutated.formula_mask != tuple(D1.FORMULA_MASK)


# ═══════════════════════════════════════════════════════════════════════════
# D1-P3：managed_field_specs ≡ 原 MANAGED_FIELD_SPECS（投影掉第 7 位）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "spec_fn,original",
    [
        (_spec_d1, D1.MANAGED_FIELD_SPECS),
        (_spec_d3, D3.MANAGED_FIELD_SPECS),
        (_spec_d6, D6.MANAGED_FIELD_SPECS),
    ],
    ids=["d1", "d3", "d6"],
)
def test_p3_managed_field_specs_equals_original(spec_fn, original) -> None:
    """D1-P3：引擎输出投影掉 group_header_cell 后，逐元组相等含顺序。"""
    engine = managed_field_specs(spec_fn())
    projected = tuple(row[:6] for row in engine)
    assert projected == tuple(original), (
        f"引擎 {len(projected)} 条 vs 原 {len(original)} 条；"
        f"首个差异: {next((i for i, (a, b) in enumerate(zip(projected, original)) if a != b), None)}"
    )


def test_p3_mutation_aging_order_scrambled_breaks_equality() -> None:
    """变异：账龄段展开顺序错乱（倒序 segments）⇒ 排序后列序仍对但 key 与列错配 ⇒ 必不等。"""
    base = _spec_d3()
    scrambled_groups = tuple(
        AgingGroupSpec(
            json_prefix=g.json_prefix,
            group_header_cell=g.group_header_cell,
            segments=tuple(reversed(g.segments)),
            leaf_labels=g.leaf_labels,
        )
        for g in base.aging_groups
    )
    mutated = RowTableSheetSpec(
        **{
            **{f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()},
            "aging_groups": scrambled_groups,
        }
    )
    projected = tuple(row[:6] for row in managed_field_specs(mutated))
    assert projected != tuple(D3.MANAGED_FIELD_SPECS), "账龄顺序错乱未被检出 —— P3 空转"


# ═══════════════════════════════════════════════════════════════════════════
# D1-P4：nested / flat 两种 key 派生各自等于原写法
# ═══════════════════════════════════════════════════════════════════════════


def _aging_rows_of(provider) -> tuple[tuple, ...]:
    """从 provider 的 `MANAGED_FIELD_SPECS` 里筛出账龄字段（= 非标量字段）。

    🔴 **锚点迁移**（2026-09-26）：原判据锚在 provider 的私有 `_aging_field_specs()` 上，
    而 D3 已按 Task 16 声明化（该私有函数被引擎取代后消失）⇒ 判据必须锚在**不随收敛消失**
    的那一侧。`MANAGED_FIELD_SPECS` 与 `SCALAR_FIELD_SPECS` 都是 provider 的公开常量、
    收敛前后都在，差集即账龄展开结果 —— 这才是"数不变量"。
    """
    scalar_keys = {row[0] for row in provider.SCALAR_FIELD_SPECS}
    return tuple(
        row for row in provider.MANAGED_FIELD_SPECS if row[0] not in scalar_keys
    )


def test_p4_nested_key_derivation_equals_original() -> None:
    """nested（D3）：key = snake(json_prefix)_seg.lower()，json_key = prefix/seg。"""
    engine = expand_aging_fields(_spec_d3())
    original = _aging_rows_of(D3)
    assert original, "D3 应有账龄字段（否则本判据空转）"
    # 引擎输出按列序、provider 常量按列序（两侧都经 sorted(col_index)）⇒ 可直接逐元组比
    assert tuple(row[:6] for row in engine) == tuple(
        sorted(original, key=lambda r: col_index(r[1]))
    )


def test_p4_flat_key_derivation_equals_original() -> None:
    """flat（D6）：key = snake(flat_key)，json_key = flat_key 本身（无 nested `/`）。"""
    engine = expand_aging_fields(_spec_d6())
    original = _aging_rows_of(D6)
    assert original, "D6 应有账龄字段（否则本判据空转）"
    assert tuple(row[:6] for row in engine) == tuple(
        sorted(original, key=lambda r: col_index(r[1]))
    )


def test_p4_mutation_flat_via_nested_derivation_breaks_d6() -> None:
    """反证式变异：把 D6 的 flat 声明成 nested ⇒ segments 是三元、与 nested 二元解包不兼容
    或派生出错的 key ⇒ 必不等于原写法。"""
    base = _spec_d6()
    mutated = RowTableSheetSpec(
        **{
            **{f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()},
            "aging_layout": AgingLayout.nested,
        }
    )
    # nested 分支要求 segments 是 (seg_key, column) 二元且 leaf_labels 长度匹配；
    # D6 的三元 segments + 空 leaf_labels ⇒ 必抛或产出不等结果，两者都算"被检出"。
    try:
        engine = expand_aging_fields(mutated)
    except (ValueError, TypeError):
        return  # fail-closed 即已检出
    assert tuple(row[:6] for row in engine) != tuple(D6._aging_field_specs()), (
        "flat 走 nested 派生未被检出 —— P4 空转"
    )
