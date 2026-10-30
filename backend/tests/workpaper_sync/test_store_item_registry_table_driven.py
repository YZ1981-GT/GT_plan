# -*- coding: utf-8 -*-
"""同构 rows plan 表驱动注册的逐值与顺序守卫。"""
from __future__ import annotations

import pytest

from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY
from app.services.workpaper_sync.phase5_row_table_sheet import StoreKind

_K = (
    ("k2.other_current_assets_adjustment", "phase5_k2_other_current_assets", "K2-3-adj-entries"),
    ("k3.other_payables_adjustment", "phase5_k3_other_payables", "K3-3-adj-entries"),
    ("k4.other_current_liabilities_adjustment", "phase5_k4_other_current_liabilities", "K4-3-adj-entries"),
    ("k5.provisions_adjustment", "phase5_k5_provisions", "K5-3-entries"),
    ("k6.held_for_sale_adjustment", "phase5_k6_held_for_sale", "K6-3-adj-entries"),
    ("k7.deferred_income_adjustment", "phase5_k7_deferred_income", "K7-3-adj-entries"),
)
_N = (
    ("n1.deferred_tax_assets", "phase5_n1_deferred_tax_assets", "N1-2-detail-rows"),
    ("n2.taxes_payable", "phase5_n2_taxes_payable", "N2-2-detail-rows"),
    ("n3.deferred_tax_liabilities", "phase5_n3_deferred_tax_liabilities", "N3-2-rows"),
    ("n4.taxes_and_surcharges", "phase5_n4_taxes_and_surcharges", "N4-2-detail-rows"),
    ("n5.income_tax_expense", "phase5_n5_income_tax_expense", "N5-2-rows"),
)


@pytest.mark.parametrize(("adapter_id", "provider", "item_id"), _K + _N)
def test_table_driven_plan_values(adapter_id: str, provider: str, item_id: str) -> None:
    plan = STORE_MERGE_REGISTRY[adapter_id]
    assert plan.adapter_id == adapter_id
    assert plan.provider_module == provider
    assert plan.item_ids == (item_id,)
    assert plan.items[0].kind is StoreKind.rows
    assert plan.merge_rows_fn == "merge_projection_into_store_rows"
    assert plan.merge_state_fn is None
    assert plan.dual_store_fn is None
    expected_oo = "neutralize_oo_crash_if_formulas" if adapter_id.startswith("n") else None
    assert plan.oo_crash_neutralization_fn == expected_oo


def test_table_driven_plan_order_is_stable() -> None:
    keys = list(STORE_MERGE_REGISTRY)
    start = keys.index(_K[0][0])
    assert keys[start:start + len(_K) + len(_N)] == [row[0] for row in _K + _N]
