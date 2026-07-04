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
from ._g5_long_term_receivable import render as render_g5_long_term_receivable
from ._g8_other_equity_instruments import render as render_g8_other_equity_instruments
from ._g9_other_noncurrent_financial import render as render_g9_other_noncurrent_financial
from ._g10_trading_financial_liabilities import render as render_g10_trading_financial_liabilities
from ._g11_investment_income import render as render_g11_investment_income
from ._g12_net_hedge_gains import render as render_g12_net_hedge_gains
from ._g13_fair_value_changes import render as render_g13_fair_value_changes
from ._g14_credit_impairment_loss import render as render_g14_credit_impairment_loss
from ._e1_monetary_fund import render as render_e1_monetary_fund

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
    "g5-long-term-receivable": render_g5_long_term_receivable,
    "g8-other-equity-instruments": render_g8_other_equity_instruments,
    "g9-other-noncurrent-financial": render_g9_other_noncurrent_financial,
    "g10-trading-financial-liabilities": render_g10_trading_financial_liabilities,
    "g11-investment-income": render_g11_investment_income,
    "g12-net-hedge-gains": render_g12_net_hedge_gains,
    "g13-fair-value-changes": render_g13_fair_value_changes,
    "g14-credit-impairment-loss": render_g14_credit_impairment_loss,
}
