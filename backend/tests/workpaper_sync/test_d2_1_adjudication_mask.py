# -*- coding: utf-8 -*-
"""D2-1 审定表逐格 mask + 固定行 —— 行为级判据（judge-first）。

spec: d2-sync-coverage-via-row-table-engine · Task 4/11
Requirements 3.1/3.2/3.3/3.7 · 9.2 · design Property 6/7

D2-1 是逐格审定表（311 公式 / 密度 38%），固定 4 行（individual/aging/customer-type/total），
row_mode=fixed_rows（D4-6 稳定 key 固定行范式）。逐格 mask 依赖已入库的 merge._protection
格级判定（cell_in_ranges + _mask_spans_data_column，commit 8c51975b5）。

Q6：D2-1 是固定行，无动态 identity 列需求；变异改 dynamic_identity ⇒ 必红。
Q7：逐格 mask 下 6 个人工金额字段仍判 editable；变异换 column_in_ranges ⇒ 必红
    （钉住 D4-1 踩过的坑：声明 editable 的金额字段被整列误判 read_only_masked_cell）。
"""
from __future__ import annotations

from app.services.workpaper_sync import phase5_d2_01_adjudication as m


# ═══════════════════════════════════════════════════════════════════════════
# Q6：固定 4 行，row_mode=fixed_rows，无动态 identity 列需求
# ═══════════════════════════════════════════════════════════════════════════
def test_d21_has_exactly_four_fixed_rows() -> None:
    keys = [rk for rk, _r, _c, _s in m.FIXED_ROWS_D21]
    assert keys == ["individual", "aging", "customer-type", "total"], keys


def test_row_mode_is_fixed_rows_not_dynamic() -> None:
    assert m.ROW_MODE == "fixed_rows"
    # Property 6：固定行不需要动态 identity 列
    assert m.requires_dynamic_identity_column() is False


def test_only_total_row_is_summary() -> None:
    assert m.row_type_for("total") == "summary"
    for rk in ("individual", "aging", "customer-type"):
        assert m.row_type_for(rk) == "fixed"


def test_unknown_row_key_fails_closed() -> None:
    import pytest

    with pytest.raises(ValueError):
        m.row_type_for("unknown-row")


# ═══════════════════════════════════════════════════════════════════════════
# Q7：逐格 mask 下 6 个人工金额字段仍判 editable（格级判定生效）
# ═══════════════════════════════════════════════════════════════════════════
def test_editable_amount_cells_are_not_masked() -> None:
    """Property 7 核心：6 个人工金额格必须判 editable（非 read_only_masked_cell）。"""
    misjudged = m.editable_amount_cells_are_not_masked()
    assert misjudged == [], f"这些人工金额格被误判 masked（D4-1 踩过的坑）: {misjudged}"


def test_sumif_and_derived_cells_are_masked() -> None:
    """反向：SUMIF 取数格（F/G/H）与派生列格（E/I/J/K）必须判 masked（OO 重算不覆盖）。"""
    # SUMIF 列在数据行
    for cell in ("F8", "G8", "H8", "F10", "F11"):
        assert m.cell_is_masked(cell), f"{cell} SUMIF 格应判 masked"
    # 派生列
    for cell in ("E8", "I8", "J8", "K8"):
        assert m.cell_is_masked(cell), f"{cell} 派生格应判 masked"


def test_editable_cells_on_same_column_as_masked_still_editable() -> None:
    """格级判定关键：B/C/D 在 R10/R11 是人工录入，即便 R9/R13 同列 B/C/D 有 mask
    也不得被整列误判（这正是 D4-1 六字段被整列挡的坑）。"""
    # R9/R13 的 B/C/D 在 mask 里（小计/合计行）
    assert m.cell_is_masked("B9")
    assert m.cell_is_masked("B13")
    # 但 R10/R11 的 B/C/D 不在 mask（人工录入）
    for cell in ("B10", "C10", "D10", "B11", "C11", "D11"):
        assert not m.cell_is_masked(cell), f"{cell} 应 editable（格级判定，非整列）"


def test_mapping_digest_stable() -> None:
    assert m.assert_mapping_digest_d21() == m.EXPECTED_MAPPING_DIGEST_D21


# ═══════════════════════════════════════════════════════════════════════════
# 父契约接入（P0-1 复盘修复：D2-1 不再是孤立模块，真进父契约 sheets[]）
# ═══════════════════════════════════════════════════════════════════════════
def test_d21_is_attached_to_parent_contract() -> None:
    """D2-1 sheet 真进父契约 sheets[]（d21-managed），parse_contract 强校验通过。

    🔴 P0-1 复盘修复：此前 D2-1 provider 只被判据 import、未接入父契约（孤立声明）。
    现照 D4-9 totals 静态字段范式接入：6 个 editable 金额格 + 逐格 formula_mask + 无 row_identity。
    """
    from app.services.workpaper_sync import pilot_d2_large_json as parent
    from app.services.workpaper_sync.contracts import parse_contract

    contract = parse_contract(parent.build_contract_payload(), adapter_id=parent.PILOT_ADAPTER_ID)
    by_key = {s.sheet_key: s for s in contract.sheets}
    assert m.SHEET_KEY_D21 in by_key, "D2-1 审定表未接入父契约 sheets[]"
    d21 = by_key[m.SHEET_KEY_D21]
    # 单 table（静态 cell 型），6 个 editable 金额字段，无 row_identity（固定行不注入 UUID）。
    assert len(d21.tables) == 1
    assert len(d21.tables[0].fields) == 6, "D2-1 应声明 6 个 editable 金额格"
    assert d21.tables[0].row_identity is None, "静态 cell 型不应有 row_identity"
    # 逐格 mask 进契约（SUMIF + 派生 + 小计/合计）。
    assert len(d21.tables[0].formula_mask) == len(m.FORMULA_MASK)
    # 受管区总数：D2-2 ① + D2-3 ② + D2-1 ① = 4（D2-4 判 single_html 不计）。
    assert sum(len(s.tables) for s in contract.sheets) == 4


def test_d21_editable_cells_map_to_percell_store_keys() -> None:
    """6 个 editable 金额格的 store_item_id 与前端 per-cell 锚点逐字对齐。"""
    store_ids = {sid for _c, _col, _r, _rk, sid, _vt, _h in m.EDITABLE_CELL_SPECS}
    assert store_ids == {
        "D2-adj-aging-prior-unadjusted", "D2-adj-aging-prior-aje", "D2-adj-aging-prior-rje",
        "D2-adj-customer-type-prior-unadjusted", "D2-adj-customer-type-prior-aje",
        "D2-adj-customer-type-prior-rje",
    }, store_ids
