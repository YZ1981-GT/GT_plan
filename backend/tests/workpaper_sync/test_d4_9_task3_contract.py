# -*- coding: utf-8 -*-
"""D4-9 Task 3 守卫：per-entry contract 结构（行为级，parse_contract 真跑）。

spec: d4-9-customer-structure-bidirectional-writeback / Task 3
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6

判据全部落在 `parse_contract` 解析出的 `SyncContract` 对象结构上（真跑校验器，非符号存在）。
"""

from __future__ import annotations

import pytest

from app.services.workpaper_sync import phase5_d4_customer_structure as M
from app.services.workpaper_sync.contracts import FieldMode


@pytest.fixture(scope="module")
def contract():
    return M.assert_contract_file_matches_source()


def _sheet(contract):
    assert len(contract.sheets) == 1
    return contract.sheets[0]


class TestThreeTableStructure:
    def test_exactly_three_tables(self, contract) -> None:
        sheet = _sheet(contract)
        keys = [t.table_key for t in sheet.tables]
        assert keys == [M.CUR_TABLE_KEY, M.PRI_TABLE_KEY, M.TOTALS_TABLE_KEY]

    def test_dynamic_row_tables_have_identity_and_delete_policy(self, contract) -> None:
        sheet = _sheet(contract)
        by_key = {t.table_key: t for t in sheet.tables}
        for key in (M.CUR_TABLE_KEY, M.PRI_TABLE_KEY):
            t = by_key[key]
            assert t.row_identity is not None, f"{key} 缺 row_identity"
            assert t.delete_policy is not None, f"{key} 缺 delete_policy"
            # 6 个行内字段全 row_scoped。
            assert len(t.fields) == 6
            assert all(f.row_scoped for f in t.fields)

    def test_totals_table_is_static_scalar(self, contract) -> None:
        sheet = _sheet(contract)
        totals = next(t for t in sheet.tables if t.table_key == M.TOTALS_TABLE_KEY)
        assert totals.row_identity is None, "totals 表不得有 row_identity"
        assert totals.delete_policy is None, "totals 表不得有 delete_policy"
        assert len(totals.fields) == 4
        for f in totals.fields:
            assert f.row_scoped is False, f"{f.stable_field_key} 必须 row_scoped=False"
            assert f.cell is not None and f.cell.static_row is not None, "totals 字段必须用静态行号"
            assert "{row_uuid}" not in f.json_pointer

    def test_totals_static_rows_match_frozen_cells(self, contract) -> None:
        sheet = _sheet(contract)
        totals = next(t for t in sheet.tables if t.table_key == M.TOTALS_TABLE_KEY)
        by_key = {f.stable_field_key: f for f in totals.fields}
        expect = {
            M.stable_key_for_total("current_total_amount"): ("C", 24),
            M.stable_key_for_total("current_total_quantity"): ("E", 24),
            M.stable_key_for_total("prior_total_amount"): ("C", 38),
            M.stable_key_for_total("prior_total_quantity"): ("E", 38),
        }
        for key, (col, row) in expect.items():
            f = by_key[key]
            assert f.cell.column == col and f.cell.static_row == row


class TestFormulaAndFooter:
    def test_ratio_columns_are_formula_and_masked(self, contract) -> None:
        sheet = _sheet(contract)
        by_key = {t.table_key: t for t in sheet.tables}
        for key, mask in (
            (M.CUR_TABLE_KEY, {"D", "F"}),
            (M.PRI_TABLE_KEY, {"D", "F"}),
        ):
            t = by_key[key]
            formula_cols = {
                f.cell.column for f in t.fields if f.mode is FieldMode.formula and f.cell
            }
            assert formula_cols == mask, f"{key} 占比公式列应为 D/F，实得 {formula_cols}"
            # 每个 formula 列必须落在 formula_mask 内（parse_contract 的 CS-13 已保证；这里显式再断言）。
            mask_cols = set()
            for rng in t.formula_mask:
                mask_cols.add(rng.split(":")[0].rstrip("0123456789"))
            assert formula_cols <= mask_cols

    def test_footer_carries_total_formula(self, contract) -> None:
        sheet = _sheet(contract)
        by_key = {t.table_key: t for t in sheet.tables}
        for key in (M.CUR_TABLE_KEY, M.PRI_TABLE_KEY):
            t = by_key[key]
            assert t.footer_anchor is not None
            assert t.footer_anchor.carries_total_formula is True

    def test_totals_table_has_no_formula_mask(self, contract) -> None:
        sheet = _sheet(contract)
        totals = next(t for t in sheet.tables if t.table_key == M.TOTALS_TABLE_KEY)
        # totals 无 formula 字段（design §2.2），故无 formula_mask。
        assert not totals.formula_mask


class TestSourceRefAndCounts:
    def test_all_fields_have_source_ref(self, contract) -> None:
        sheet = _sheet(contract)
        for t in sheet.tables:
            for f in t.fields:
                assert f.source_ref and f.source_ref.strip(), f"{f.stable_field_key} 缺 source_ref"

    def test_field_counts_frozen(self, contract) -> None:
        M.assert_field_counts()  # 6 行内 + 4 totals
        sheet = _sheet(contract)
        total_fields = sum(len(t.fields) for t in sheet.tables)
        assert total_fields == 6 + 6 + 4
