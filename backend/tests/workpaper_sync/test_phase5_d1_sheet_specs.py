# -*- coding: utf-8 -*-
"""D1-2 / D1-4 sheet 声明层判据（Task 25/26 最小验证）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 25/26 · Requirements 5.1/5.2/5.4/5.7/11.7

不重复实测几何证据（已在各模块 docstring 登记 `docs/operations/evidence/
row-table-engine-d1-coverage/`），只验证声明本身的类型自洽 + 与引擎的接口契约。
"""
from __future__ import annotations

from app.services.workpaper_sync.excel_extract import BindingKind
from app.services.workpaper_sync.phase5_d1_02_category import SPEC_D102
from app.services.workpaper_sync.phase5_d1_04_bad_debt import (
    DOWNSTREAM_CONSUMERS_D104,
    SPEC_D104_INDIVIDUAL,
    SPEC_D104_NOTETYPE,
    SPEC_D104_PORTFOLIO,
    SPECS_D104,
    THIRD_WRITER_STORE_KEYS,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    StoreKind,
    managed_field_specs,
)


class TestD102CategorySpec:
    """D1-2：稳定 key 固定行（不是 UUID 动态行）。"""

    def test_row_identity_is_stable_key_not_row_id(self) -> None:
        assert SPEC_D102.row_identity_key == "key"

    def test_binding_kind_is_excel_table_despite_fixed_rows(self) -> None:
        """🔴 关键判据：稳定 key 固定行仍是 excel_table binding（仍注入 UUID 列），
        不是 static_region —— 判据是「有没有行维度」而非「行会不会变」（D4-6 范式）。
        """
        assert SPEC_D102.binding_kind is BindingKind.excel_table
        assert SPEC_D102.uuid_col  # 非空

    def test_formula_mask_matches_e_h_k_columns(self) -> None:
        assert SPEC_D102.formula_mask == ("E11:E13", "H11:H13", "K11:K13")

    def test_managed_field_specs_count_is_11(self) -> None:
        assert len(managed_field_specs(SPEC_D102)) == 11

    def test_store_kind_is_rows(self) -> None:
        assert SPEC_D102.store_kind is StoreKind.rows


class TestD104BadDebtThreeRegions:
    """D1-4：三区（个别计提/组合计提 excel_table + 票据种类小计 static_region）。"""

    def test_three_specs_declared(self) -> None:
        assert len(SPECS_D104) == 3
        assert SPECS_D104 == (SPEC_D104_INDIVIDUAL, SPEC_D104_PORTFOLIO, SPEC_D104_NOTETYPE)

    def test_individual_and_portfolio_are_excel_table(self) -> None:
        assert SPEC_D104_INDIVIDUAL.binding_kind is BindingKind.excel_table
        assert SPEC_D104_PORTFOLIO.binding_kind is BindingKind.excel_table

    def test_notetype_is_static_region_with_no_row_dimension(self) -> None:
        """🔴 第三区在 footer 之下 ⇒ static_region，无行身份键、table_name/uuid_col 必空。"""
        assert SPEC_D104_NOTETYPE.binding_kind is BindingKind.static_region
        assert SPEC_D104_NOTETYPE.row_identity_key == ""
        assert SPEC_D104_NOTETYPE.table_name == ""
        assert SPEC_D104_NOTETYPE.uuid_col == ""
        assert SPEC_D104_NOTETYPE.defined_name  # 非空

    def test_three_regions_use_distinct_uuid_columns(self) -> None:
        """🔴 D4-1 教训：同 sheet 多区必须各用不同 UUID 列，否则行身份串区。
        （static_region 无 UUID 列，只比较两个 excel_table 区）
        """
        assert SPEC_D104_INDIVIDUAL.uuid_col != SPEC_D104_PORTFOLIO.uuid_col
        assert SPEC_D104_INDIVIDUAL.uuid_col == "O"
        assert SPEC_D104_PORTFOLIO.uuid_col == "P"

    def test_three_regions_use_distinct_store_item_ids(self) -> None:
        ids = {s.store_item_id for s in SPECS_D104}
        assert len(ids) == 3
        assert ids == {"D1-bd-individual-rows", "D1-bd-portfolio-rows", "D1-notetype-rows"}

    def test_three_regions_row_ranges_do_not_overlap(self) -> None:
        ranges = [(s.first_data_row, s.last_data_row) for s in SPECS_D104]
        assert ranges == [(13, 16), (18, 21), (23, 24)]

    def test_third_writer_registered_for_portfolio_key_only(self) -> None:
        """🔴 需求 5.7：只有 portfolio 键有第三写入方，个别计提与票据种类无此冲突。"""
        assert set(THIRD_WRITER_STORE_KEYS) == {"D1-bd-portfolio-rows"}
        assert "syncReversalToD14" in THIRD_WRITER_STORE_KEYS["D1-bd-portfolio-rows"]

    def test_downstream_consumers_are_declared_not_empty(self) -> None:
        """需求 5.8：下游消费方清单非空，零回归判据须覆盖它们而非只验自身读回等值。"""
        assert len(DOWNSTREAM_CONSUMERS_D104) >= 4

    def test_formula_mask_matches_e_k_n_columns_per_region(self) -> None:
        assert SPEC_D104_INDIVIDUAL.formula_mask == ("E13:E16", "K13:K16", "N13:N16")
        assert SPEC_D104_PORTFOLIO.formula_mask == ("E18:E21", "K18:K21", "N18:N21")
