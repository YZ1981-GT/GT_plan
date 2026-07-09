"""底稿渲染策略模块

按 componentType 分发的渲染策略函数集合。
主入口 wp_render_config.get_render_config 通过 RENDERER_DISPATCH 调度。
"""

from __future__ import annotations

from typing import Callable

from ._a_program import render as render_a_program
from ._a112_dual import render as render_a112_dual
from ._a115_disclosure import render as render_a115_disclosure
from ._a117_corresponding import render as render_a117_corresponding
from ._a111_subsequent_events_inquiry import render as render_a111_subsequent_events
from ._a173_consultation_record import render as render_a173_consultation_record
from ._a1731_consultation_execution import render as render_a1731_consultation_execution
from ._a174_disagreement_record import render as render_a174_disagreement_record
from ._a176_closing_meeting import render as render_a176_closing_meeting
from ._a177_independence_declaration import render as render_a177_independence_declaration
from ._a181_regulatory_submission import render as render_a181_regulatory_submission
from ._a182_regulatory_communication import render as render_a182_regulatory_communication
from ._a81_other_info_representation import render as render_a81_other_info_representation
from ._a91_deficiency_letter import render as render_a91_deficiency_letter
from ._a92_deficiency_letter_governance import render as render_a92_deficiency_letter_governance
from ._a101_governance_communication import render as render_a101_governance_communication
from ._a121_legal_confirmation import render as render_a121_legal_confirmation
from ._a171_audit_summary import render as render_a171_audit_summary
from ._a1721_kam import render as render_a1721_kam
from ._a271_it_audit_memo import render as render_a271_it_audit_memo
from ._a51_cashflow import render as render_a51_cashflow
from ._a3_8_goodwill import render as render_a3_8_goodwill
from ._b14_due_diligence import render as render_b14_due_diligence
from ._word_template import render as render_word_template
from ._analytical_review import render as render_analytical_review
from ._audit_sheet import render as render_audit_sheet
from ._b_index import render as render_b_index
from ._c_note import render as render_c_note
from ._checklist import render as render_checklist
from ._review_checklist import render as render_review_checklist
from ._univer_grid import render as render_univer_grid
from ._d1_notes_receivable import render as render_d1_notes_receivable
from ._d2_accounts_receivable import render as render_d2_accounts_receivable
from ._d4_operating_revenue import render as render_d4_operating_revenue
from ._d3_prepaid_accounts import render as render_d3_prepaid_accounts
from ._d5_receivables_financing import render as render_d5_receivables_financing
from ._d6_contract_assets import render as render_d6_contract_assets
from ._d7_contract_liabilities import render as render_d7_contract_liabilities
from ._f1_prepayment import render as render_f1_prepayment
from ._f2_inventory_main import render as render_f2_inventory_main
from ._f2_inventory_valuation_impairment import render as render_f2_inventory_valuation_impairment
from ._f2_inventory_special import render as render_f2_inventory_special
from ._f2_stocktake import render as render_f2_stocktake
from ._g1_trading_financial_assets import render as render_g1_trading_financial_assets
from ._f3_notes_payable import render as render_f3_notes_payable
from ._f4_accounts_payable import render as render_f4_accounts_payable
from ._f5_cost_of_sales import render as render_f5_cost_of_sales
from ._g2_interest_receivable import render as render_g2_interest_receivable
from ._g3_dividend_receivable import render as render_g3_dividend_receivable
from ._g4_bond_investment_main import render as render_g4_bond_investment_main
from ._g4_bond_investment_sppi import render as render_g4_bond_investment_sppi
from ._g4_bond_investment_ecl import render as render_g4_bond_investment_ecl
from ._g5_long_term_receivable import render as render_g5_long_term_receivable
from ._g6_other_bond_investment_main import render as render_g6_other_bond_investment_main
from ._g6_other_bond_investment_sppi import render as render_g6_other_bond_investment_sppi
from ._g6_other_bond_investment_ecl import render as render_g6_other_bond_investment_ecl
from ._g7_long_term_equity_main import render as render_g7_long_term_equity_main
from ._g7_long_term_equity_method import render as render_g7_long_term_equity_method
from ._g7_long_term_equity_subsidiary import render as render_g7_long_term_equity_subsidiary
from ._g8_other_equity_instruments import render as render_g8_other_equity_instruments
from ._g9_other_noncurrent_financial import render as render_g9_other_noncurrent_financial
from ._g10_trading_financial_liabilities import render as render_g10_trading_financial_liabilities
from ._g11_investment_income import render as render_g11_investment_income
from ._g12_net_hedge_gains import render as render_g12_net_hedge_gains
from ._g13_fair_value_changes import render as render_g13_fair_value_changes
from ._g14_credit_impairment_loss import render as render_g14_credit_impairment_loss
from ._h10_asset_disposal_income import render as render_h10_asset_disposal_income
from ._e1_monetary_fund import render as render_e1_monetary_fund
from ._g0_confirmation import render_g0_diff_securities, render_g0_alternative
from ._h0_confirmation import render_h0_alternative
from ._c1_entity_level_control import render as render_c1_entity_level_control
from ._c_control_test import render as render_c_control_test
from ._c22_itgc import render as render_c22_itgc
from ._c23_journal_control import render as render_c23_journal_control
from ._c24_journal_detail import render as render_c24_journal_detail
from ._c25_internal_audit import render as render_c25_internal_audit
from ._c26_info_processing import render as render_c26_info_processing
from ._l1_short_term_loans import render as render_l1_short_term_loans
from ._l2_interest_payable import render as render_l2_interest_payable
from ._l3_long_term_loans import render as render_l3_long_term_loans
from ._l4_bonds_payable import render as render_l4_bonds_payable
from ._l5_long_term_payables import render as render_l5_long_term_payables
from ._l6_special_payables import render as render_l6_special_payables
from ._l7_other_noncurrent_liabilities import render as render_l7_other_noncurrent_liabilities
from ._l8_financial_expenses import render as render_l8_financial_expenses
from ._m1_dividends_payable import render as render_m1_dividends_payable
from ._m2_paid_in_capital import render as render_m2_paid_in_capital
from ._m3_treasury_stock import render as render_m3_treasury_stock
from ._m4_capital_reserve import render as render_m4_capital_reserve
from ._m5_surplus_reserve import render as render_m5_surplus_reserve
from ._m6_retained_earnings import render as render_m6_retained_earnings
from ._m7_special_reserve import render as render_m7_special_reserve
from ._m8_general_risk_reserve import render as render_m8_general_risk_reserve
from ._m9_other_comprehensive_income import render as render_m9_other_comprehensive_income
from ._n1_deferred_tax_assets import render as render_n1_deferred_tax_assets
from ._n2_taxes_payable import render as render_n2_taxes_payable
from ._n3_deferred_tax_liabilities import render as render_n3_deferred_tax_liabilities
from ._n5_income_tax_expense import render as render_n5_income_tax_expense
from ._m10_other_equity_instruments import render as render_m10_other_equity_instruments
from ._s3_policy_change import render as render_s3_policy_change
from ._s4_nonmonetary_exchange import render as render_s4_nonmonetary_exchange
from ._s5_debt_restructuring import render as render_s5_debt_restructuring
from ._s6_fund_occupation import render as render_s6_fund_occupation
from ._s12_cpa_expert import render as render_s12_cpa_expert
from ._s13_mgmt_expert import render as render_s13_mgmt_expert
from ._s14_accounting_estimate import render as render_s14_accounting_estimate
from ._s15_eps_roe import render as render_s15_eps_roe
from ._s20_revenue_deduction import render as render_s20_revenue_deduction
from ._s21_data_asset import render as render_s21_data_asset

# 策略函数签名: async def render(ctx: RenderContext) -> dict | None
# 各策略文件在后续 task 中逐一实现后注册到此 dict
RENDERER_DISPATCH: dict[str, Callable] = {
    "b-index": render_b_index,
    "a-program-console": render_a_program,
    "a1-dashboard": render_a_program,
    "a1-12-dual-checklist": render_a112_dual,
    "a1-15-disclosure-checklist": render_a115_disclosure,
    "a1-17-corresponding-data": render_a117_corresponding,
    "a17-6-closing-meeting": render_a176_closing_meeting,
    "a17-3-consultation-record": render_a173_consultation_record,
    "a17-3-1-consultation-execution": render_a1731_consultation_execution,
    "a17-4-disagreement-record": render_a174_disagreement_record,
    "a17-7-independence-declaration": render_a177_independence_declaration,
    "a11-1-subsequent-events-inquiry": render_a111_subsequent_events,
    "a18-1-regulatory-submission": render_a181_regulatory_submission,
    "a18-2-regulatory-communication": render_a182_regulatory_communication,
    "a8-1-other-info-representation": render_a81_other_info_representation,
    "a9-1-deficiency-letter": render_a91_deficiency_letter,
    "a9-2-deficiency-letter-governance": render_a92_deficiency_letter_governance,
    "a27-1-it-audit-memo": render_a271_it_audit_memo,
    "a10-1-governance-communication": render_a101_governance_communication,
    "a12-1-legal-confirmation": render_a121_legal_confirmation,
    "a17-1-audit-summary": render_a171_audit_summary,
    "a17-2-1-kam": render_a1721_kam,
    "a5-1-cashflow-audit": render_a51_cashflow,
    "a3-8-goodwill-impairment": render_a3_8_goodwill,
    "b1-4-due-diligence-report": render_b14_due_diligence,
    "a2-adjustment-console": render_a_program,
    "a3-consolidation-console": render_a_program,
    "audit-sheet": render_audit_sheet,
    "checklist-table": render_checklist,
    "review-checklist": render_review_checklist,
    "analytical-review": render_analytical_review,
    "c-note-table": render_c_note,
    "univer": render_univer_grid,
    "word-template": render_word_template,
    "d1-notes-receivable": render_d1_notes_receivable,
    "d2-accounts-receivable": render_d2_accounts_receivable,
    "d4-operating-revenue": render_d4_operating_revenue,
    "d3-prepaid-accounts": render_d3_prepaid_accounts,
    "d5-receivables-financing": render_d5_receivables_financing,
    "d6-contract-assets": render_d6_contract_assets,
    "d7-contract-liabilities": render_d7_contract_liabilities,
    "e1-monetary-fund": render_e1_monetary_fund,
    "f1-prepayment": render_f1_prepayment,
    "f2-inventory-main": render_f2_inventory_main,
    "f2-inventory-valuation-impairment": render_f2_inventory_valuation_impairment,
    "f2-inventory-special": render_f2_inventory_special,
    "f2-stocktake-bundle": render_f2_stocktake,
    "g1-trading-financial-assets": render_g1_trading_financial_assets,
    "f3-notes-payable": render_f3_notes_payable,
    "f4-accounts-payable": render_f4_accounts_payable,
    "f5-cost-of-sales": render_f5_cost_of_sales,
    "g2-interest-receivable": render_g2_interest_receivable,
    "g3-dividend-receivable": render_g3_dividend_receivable,
    "g4-bond-investment-main": render_g4_bond_investment_main,
    "g4-bond-investment-sppi": render_g4_bond_investment_sppi,
    "g4-bond-investment-ecl": render_g4_bond_investment_ecl,
    "g5-long-term-receivable": render_g5_long_term_receivable,
    "g6-other-bond-investment-main": render_g6_other_bond_investment_main,
    "g6-other-bond-investment-sppi": render_g6_other_bond_investment_sppi,
    "g6-other-bond-investment-ecl": render_g6_other_bond_investment_ecl,
    "g7-long-term-equity-main": render_g7_long_term_equity_main,
    "g7-long-term-equity-method": render_g7_long_term_equity_method,
    "g7-long-term-equity-subsidiary": render_g7_long_term_equity_subsidiary,
    "g8-other-equity-instruments": render_g8_other_equity_instruments,
    "g9-other-noncurrent-financial": render_g9_other_noncurrent_financial,
    "g10-trading-financial-liabilities": render_g10_trading_financial_liabilities,
    "g11-investment-income": render_g11_investment_income,
    "g12-net-hedge-gains": render_g12_net_hedge_gains,
    "g13-fair-value-changes": render_g13_fair_value_changes,
    "g14-credit-impairment-loss": render_g14_credit_impairment_loss,
    "h10-asset-disposal-income": render_h10_asset_disposal_income,
    "confirmation-diff-securities": render_g0_diff_securities,
    "confirmation-alternative-g06": render_g0_alternative,
    "confirmation-alternative-h05": render_h0_alternative,
    "c1-entity-level-control": render_c1_entity_level_control,
    "c-control-test": render_c_control_test,
    "c22-itgc-bundle": render_c22_itgc,
    "c23-journal-entry-control": render_c23_journal_control,
    "c24-journal-entry-detail": render_c24_journal_detail,
    "c25-internal-audit-reliance": render_c25_internal_audit,
    "c26-info-processing-control": render_c26_info_processing,
    "l1-short-term-loans": render_l1_short_term_loans,
    "l2-interest-payable": render_l2_interest_payable,
    "l3-long-term-loans": render_l3_long_term_loans,
    "l4-bonds-payable": render_l4_bonds_payable,
    "l5-long-term-payables": render_l5_long_term_payables,
    "l6-special-payables": render_l6_special_payables,
    "l7-other-noncurrent-liabilities": render_l7_other_noncurrent_liabilities,
    "l8-financial-expenses": render_l8_financial_expenses,
    "m1-dividends-payable": render_m1_dividends_payable,
    "m2-paid-in-capital": render_m2_paid_in_capital,
    "m3-treasury-stock": render_m3_treasury_stock,
    "m4-capital-reserve": render_m4_capital_reserve,
    "m5-surplus-reserve": render_m5_surplus_reserve,
    "m6-retained-earnings": render_m6_retained_earnings,
    "m7-special-reserve": render_m7_special_reserve,
    "m8-general-risk-reserve": render_m8_general_risk_reserve,
    "m9-other-comprehensive-income": render_m9_other_comprehensive_income,
    "m10-other-equity-instruments": render_m10_other_equity_instruments,
    "n1-deferred-tax-assets": render_n1_deferred_tax_assets,
    "n2-taxes-payable": render_n2_taxes_payable,
    "n3-deferred-tax-liabilities": render_n3_deferred_tax_liabilities,
    "n5-income-tax-expense": render_n5_income_tax_expense,
    "s3-policy-change": render_s3_policy_change,
    "s4-nonmonetary-exchange": render_s4_nonmonetary_exchange,
    "s5-debt-restructuring": render_s5_debt_restructuring,
    "s6-fund-occupation": render_s6_fund_occupation,
    "s12-cpa-expert": render_s12_cpa_expert,
    "s13-mgmt-expert": render_s13_mgmt_expert,
    "s14-accounting-estimate": render_s14_accounting_estimate,
    "s15-eps-roe": render_s15_eps_roe,
    "s20-revenue-deduction": render_s20_revenue_deduction,
    "s21-data-asset": render_s21_data_asset,
}
