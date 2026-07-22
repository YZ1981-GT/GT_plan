"""专属组件 /{wp_id}/... 子路由 gate 应用清单（Task 9 DEDICATED-SUB-ROUTE / 组件 C10 EntryIntegration）

Feature: procedure-delegation-visibility-isolation
Requirements: 5.8-5.18, 7.5, 8.5, 8.10-8.12, 8.15, 9, 12.7-12.9

本清单是「按模块」的数据真源：登记 D~N（及 A/B/C/S）**专属科目组件** 的 per-component 路由模块。
这些路由全部形如 ``/api/{module}/{wp_id}/{suffix}``（binding=wp_id），因此可由单一 router-level
依赖 ``dedicated_wp_gate`` 统一接入 Wp_Bound_Gate——一处机制覆盖数百路由，避免逐路由手工接线。

集合由 ``app.security.entry_coverage_scanner`` 生成的 ledger 派生（未迁移 + wp_id 绑定 + 专属科目
组件模块），与 ledger 的 ``gated`` 标记一一对应（Task 16 双向一致）。横切路由（wp_ai/wp_evidence/
attachment/onlyoffice/bulk 等）不在此集合，分别由 Task 9 核心内联 gate 与 Task 10/11 覆盖。
"""
from __future__ import annotations

__all__ = [
    "DEDICATED_COMPONENT_ROUTER_MODULES",
    "is_dedicated_module",
    "router_has_dedicated_module",
]

# endpoint.__module__ 全集（与 ledger entrypoint 的模块段一致）。
DEDICATED_COMPONENT_ROUTER_MODULES: frozenset[str] = frozenset(
    {
        'app.routers.a171_ai_generate',
        'app.routers.a176_docx_sync',
        'app.routers.a177_ai_generate',
        'app.routers.a21_review',
        'app.routers.h7_biological_assets',
        'app.routers.h9_lease_liabilities',
        'app.routers.l1_short_term_loans',
        'app.routers.l2_interest_payable',
        'app.routers.l3_long_term_loans',
        'app.routers.l4_bonds_payable',
        'app.routers.l5_long_term_payables',
        'app.routers.l6_special_payables',
        'app.routers.l7_other_noncurrent_liabilities',
        'app.routers.l8_financial_expenses',
        'app.routers.m10_other_equity_instruments',
        'app.routers.m1_dividends_payable',
        'app.routers.m2_paid_in_capital',
        'app.routers.m3_treasury_stock',
        'app.routers.m4_capital_reserve',
        'app.routers.m5_surplus_reserve',
        'app.routers.m6_retained_earnings',
        'app.routers.m7_special_reserve',
        'app.routers.m8_general_risk_reserve',
        'app.routers.m9_other_comprehensive_income',
        'app.routers.n1_deferred_tax_assets',
        'app.routers.n2_taxes_payable',
        'app.routers.n3_deferred_tax_liabilities',
        'app.routers.n5_income_tax_expense',
        'app.routers.s_estimate_calculation',
        'app.routers.s_transaction_calculation',
        'app.routers.wp_disclosure_sync',
        'app.routers.wp_f2_impairment',
        'app.routers.wp_f2_valuation',
        'app.routers.wp_g_classification',
        'app.routers.wp_g_ecl',
        'app.routers.wp_g_fair_value',
        'app.routers.wp_h_depreciation',
        'app.routers.wp_h_impairment',
        'app.routers.wp_i_amortization',
        'app.routers.wp_i_capitalization',
        'app.routers.wp_i_goodwill',
        'app.routers.wp_j_payroll_calc',
        'app.routers.wp_j_share_payment',
        'app.routers.wp_k_expense_analysis',
        'app.routers.wp_k_impairment_summary',
        'app.routers.wp_l_bond_amortization',
        'app.routers.wp_l_interest_calc',
        'app.routers.wp_m_equity_movement',
        'app.routers.wp_n_income_tax_calc',
        'app.routers.wp_render_strategies._c24_import_export',
        'app.routers.wp_render_strategies._cycle_import_export_common',
        'app.routers.wp_render_strategies._d1_ai_generate',
        'app.routers.wp_render_strategies._d1_disclosure_export',
        'app.routers.wp_render_strategies._d1_import_export._impl',
        'app.routers.wp_render_strategies._d2_ai_generate',
        'app.routers.wp_render_strategies._d2_derecognition',
        'app.routers.wp_render_strategies._d2_import_export',
        'app.routers.wp_render_strategies._d3_ai_generate',
        'app.routers.wp_render_strategies._d3_import_export',
        'app.routers.wp_render_strategies._d4_ai_generate',
        'app.routers.wp_render_strategies._d4_contract_ocr',
        'app.routers.wp_render_strategies._d4_import_export',
        'app.routers.wp_render_strategies._d5_ai_generate',
        'app.routers.wp_render_strategies._d5_import_export',
        'app.routers.wp_render_strategies._d6_ai_generate',
        'app.routers.wp_render_strategies._d6_import_export',
        'app.routers.wp_render_strategies._d7_ai_generate',
        'app.routers.wp_render_strategies._d7_import_export',
        'app.routers.wp_render_strategies._e1_import_export',
        'app.routers.wp_render_strategies._f0_import_export',
        'app.routers.wp_render_strategies._f1_ai_generate',
        'app.routers.wp_render_strategies._f1_import_export',
        'app.routers.wp_render_strategies._f2_contract_ocr',
        'app.routers.wp_render_strategies._f2_import_export',
        'app.routers.wp_render_strategies._f2_inventory_main_ai',
        'app.routers.wp_render_strategies._f2_special_ai',
        'app.routers.wp_render_strategies._f2_special_contract_ocr',
        'app.routers.wp_render_strategies._f2_special_import_export',
        'app.routers.wp_render_strategies._f2_stocktake_ai',
        'app.routers.wp_render_strategies._f2_stocktake_contract_ocr',
        'app.routers.wp_render_strategies._f2_stocktake_import_export',
        'app.routers.wp_render_strategies._f2_valuation_ai',
        'app.routers.wp_render_strategies._f2_valuation_contract_ocr',
        'app.routers.wp_render_strategies._f2_valuation_import_export',
        'app.routers.wp_render_strategies._f3_contract_ocr',
        'app.routers.wp_render_strategies._f3_import_export',
        'app.routers.wp_render_strategies._f3_notes_payable_ai',
        'app.routers.wp_render_strategies._f4_accounts_payable_ai',
        'app.routers.wp_render_strategies._f5_contract_ocr',
        'app.routers.wp_render_strategies._f5_cost_of_sales_ai',
        'app.routers.wp_render_strategies._g0_confirmation_ai',
        'app.routers.wp_render_strategies._g0_confirmation_import_export',
        'app.routers.wp_render_strategies._g10_contract_ocr',
        'app.routers.wp_render_strategies._g10_trading_financial_liabilities_ai',
        'app.routers.wp_render_strategies._g10_trading_financial_liabilities_validate',
        'app.routers.wp_render_strategies._g11_contract_ocr',
        'app.routers.wp_render_strategies._g11_investment_income_ai',
        'app.routers.wp_render_strategies._g11_investment_income_import_export',
        'app.routers.wp_render_strategies._g11_investment_income_validate',
        'app.routers.wp_render_strategies._g12_net_hedge_gains_ai',
        'app.routers.wp_render_strategies._g13_fair_value_changes_ai',
        'app.routers.wp_render_strategies._g14_credit_impairment_loss_ai',
        'app.routers.wp_render_strategies._g1_trading_financial_assets_ai',
        'app.routers.wp_render_strategies._g2_interest_receivable_ai',
        'app.routers.wp_render_strategies._g3_dividend_receivable_ai',
        'app.routers.wp_render_strategies._g4_bond_investment_ecl_ai',
        'app.routers.wp_render_strategies._g4_bond_investment_ecl_import_export',
        'app.routers.wp_render_strategies._g4_bond_investment_main_ai',
        'app.routers.wp_render_strategies._g4_bond_investment_main_import_export',
        'app.routers.wp_render_strategies._g4_bond_investment_sppi_ai',
        'app.routers.wp_render_strategies._g4_bond_investment_sppi_import_export',
        'app.routers.wp_render_strategies._g5_long_term_receivable_ai',
        'app.routers.wp_render_strategies._g6_other_bond_investment_ecl_ai',
        'app.routers.wp_render_strategies._g6_other_bond_investment_ecl_import_export',
        'app.routers.wp_render_strategies._g6_other_bond_investment_main_ai',
        'app.routers.wp_render_strategies._g6_other_bond_investment_main_import_export',
        'app.routers.wp_render_strategies._g6_other_bond_investment_sppi_ai',
        'app.routers.wp_render_strategies._g6_other_bond_investment_sppi_import_export',
        'app.routers.wp_render_strategies._g7_long_term_equity_main_ai',
        'app.routers.wp_render_strategies._g7_long_term_equity_main_import_export',
        'app.routers.wp_render_strategies._g7_long_term_equity_method_ai',
        'app.routers.wp_render_strategies._g7_long_term_equity_method_import_export',
        'app.routers.wp_render_strategies._g7_long_term_equity_subsidiary_ai',
        'app.routers.wp_render_strategies._g7_long_term_equity_subsidiary_import_export',
        'app.routers.wp_render_strategies._g8_contract_ocr',
        'app.routers.wp_render_strategies._g8_other_equity_instruments_ai',
        'app.routers.wp_render_strategies._g8_other_equity_instruments_import_export',
        'app.routers.wp_render_strategies._g8_other_equity_instruments_validate',
        'app.routers.wp_render_strategies._g9_contract_ocr',
        'app.routers.wp_render_strategies._g9_other_noncurrent_financial_ai',
        'app.routers.wp_render_strategies._g9_other_noncurrent_financial_validate',
        'app.routers.wp_render_strategies._h0_confirmation_ai',
        'app.routers.wp_render_strategies._h0_confirmation_import_export',
        'app.routers.wp_render_strategies._h10_asset_disposal_income_ai',
        'app.routers.wp_render_strategies._h10_asset_disposal_income_import_export',
        'app.routers.wp_render_strategies._h10_asset_disposal_income_validate',
        'app.routers.wp_render_strategies._h1_ai_generate',
        'app.routers.wp_render_strategies._h1_depreciation_engine',
        'app.routers.wp_render_strategies._h1_property_ocr',
        'app.routers.wp_render_strategies._h1_stocktake_summary_ocr',
        'app.routers.wp_render_strategies._h1_stocktake_plan_export',
        'app.routers.wp_render_strategies._h2_ai_generate',
        'app.routers.wp_render_strategies._h2_interest_cap_engine',
        'app.routers.wp_render_strategies._h3_ai_generate',
        'app.routers.wp_render_strategies._h3_transfer_engine',
        'app.routers.wp_render_strategies._h3_property_ocr',
        'app.routers.wp_render_strategies._h3_contract_ocr',
        'app.routers.wp_render_strategies._i1_ai_generate',
        'app.routers.wp_render_strategies._i1_amortization_engine',
        'app.routers.wp_render_strategies._i2_ai_generate',
        'app.routers.wp_render_strategies._i2_capitalization_engine',
        'app.routers.wp_render_strategies._i3_ai_generate',
        'app.routers.wp_render_strategies._i3_dcf_engine',
        'app.routers.wp_render_strategies._i4_ai_generate',
        'app.routers.wp_render_strategies._i5_ai_generate',
        'app.routers.wp_render_strategies._i6_ai_generate',
        'app.routers.wp_render_strategies._j1_ai_generate',
        'app.routers.wp_render_strategies._j1_import_export',
        'app.routers.wp_render_strategies._j2_ai_generate',
        'app.routers.wp_render_strategies._j2_import_export',
        'app.routers.wp_render_strategies._j3_ai_generate',
        'app.routers.wp_render_strategies._j3_import_export',
        'app.routers.wp_render_strategies._k0_confirmation_ai',
        'app.routers.wp_render_strategies._k0_confirmation_import_export',
        'app.routers.wp_render_strategies._k10_ai_generate',
        'app.routers.wp_render_strategies._k11_ai_generate',
        'app.routers.wp_render_strategies._k12_ai_generate',
        'app.routers.wp_render_strategies._k13_ai_generate',
        'app.routers.wp_render_strategies._k1_ai_generate',
        'app.routers.wp_render_strategies._k2_ai_generate',
        'app.routers.wp_render_strategies._k3_ai_generate',
        'app.routers.wp_render_strategies._k4_ai_generate',
        'app.routers.wp_render_strategies._k5_ai_generate',
        'app.routers.wp_render_strategies._k6_ai_generate',
        'app.routers.wp_render_strategies._k7_ai_generate',
        'app.routers.wp_render_strategies._k8_ai_generate',
        'app.routers.wp_render_strategies._k9_ai_generate',
        'app.routers.wp_render_strategies._l0_confirmation_ai',
        'app.routers.wp_render_strategies._l0_confirmation_import_export',
    }
)


def is_dedicated_module(module: str | None) -> bool:
    """该 endpoint 模块是否属于专属组件 per-component 路由集合。"""
    return bool(module) and module in DEDICATED_COMPONENT_ROUTER_MODULES


def router_has_dedicated_module(router) -> bool:
    """APIRouter 是否为专属组件路由（其任一 route 的 endpoint 模块在清单内）。

    专属组件路由的全部 route 均来自同一 per-component 模块，故 any == all；用于 registry
    include 时决定是否附加 ``dedicated_wp_gate`` 依赖。
    """
    for route in getattr(router, "routes", []):
        ep = getattr(route, "endpoint", None)
        if ep is not None and getattr(ep, "__module__", None) in DEDICATED_COMPONENT_ROUTER_MODULES:
            return True
    return False


def router_has_wp_id_route(router) -> bool:
    """APIRouter 是否含 ``{wp_id}`` / ``{wp_index_id}`` 路径参数的路由（横切 wp 绑定路由）。

    Task 16 CROSS-CUTTING-WP-GATE：横切 router（wp_ai/wp_editor/wp_review/wp_structure/
    working_paper 等）的部分路由形如 ``.../{wp_id}/...`` —— 与专属组件同为 wp_id 绑定，可由同一
    router-level 依赖 ``dedicated_wp_gate`` 统一接入 Wp_Bound_Gate。``dedicated_wp_gate`` 对无
    ``wp_id``/``wp_index_id`` 路径段的路由是 **安全 no-op**（不改变原生授权），因此对混合 router
    附加该依赖只影响其 wp_id 绑定子路由，绝不误拒非 wp 路由（defense in depth，additive）。
    """
    for route in getattr(router, "routes", []):
        path = getattr(route, "path", "") or ""
        if "{wp_id}" in path or "{wp_index_id}" in path:
            return True
    return False
