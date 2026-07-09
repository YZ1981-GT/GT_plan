"""底稿管理路由注册 — 按 6 大聚合组 + 辅助组循环注册

分组方案（design §7.1）：
  模板管理: wp_template / wp_template_metadata / wp_template_files / wp_template_xlsx / wp_template_docx / wp_template_download / wp_template_version
  生命周期: working_paper / workpaper_batch_status / wp_batch_ops / wp_progress / wp_prerequisite_status / wp_procedure_status
  复核:     wp_review / wp_review_status / wp_cell_annotations / review_records_global / wp_eqcr_evaluation
  渲染:     wp_render_config / wp_classification / wp_html_save / wp_xlsx_export / wp_index_resolve / wp_trace / wp_disclosure_sync
  数据:     formula / wp_mapping / wp_data_rules / wp_prefill_context / wp_prefill_preview / wp_user_formulas / wp_cross_check / wp_dependencies / sampling / sampling_enhanced / cutoff_sampling / voucher_sampling / aging_analysis / data_fetch_custom
  搜索:     wp_search / wp_version_search / global_search / wp_health_dashboard
  程序管理: wp_procedures / wp_procedure_trim / wp_step_mapping / wp_evidence
  AI与辅助: wp_ai / wp_ai_confirm / wp_chat / wp_explanation
  其他:     qc / wp_storage / wp_download / workpaper_summary / process_record / review_conversations / annotations / background_jobs / wp_data_rules / excel_html / wp_structure / wp_manuals / wp_fine_rules
"""
from fastapi import FastAPI


def register_workpaper_routers(app: FastAPI) -> None:
    """注册底稿管理相关路由（6 大聚合组 + 辅助组，循环注册）"""
    from app.routers.wp_template import router as wp_template
    from app.routers.wp_template_metadata import router as wp_template_metadata
    from app.routers.wp_template_files import router as wp_template_files
    from app.routers.wp_template_xlsx import router as wp_template_xlsx
    from app.routers.wp_template_docx import router as wp_template_docx
    from app.routers.wp_template_download import router as wp_template_download
    from app.routers.wp_template_version import router as wp_template_version
    from app.routers.wp_template_list import router as wp_template_list
    from app.routers.working_paper import router as working_paper
    from app.routers.wp_editor_router import router as wp_editor
    from app.routers.wp_batch_router import router as wp_batch_domain
    from app.routers.wp_relation_router import router as wp_relation_domain
    from app.routers.wp_review_router import router as wp_review_domain
    from app.routers.workpaper_batch_status import router as workpaper_batch_status
    from app.routers.wp_batch_ops import router as wp_batch_ops
    from app.routers.wp_progress import router as wp_progress
    from app.routers.wp_prerequisite_status import router as wp_prerequisite_status
    from app.routers.wp_procedure_status import router as wp_procedure_status
    from app.routers.wp_procedure_status import categories_router as wp_procedure_categories
    from app.routers.wp_review import router as wp_review
    from app.routers.wp_review_status import router as wp_review_status
    from app.routers.wp_cell_annotations import router as wp_cell_annotations
    from app.routers.review_records_global import router as review_records_global
    from app.routers.wp_eqcr_evaluation import router as wp_eqcr_evaluation
    from app.routers.wp_render_config import router as wp_render_config
    from app.routers.wp_classification import router as wp_classification
    from app.routers.wp_html_save import router as wp_html_save
    from app.routers.wp_xlsx_export import router as wp_xlsx_export
    from app.routers.wp_index_resolve import router as wp_index_resolve
    from app.routers.wp_trace import router as wp_trace
    from app.routers.wp_disclosure_sync import router as wp_disclosure_sync
    from app.routers.formula import router as formula
    from app.routers.wp_mapping import router as wp_mapping
    from app.routers.wp_data_rules import router as wp_data_rules
    from app.routers.wp_prefill_context import router as wp_prefill_context
    from app.routers.wp_prefill_preview import router as wp_prefill_preview
    from app.routers.wp_user_formulas import router as wp_user_formulas
    from app.routers.wp_cross_check import router as wp_cross_check
    from app.routers.wp_dependencies import router as wp_dependencies
    from app.routers.sampling import router as sampling
    from app.routers.sampling_enhanced import router as sampling_enhanced
    from app.routers.aging_analysis import router as aging_analysis
    from app.routers.data_fetch_custom import router as data_fetch_custom
    from app.routers.wp_search import router as wp_search
    from app.routers.wp_version_search import router as wp_version_search
    from app.routers.global_search import router as global_search
    from app.routers.wp_health_dashboard import router as wp_health_dashboard
    from app.routers.wp_procedures import router as wp_procedures
    from app.routers.wp_procedure_trim import router as wp_procedure_trim
    from app.routers.wp_step_mapping import router as wp_step_mapping
    from app.routers.wp_evidence import router as wp_evidence
    from app.routers.wp_ai import router as wp_ai
    from app.routers.wp_ai_confirm import router as wp_ai_confirm
    from app.routers.wp_chat import router as wp_chat
    from app.routers.wp_explanation import router as wp_explanation
    from app.routers.qc import router as qc
    from app.routers.wp_storage import router as wp_storage
    from app.routers.wp_download import router as wp_download
    from app.routers.workpaper_summary import router as workpaper_summary
    from app.routers.process_record import router as process_record
    from app.routers.review_conversations import router as review_conversations
    from app.routers.annotations import router as annotations
    from app.routers.background_jobs import router as background_jobs
    from app.routers.excel_html import router as excel_html
    from app.routers.wp_structure import router as wp_structure
    from app.routers.wp_manuals import router as wp_manuals
    from app.routers.wp_fine_rules import router as wp_fine_rules
    from app.routers.wp_offline import router as wp_offline
    from app.routers.wp_audit_flow_graph import router as wp_audit_flow_graph
    from app.routers.wp_sheet_lock import router as wp_sheet_lock
    from app.routers.standard_conversion import router as standard_conversion
    from app.routers.attachment_lineage import router as attachment_lineage
    from app.routers.wp_functional_actions import router as wp_functional_actions
    from app.routers.wp_formula import router as wp_formula
    from app.routers.bad_debt_rows import router as bad_debt_rows
    from app.routers.account_packages import router as account_packages
    from app.routers.wp_export_import_router import router as wp_export_import
    from app.routers.wp_template_copy_router import router as wp_template_copy
    from app.routers.cf_verification import router as cf_verification
    from app.routers.review_workflow import router as review_workflow_router, signing_router, my_signing_router
    from app.routers.wp_procedure_tables import router as wp_procedure_tables
    from app.routers.wp_field_overrides import router as wp_field_overrides
    from app.routers.wp_report_analysis import router as wp_report_analysis
    from app.routers.wp_misstatement import router as wp_misstatement
    from app.routers.checklist_responses import router as checklist_responses
    from app.routers.completion_phase import router as completion_phase
    from app.routers.a17_summary import router as a17_summary
    from app.routers.a18_regulatory import router as a18_regulatory
    from app.routers.b14_ai_generate import router as b14_ai_generate
    from app.routers.a171_ai_generate import router as a171_ai_generate
    from app.routers.a177_ai_generate import router as a177_ai_generate
    from app.routers.a176_docx_sync import router as a176_docx_sync
    from app.routers.a21_review import router as a21_review
    from app.routers.wp_export_word import router as wp_export_word
    from app.routers.b5_version import router as b5_version
    from app.routers.analytical_review_save import router as analytical_review_save
    from app.routers.wp_render_strategies._d1_import_export import router as d1_import_export
    from app.routers.wp_render_strategies._d1_ai_generate import router as d1_ai_generate
    from app.routers.wp_render_strategies._d2_import_export import router as d2_import_export
    from app.routers.wp_render_strategies._d2_ai_generate import router as d2_ai_generate
    from app.routers.wp_render_strategies._d1_disclosure_export import router as d1_disclosure_export
    from app.routers.wp_render_strategies._d3_import_export import router as d3_import_export
    from app.routers.wp_render_strategies._d3_ai_generate import router as d3_ai_generate
    from app.routers.wp_render_strategies._d4_import_export import router as d4_import_export
    from app.routers.wp_render_strategies._d4_ai_generate import router as d4_ai_generate
    from app.routers.wp_render_strategies._d4_contract_ocr import router as d4_contract_ocr
    from app.routers.wp_render_strategies._d5_import_export import router as d5_import_export
    from app.routers.wp_render_strategies._d5_ai_generate import router as d5_ai_generate
    from app.routers.wp_render_strategies._d6_import_export import router as d6_import_export
    from app.routers.wp_render_strategies._d6_ai_generate import router as d6_ai_generate
    from app.routers.wp_render_strategies._d7_import_export import router as d7_import_export
    from app.routers.wp_render_strategies._d7_ai_generate import router as d7_ai_generate
    from app.routers.wp_render_strategies._e1_import_export import router as e1_import_export
    from app.routers.wp_render_strategies._f1_import_export import router as f1_import_export
    from app.routers.wp_render_strategies._f2_import_export import router as f2_import_export
    from app.routers.wp_render_strategies._f2_inventory_main_ai import router as f2_ai_generate
    from app.routers.wp_render_strategies._f2_contract_ocr import router as f2_contract_ocr
    from app.routers.wp_render_strategies._f2_valuation_import_export import router as f2_val_import_export
    from app.routers.wp_render_strategies._f2_valuation_ai import router as f2_val_ai_generate
    from app.routers.wp_render_strategies._f2_special_import_export import router as f2_spe_import_export
    from app.routers.wp_render_strategies._f2_stocktake_import_export import router as f2_st_import_export
    from app.routers.wp_render_strategies._f2_stocktake_contract_ocr import router as f2_st_contract_ocr
    from app.routers.wp_render_strategies._f2_stocktake_ai import router as f2_st_ai_generate
    from app.routers.wp_render_strategies._f2_special_ai import router as f2_spe_ai_generate
    from app.routers.wp_render_strategies._f2_special_contract_ocr import router as f2_spe_contract_ocr
    from app.routers.wp_render_strategies._f2_valuation_contract_ocr import router as f2_val_contract_ocr
    from app.routers.wp_render_strategies._f3_import_export import router as f3_import_export
    from app.routers.wp_render_strategies._f3_notes_payable_ai import router as f3_ai_generate
    from app.routers.wp_render_strategies._f3_contract_ocr import router as f3_contract_ocr
    from app.routers.wp_render_strategies._f4_import_export import router as f4_import_export
    from app.routers.wp_render_strategies._f4_accounts_payable_ai import router as f4_ai_generate
    from app.routers.wp_render_strategies._f5_import_export import router as f5_import_export
    from app.routers.wp_render_strategies._f5_cost_of_sales_ai import router as f5_ai_generate
    from app.routers.wp_render_strategies._f5_contract_ocr import router as f5_contract_ocr
    from app.routers.wp_render_strategies._g0_confirmation_import_export import router as g0_import_export
    from app.routers.wp_render_strategies._g0_confirmation_ai import router as g0_ai_generate
    from app.routers.wp_render_strategies._h0_confirmation_import_export import router as h0_import_export
    from app.routers.wp_render_strategies._h0_confirmation_ai import router as h0_ai_generate
    from app.routers.wp_render_strategies._g1_trading_financial_assets_import_export import router as g1_import_export
    from app.routers.wp_render_strategies._g1_trading_financial_assets_ai import router as g1_ai_generate
    from app.routers.wp_render_strategies._g2_interest_receivable_import_export import router as g2_import_export
    from app.routers.wp_render_strategies._g2_interest_receivable_ai import router as g2_ai_generate
    from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import router as g3_import_export
    from app.routers.wp_render_strategies._g3_dividend_receivable_ai import router as g3_ai_generate
    from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import router as g4_main_import_export
    from app.routers.wp_render_strategies._g4_bond_investment_main_ai import router as g4_main_ai_generate
    from app.routers.wp_render_strategies._g4_bond_investment_sppi_import_export import router as g4_sppi_import_export
    from app.routers.wp_render_strategies._g4_bond_investment_sppi_ai import router as g4_sppi_ai_generate
    from app.routers.wp_render_strategies._g4_bond_investment_ecl_import_export import router as g4_ecl_import_export
    from app.routers.wp_render_strategies._g4_bond_investment_ecl_ai import router as g4_ecl_ai_generate
    from app.routers.wp_render_strategies._g6_other_bond_investment_main_import_export import router as g6_main_import_export
    from app.routers.wp_render_strategies._g6_other_bond_investment_main_ai import router as g6_main_ai_generate
    from app.routers.wp_render_strategies._g6_other_bond_investment_sppi_import_export import router as g6_sppi_import_export
    from app.routers.wp_render_strategies._g6_other_bond_investment_sppi_ai import router as g6_sppi_ai_generate
    from app.routers.wp_render_strategies._g6_other_bond_investment_ecl_import_export import router as g6_ecl_import_export
    from app.routers.wp_render_strategies._g6_other_bond_investment_ecl_ai import router as g6_ecl_ai_generate
    from app.routers.wp_render_strategies._g7_long_term_equity_main_import_export import router as g7_main_import_export
    from app.routers.wp_render_strategies._g7_long_term_equity_main_ai import router as g7_main_ai_generate
    from app.routers.wp_render_strategies._g7_long_term_equity_method_import_export import router as g7_method_import_export
    from app.routers.wp_render_strategies._g7_long_term_equity_method_ai import router as g7_method_ai_generate
    from app.routers.wp_render_strategies._g7_long_term_equity_subsidiary_import_export import router as g7_sub_import_export
    from app.routers.wp_render_strategies._g7_long_term_equity_subsidiary_ai import router as g7_sub_ai_generate
    from app.routers.wp_render_strategies._g12_net_hedge_gains_import_export import router as g12_import_export
    from app.routers.wp_render_strategies._g12_net_hedge_gains_ai import router as g12_ai_generate
    from app.routers.wp_render_strategies._g13_fair_value_changes_import_export import router as g13_import_export
    from app.routers.wp_render_strategies._g13_fair_value_changes_ai import router as g13_ai_generate
    from app.routers.wp_render_strategies._g14_credit_impairment_loss_import_export import router as g14_import_export
    from app.routers.wp_render_strategies._g14_credit_impairment_loss_ai import router as g14_ai_generate
    from app.routers.wp_render_strategies._g8_other_equity_instruments_import_export import router as g8_import_export
    from app.routers.wp_render_strategies._g8_other_equity_instruments_validate import router as g8_validate
    from app.routers.wp_render_strategies._g8_other_equity_instruments_ai import router as g8_ai_generate
    from app.routers.wp_render_strategies._g8_contract_ocr import router as g8_contract_ocr
    from app.routers.wp_render_strategies._g9_other_noncurrent_financial_import_export import router as g9_import_export
    from app.routers.wp_render_strategies._g9_other_noncurrent_financial_validate import router as g9_validate
    from app.routers.wp_render_strategies._g9_other_noncurrent_financial_ai import router as g9_ai_generate
    from app.routers.wp_render_strategies._g9_contract_ocr import router as g9_contract_ocr
    from app.routers.wp_render_strategies._g10_trading_financial_liabilities_import_export import router as g10_import_export
    from app.routers.wp_render_strategies._g10_trading_financial_liabilities_ai import router as g10_ai_generate
    from app.routers.wp_render_strategies._g10_trading_financial_liabilities_validate import router as g10_validate
    from app.routers.wp_render_strategies._g10_contract_ocr import router as g10_contract_ocr
    from app.routers.wp_render_strategies._g11_investment_income_import_export import router as g11_import_export
    from app.routers.wp_render_strategies._g11_investment_income_ai import router as g11_ai_generate
    from app.routers.wp_render_strategies._g11_contract_ocr import router as g11_contract_ocr
    from app.routers.wp_render_strategies._g11_investment_income_validate import router as g11_validate
    from app.routers.wp_render_strategies._h10_asset_disposal_income_import_export import router as h10_import_export
    from app.routers.wp_render_strategies._h10_asset_disposal_income_validate import router as h10_validate
    from app.routers.wp_render_strategies._h10_asset_disposal_income_ai import router as h10_ai_generate
    from app.routers.wp_render_strategies._g5_long_term_receivable_import_export import router as g5_import_export
    from app.routers.wp_render_strategies._g5_long_term_receivable_ai import router as g5_ai_generate
    from app.routers.l1_short_term_loans import router as l1_import_export
    from app.routers.wp_render_strategies._c24_import_export import router as c24_import_export
    from app.routers.l2_interest_payable import router as l2_interest_payable
    from app.routers.l3_long_term_loans import router as l3_long_term_loans
    from app.routers.l4_bonds_payable import router as l4_bonds_payable
    from app.routers.l5_long_term_payables import router as l5_long_term_payables
    from app.routers.l6_special_payables import router as l6_special_payables
    from app.routers.l7_other_noncurrent_liabilities import router as l7_other_noncurrent_liabilities
    from app.routers.l8_financial_expenses import router as l8_financial_expenses
    from app.routers.m1_dividends_payable import router as m1_dividends_payable
    from app.routers.m2_paid_in_capital import router as m2_paid_in_capital
    from app.routers.m3_treasury_stock import router as m3_treasury_stock
    from app.routers.m4_capital_reserve import router as m4_capital_reserve
    from app.routers.m5_surplus_reserve import router as m5_surplus_reserve
    from app.routers.m6_retained_earnings import router as m6_retained_earnings
    from app.routers.m7_special_reserve import router as m7_special_reserve
    from app.routers.m8_general_risk_reserve import router as m8_general_risk_reserve
    from app.routers.m9_other_comprehensive_income import router as m9_other_comprehensive_income
    from app.routers.m10_other_equity_instruments import router as m10_other_equity_instruments
    from app.routers.n1_deferred_tax_assets import router as n1_deferred_tax_assets
    from app.routers.n2_taxes_payable import router as n2_taxes_payable
    from app.routers.n3_deferred_tax_liabilities import router as n3_deferred_tax_liabilities
    from app.routers.n5_income_tax_expense import router as n5_income_tax_expense
    from app.routers.s_estimate_calculation import router as s_estimate_calculation
    from app.routers.s_transaction_calculation import router as s_transaction_calculation
    from app.routers.s34_checklist_router import router as s34_checklist
    from app.routers.issue_hints import router as issue_hints
    from app.routers.workpaper_summaries import router as workpaper_summaries
    from app.routers.wp_render_registry import router as wp_render_registry
    from app.routers.wp_onlyoffice_router import router as wp_onlyoffice
    from app.routers.cutoff_sampling import router as cutoff_sampling
    from app.routers.voucher_sampling import router as voucher_sampling

    groups = {
        # ── 6 大聚合组（design §7.1）──
        "模板管理": [wp_template, wp_template_metadata, wp_template_files, wp_template_xlsx, wp_template_docx, wp_template_download, wp_template_version, wp_template_list],
        "生命周期": [working_paper, wp_editor, wp_batch_domain, wp_relation_domain, workpaper_batch_status, wp_batch_ops, wp_progress, wp_prerequisite_status, wp_procedure_status, wp_procedure_categories],
        "复核": [wp_review_domain, wp_review, wp_review_status, wp_cell_annotations, review_records_global, wp_eqcr_evaluation, review_workflow_router, signing_router, my_signing_router],
        "渲染": [wp_render_config, wp_classification, wp_html_save, wp_xlsx_export, wp_index_resolve, wp_trace, wp_disclosure_sync, wp_onlyoffice],
        "数据": [formula, wp_mapping, wp_data_rules, wp_prefill_context, wp_prefill_preview, wp_user_formulas, wp_formula, bad_debt_rows, wp_cross_check, wp_dependencies, sampling, sampling_enhanced, cutoff_sampling, voucher_sampling, aging_analysis, data_fetch_custom, cf_verification, wp_procedure_tables, wp_field_overrides, wp_report_analysis, wp_misstatement, checklist_responses, completion_phase, a17_summary, a18_regulatory, a21_review, wp_export_word, b5_version, analytical_review_save, d1_disclosure_export, d1_import_export, d2_import_export, d3_import_export, d4_import_export, d5_import_export, d6_import_export, d7_import_export, e1_import_export, f1_import_export, f2_import_export, f2_val_import_export, f2_spe_import_export, f2_st_import_export, f3_import_export, f4_import_export, f5_import_export, g0_import_export, h0_import_export, g1_import_export, g2_import_export, g3_import_export, g4_main_import_export, g4_sppi_import_export, g4_ecl_import_export, g5_import_export, g6_main_import_export, g6_sppi_import_export, g6_ecl_import_export, g7_main_import_export, g7_method_import_export, g7_sub_import_export, g8_import_export, g8_validate, g9_import_export, g9_validate, g10_import_export, g10_validate, g11_import_export, g11_validate, g12_import_export, g13_import_export, g14_import_export, h10_import_export, h10_validate, l1_import_export, c24_import_export, l2_interest_payable, l3_long_term_loans, l4_bonds_payable, l5_long_term_payables, l6_special_payables, l7_other_noncurrent_liabilities, l8_financial_expenses, m1_dividends_payable, m2_paid_in_capital, m3_treasury_stock, m4_capital_reserve, m5_surplus_reserve, m6_retained_earnings, m7_special_reserve, m8_general_risk_reserve, m9_other_comprehensive_income, m10_other_equity_instruments, n1_deferred_tax_assets, n2_taxes_payable, n3_deferred_tax_liabilities, n5_income_tax_expense, s_estimate_calculation, s_transaction_calculation, s34_checklist],
        "搜索": [wp_search, wp_version_search, global_search, wp_health_dashboard],
        # ── 辅助组 ──
        "程序管理": [wp_procedures, wp_procedure_trim, wp_step_mapping, wp_evidence],
        "AI与辅助": [wp_ai, wp_ai_confirm, wp_chat, wp_explanation, b14_ai_generate, a171_ai_generate, a177_ai_generate, a176_docx_sync, d1_ai_generate, d2_ai_generate, d3_ai_generate, d4_ai_generate, d4_contract_ocr, d5_ai_generate, d6_ai_generate, d7_ai_generate, f2_ai_generate, f2_contract_ocr, f2_val_ai_generate, f2_val_contract_ocr, f2_spe_ai_generate, f2_spe_contract_ocr, f2_st_ai_generate, f2_st_contract_ocr, f3_ai_generate, f3_contract_ocr, f4_ai_generate, f5_ai_generate, f5_contract_ocr, g0_ai_generate, h0_ai_generate, g1_ai_generate, g2_ai_generate, g3_ai_generate, g4_main_ai_generate, g4_sppi_ai_generate, g4_ecl_ai_generate, g5_ai_generate, g6_main_ai_generate, g6_sppi_ai_generate, g6_ecl_ai_generate, g7_main_ai_generate, g7_method_ai_generate, g7_sub_ai_generate, g8_ai_generate, g8_contract_ocr, g9_ai_generate, g9_contract_ocr, g10_ai_generate, g10_contract_ocr, g11_ai_generate, g11_contract_ocr, g12_ai_generate, g13_ai_generate, g14_ai_generate, h10_ai_generate],
        "其他": [qc, wp_storage, wp_download, wp_export_import, wp_template_copy, workpaper_summary, process_record, review_conversations, annotations, background_jobs, excel_html, wp_structure, wp_manuals, wp_fine_rules, wp_offline, wp_audit_flow_graph, wp_sheet_lock, standard_conversion, attachment_lineage, wp_functional_actions, issue_hints, workpaper_summaries, wp_render_registry],
        "科目工作包": [account_packages],
    }

    for tag, routers in groups.items():
        for r in routers:
            app.include_router(r, tags=[tag])
