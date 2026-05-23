# 后端服务依赖图（MT-5）

> 本文档由 `scripts/gen_service_deps.py` 自动生成，请勿手工编辑。
>
> 重新生成命令：`python scripts/gen_service_deps.py`

## 概览

- Service 数量：**310**
- Router 数量：**258**
- 依赖边数量：**614**

## 关键路径（入度最高的 Top 5 Service）

> 入度 = 被多少个 service / router 引用。入度高 = 改动影响面大，
> 需重点保证测试覆盖与变更评审。

| 排名 | Service | 入度 | 出度 |
|------|---------|------|------|
| 1 | `dataset_query` | 29 | 1 |
| 2 | `event_bus` | 29 | 0 |
| 3 | `trace_event_service` | 18 | 0 |
| 4 | `gate_engine` | 16 | 1 |
| 5 | `audit_logger_enhanced` | 12 | 0 |

## 依赖图

```mermaid
graph TD
    router__account_chart["🛣 account_chart"]
    router__account_note_mapping["🛣 account_note_mapping"]
    router__accounting_standards["🛣 accounting_standards"]
    router__address_registry["🛣 address_registry"]
    router__address_registry_v2["🛣 address_registry_v2"]
    router__adjustments["🛣 adjustments"]
    router__admin_event_health["🛣 admin_event_health"]
    router__aging_analysis["🛣 aging_analysis"]
    router__ai_models["🛣 ai_models"]
    router__ai_plugins["🛣 ai_plugins"]
    router__ai_unified["🛣 ai_unified"]
    router__annotations["🛣 annotations"]
    router__archive["🛣 archive"]
    router__archive_completeness["🛣 archive_completeness"]
    router__assignments["🛣 assignments"]
    router__attachments["🛣 attachments"]
    router__audit_logs["🛣 audit_logs"]
    router__audit_report["🛣 audit_report"]
    router__audit_types["🛣 audit_types"]
    router__background_jobs["🛣 background_jobs"]
    router__batch_assign_enhanced["🛣 batch_assign_enhanced"]
    router__batch_brief["🛣 batch_brief"]
    router__batch_export_progress["🛣 batch_export_progress"]
    router__batch_review["🛣 batch_review"]
    router__cfs_worksheet["🛣 cfs_worksheet"]
    router__chain_workflow["🛣 chain_workflow"]
    router__component_auditor["🛣 component_auditor"]
    router__confirmations["🛣 confirmations"]
    router__conflict_guard["🛣 conflict_guard"]
    router__consistency["🛣 consistency"]
    router__consistency_replay["🛣 consistency_replay"]
    router__consol_cell_comments["🛣 consol_cell_comments"]
    router__consol_note_sections["🛣 consol_note_sections"]
    router__consol_notes["🛣 consol_notes"]
    router__consol_report["🛣 consol_report"]
    router__consol_scope["🛣 consol_scope"]
    router__consol_trial["🛣 consol_trial"]
    router__consol_worksheet["🛣 consol_worksheet"]
    router__consol_worksheet_data["🛣 consol_worksheet_data"]
    router__consolidation["🛣 consolidation"]
    router__continuous_audit["🛣 continuous_audit"]
    router__cost_overview["🛣 cost_overview"]
    router__cross_cycle_breakage["🛣 cross_cycle_breakage"]
    router__custom_query["🛣 custom_query"]
    router__custom_templates["🛣 custom_templates"]
    router__dashboard["🛣 dashboard"]
    router__dashboard_aggregator["🛣 dashboard_aggregator"]
    router__data_fetch_custom["🛣 data_fetch_custom"]
    router__data_import["🛣 data_import"]
    router__data_lifecycle["🛣 data_lifecycle"]
    router__data_quality["🛣 data_quality"]
    router__data_validation["🛣 data_validation"]
    router__dataset_force_unbind["🛣 dataset_force_unbind"]
    router__disclosure_notes["🛣 disclosure_notes"]
    router__drilldown["🛣 drilldown"]
    router__editing_lock["🛣 editing_lock"]
    router__eqcr["🛣 eqcr"]
    router__eqcr_issues["🛣 eqcr_issues"]
    router__eqcr_judgment["🛣 eqcr_judgment"]
    router__eqcr_snapshot["🛣 eqcr_snapshot"]
    router__eqcr_trends["🛣 eqcr_trends"]
    router__event_cascade_health["🛣 event_cascade_health"]
    router__events["🛣 events"]
    router__excel_html["🛣 excel_html"]
    router__export["🛣 export"]
    router__export_integrity["🛣 export_integrity"]
    router__feature_flags["🛣 feature_flags"]
    router__forex["🛣 forex"]
    router__formula["🛣 formula"]
    router__formula_audit_log["🛣 formula_audit_log"]
    router__forum["🛣 forum"]
    router__gate["🛣 gate"]
    router__global_search["🛣 global_search"]
    router__goodwill["🛣 goodwill"]
    router__gt_coding["🛣 gt_coding"]
    router__health_redis["🛣 health_redis"]
    router__i18n["🛣 i18n"]
    router__import_intelligence["🛣 import_intelligence"]
    router__import_templates["🛣 import_templates"]
    router__independence["🛣 independence"]
    router__internal_trade["🛣 internal_trade"]
    router__issues["🛣 issues"]
    router__knowledge_base["🛣 knowledge_base"]
    router__knowledge_folders["🛣 knowledge_folders"]
    router__knowledge_tsj["🛣 knowledge_tsj"]
    router__ledger_data["🛣 ledger_data"]
    router__ledger_datasets["🛣 ledger_datasets"]
    router__ledger_import_health["🛣 ledger_import_health"]
    router__ledger_import_v2["🛣 ledger_import_v2"]
    router__ledger_penetration["🛣 ledger_penetration"]
    router__ledger_raw_extra["🛣 ledger_raw_extra"]
    router__linkage["🛣 linkage"]
    router__linkage_bus["🛣 linkage_bus"]
    router__linkage_panorama["🛣 linkage_panorama"]
    router__manager_dashboard["🛣 manager_dashboard"]
    router__mapping["🛣 mapping"]
    router__materiality["🛣 materiality"]
    router__metabase["🛣 metabase"]
    router__minority_interest["🛣 minority_interest"]
    router__misstatements["🛣 misstatements"]
    router__my_reviews["🛣 my_reviews"]
    router__my_todo["🛣 my_todo"]
    router__note_advanced["🛣 note_advanced"]
    router__note_ai["🛣 note_ai"]
    router__note_conversion["🛣 note_conversion"]
    router__note_custom_section["🛣 note_custom_section"]
    router__note_data_lock["🛣 note_data_lock"]
    router__note_export["🛣 note_export"]
    router__note_group_template["🛣 note_group_template"]
    router__note_related_workpapers["🛣 note_related_workpapers"]
    router__note_section_lock["🛣 note_section_lock"]
    router__note_templates["🛣 note_templates"]
    router__note_trace["🛣 note_trace"]
    router__note_trim["🛣 note_trim"]
    router__note_wp_mapping["🛣 note_wp_mapping"]
    router__notifications["🛣 notifications"]
    router__ocr_fields["🛣 ocr_fields"]
    router__office_preview["🛣 office_preview"]
    router__offline_conflicts["🛣 offline_conflicts"]
    router__partner_dashboard["🛣 partner_dashboard"]
    router__partner_urgency["🛣 partner_urgency"]
    router__password_confirm["🛣 password_confirm"]
    router__pbc["🛣 pbc"]
    router__penetrate_by_amount["🛣 penetrate_by_amount"]
    router__performance["🛣 performance"]
    router__pm_dashboard["🛣 pm_dashboard"]
    router__presence["🛣 presence"]
    router__private_storage["🛣 private_storage"]
    router__procedures["🛣 procedures"]
    router__process_record["🛣 process_record"]
    router__project_config["🛣 project_config"]
    router__project_permissions["🛣 project_permissions"]
    router__project_wizard["🛣 project_wizard"]
    router__qc["🛣 qc"]
    router__qc_annual_reports["🛣 qc_annual_reports"]
    router__qc_audit_log_compliance["🛣 qc_audit_log_compliance"]
    router__qc_cases["🛣 qc_cases"]
    router__qc_dashboard["🛣 qc_dashboard"]
    router__qc_inspections["🛣 qc_inspections"]
    router__qc_ratings["🛣 qc_ratings"]
    router__qc_report_export["🛣 qc_report_export"]
    router__qc_rotation_due["🛣 qc_rotation_due"]
    router__qc_rules["🛣 qc_rules"]
    router__qc_vr_heatmap["🛣 qc_vr_heatmap"]
    router__query_builder["🛣 query_builder"]
    router__reclassification["🛣 reclassification"]
    router__recycle_bin["🛣 recycle_bin"]
    router__regulatory["🛣 regulatory"]
    router__report_config["🛣 report_config"]
    router__report_export["🛣 report_export"]
    router__report_line_mapping["🛣 report_line_mapping"]
    router__report_mapping["🛣 report_mapping"]
    router__report_related_workpapers["🛣 report_related_workpapers"]
    router__report_trace["🛣 report_trace"]
    router__reports["🛣 reports"]
    router__review_config["🛣 review_config"]
    router__review_conversations["🛣 review_conversations"]
    router__review_recommend["🛣 review_recommend"]
    router__review_records_global["🛣 review_records_global"]
    router__review_templates["🛣 review_templates"]
    router__risk_summary["🛣 risk_summary"]
    router__role_ai_features["🛣 role_ai_features"]
    router__role_context["🛣 role_context"]
    router__rotation["🛣 rotation"]
    router__sampling["🛣 sampling"]
    router__sampling_enhanced["🛣 sampling_enhanced"]
    router__security["🛣 security"]
    router__shared_config["🛣 shared_config"]
    router__signatures["🛣 signatures"]
    router__sod["🛣 sod"]
    router__staff["🛣 staff"]
    router__stale_summary["🛣 stale_summary"]
    router__subsequent_events["🛣 subsequent_events"]
    router__system_dicts["🛣 system_dicts"]
    router__system_settings["🛣 system_settings"]
    router__t_accounts["🛣 t_accounts"]
    router__task_center["🛣 task_center"]
    router__task_events["🛣 task_events"]
    router__task_tree["🛣 task_tree"]
    router__tb_sync["🛣 tb_sync"]
    router__template_library["🛣 template_library"]
    router__template_library_mgmt["🛣 template_library_mgmt"]
    router__trace["🛣 trace"]
    router__trial_balance["🛣 trial_balance"]
    router__validation_rules["🛣 validation_rules"]
    router__version_line["🛣 version_line"]
    router__vr_coverage["🛣 vr_coverage"]
    router__word_export["🛣 word_export"]
    router__workflow_status["🛣 workflow_status"]
    router__workhour_approval["🛣 workhour_approval"]
    router__workhour_approve["🛣 workhour_approve"]
    router__workhour_budget["🛣 workhour_budget"]
    router__workhour_entries["🛣 workhour_entries"]
    router__workhour_list["🛣 workhour_list"]
    router__workhours["🛣 workhours"]
    router__working_paper["🛣 working_paper"]
    router__workpaper_batch_status["🛣 workpaper_batch_status"]
    router__workpaper_html_preview["🛣 workpaper_html_preview"]
    router__workpaper_prior_year["🛣 workpaper_prior_year"]
    router__workpaper_remind["🛣 workpaper_remind"]
    router__workpaper_requirements["🛣 workpaper_requirements"]
    router__workpaper_summary["🛣 workpaper_summary"]
    router__wp_ai["🛣 wp_ai"]
    router__wp_ai_confirm["🛣 wp_ai_confirm"]
    router__wp_ai_interview["🛣 wp_ai_interview"]
    router__wp_ai_stocktake["🛣 wp_ai_stocktake"]
    router__wp_batch_ops["🛣 wp_batch_ops"]
    router__wp_business_pattern["🛣 wp_business_pattern"]
    router__wp_cell_annotations["🛣 wp_cell_annotations"]
    router__wp_chat["🛣 wp_chat"]
    router__wp_cross_check["🛣 wp_cross_check"]
    router__wp_data_rules["🛣 wp_data_rules"]
    router__wp_dependencies["🛣 wp_dependencies"]
    router__wp_download["🛣 wp_download"]
    router__wp_eqcr_evaluation["🛣 wp_eqcr_evaluation"]
    router__wp_evidence["🛣 wp_evidence"]
    router__wp_explanation["🛣 wp_explanation"]
    router__wp_f2_impairment["🛣 wp_f2_impairment"]
    router__wp_f2_valuation["🛣 wp_f2_valuation"]
    router__wp_fine_rules["🛣 wp_fine_rules"]
    router__wp_g_classification["🛣 wp_g_classification"]
    router__wp_g_ecl["🛣 wp_g_ecl"]
    router__wp_g_fair_value["🛣 wp_g_fair_value"]
    router__wp_h_depreciation["🛣 wp_h_depreciation"]
    router__wp_h_impairment["🛣 wp_h_impairment"]
    router__wp_health_dashboard["🛣 wp_health_dashboard"]
    router__wp_i_amortization["🛣 wp_i_amortization"]
    router__wp_i_capitalization["🛣 wp_i_capitalization"]
    router__wp_i_goodwill["🛣 wp_i_goodwill"]
    router__wp_j_payroll_calc["🛣 wp_j_payroll_calc"]
    router__wp_j_share_payment["🛣 wp_j_share_payment"]
    router__wp_k_expense_analysis["🛣 wp_k_expense_analysis"]
    router__wp_k_impairment_summary["🛣 wp_k_impairment_summary"]
    router__wp_l_bond_amortization["🛣 wp_l_bond_amortization"]
    router__wp_l_interest_calc["🛣 wp_l_interest_calc"]
    router__wp_m_equity_movement["🛣 wp_m_equity_movement"]
    router__wp_manuals["🛣 wp_manuals"]
    router__wp_mapping["🛣 wp_mapping"]
    router__wp_n_income_tax_calc["🛣 wp_n_income_tax_calc"]
    router__wp_prefill_context["🛣 wp_prefill_context"]
    router__wp_prefill_preview["🛣 wp_prefill_preview"]
    router__wp_prerequisite_status["🛣 wp_prerequisite_status"]
    router__wp_procedure_status["🛣 wp_procedure_status"]
    router__wp_procedure_trim["🛣 wp_procedure_trim"]
    router__wp_procedures["🛣 wp_procedures"]
    router__wp_progress["🛣 wp_progress"]
    router__wp_review["🛣 wp_review"]
    router__wp_review_status["🛣 wp_review_status"]
    router__wp_search["🛣 wp_search"]
    router__wp_step_mapping["🛣 wp_step_mapping"]
    router__wp_storage["🛣 wp_storage"]
    router__wp_structure["🛣 wp_structure"]
    router__wp_template["🛣 wp_template"]
    router__wp_template_download["🛣 wp_template_download"]
    router__wp_template_files["🛣 wp_template_files"]
    router__wp_template_metadata["🛣 wp_template_metadata"]
    router__wp_user_formulas["🛣 wp_user_formulas"]
    router__wp_version_search["🛣 wp_version_search"]
    service__account_chart_service["⚙ account_chart_service"]
    service__accounting_standard_service["⚙ accounting_standard_service"]
    service__address_registry["⚙ address_registry"]
    service__adjustment_impact_service["⚙ adjustment_impact_service"]
    service__adjustment_service["⚙ adjustment_service"]
    service__aging_analysis_service["⚙ aging_analysis_service"]
    service__ai_chat_service["⚙ ai_chat_service"]
    service__ai_contribution_watermark["⚙ ai_contribution_watermark"]
    service__ai_plugin_service["⚙ ai_plugin_service"]
    service__ai_service["⚙ ai_service"]
    service__annotation_service["⚙ annotation_service"]
    service__archive_completeness_service["⚙ archive_completeness_service"]
    service__archive_generators["⚙ archive_generators"]
    service__archive_orchestrator["⚙ archive_orchestrator"]
    service__archive_pdf_generators["⚙ archive_pdf_generators"]
    service__archive_section_registry["⚙ archive_section_registry"]
    service__assignment_service["⚙ assignment_service"]
    service__attachment_service["⚙ attachment_service"]
    service__audit_logger_enhanced["⚙ audit_logger_enhanced ⭐"]
    service__audit_report_service["⚙ audit_report_service"]
    service__audit_type_service["⚙ audit_type_service"]
    service__auth_service["⚙ auth_service"]
    service__availability_fallback_service["⚙ availability_fallback_service"]
    service__background_job_service["⚙ background_job_service"]
    service__batch_assign_strategy["⚙ batch_assign_strategy"]
    service__batch_brief_service["⚙ batch_brief_service"]
    service__cache_manager["⚙ cache_manager"]
    service__cache_service["⚙ cache_service"]
    service__cfs_worksheet_engine["⚙ cfs_worksheet_engine"]
    service__chain_orchestrator["⚙ chain_orchestrator"]
    service__client_lookup["⚙ client_lookup"]
    service__client_quality_trend_service["⚙ client_quality_trend_service"]
    service__cloud_storage_service["⚙ cloud_storage_service"]
    service__component_auditor_service["⚙ component_auditor_service"]
    service__confirmation_service["⚙ confirmation_service"]
    service__conflict_guard_service["⚙ conflict_guard_service"]
    service__consistency_check_service["⚙ consistency_check_service"]
    service__consistency_gate["⚙ consistency_gate"]
    service__consistency_replay_engine["⚙ consistency_replay_engine"]
    service__consol_aggregation_service["⚙ consol_aggregation_service"]
    service__consol_disclosure_service["⚙ consol_disclosure_service"]
    service__consol_drilldown_service["⚙ consol_drilldown_service"]
    service__consol_enhanced_service["⚙ consol_enhanced_service"]
    service__consol_pivot_service["⚙ consol_pivot_service"]
    service__consol_report_service["⚙ consol_report_service"]
    service__consol_scope_service["⚙ consol_scope_service"]
    service__consol_tree_service["⚙ consol_tree_service"]
    service__consol_trial_service["⚙ consol_trial_service"]
    service__consol_worksheet_engine["⚙ consol_worksheet_engine"]
    service__continuous_audit_service["⚙ continuous_audit_service"]
    service__contract_analysis_service["⚙ contract_analysis_service"]
    service__cost_overview_service["⚙ cost_overview_service"]
    service__cross_cycle_breakage_service["⚙ cross_cycle_breakage_service"]
    service__custom_template_service["⚙ custom_template_service"]
    service__dashboard_aggregator_service["⚙ dashboard_aggregator_service"]
    service__dashboard_service["⚙ dashboard_service"]
    service__data_fetch_custom["⚙ data_fetch_custom"]
    service__data_health_monitor["⚙ data_health_monitor"]
    service__data_lifecycle_service["⚙ data_lifecycle_service"]
    service__data_quality_service["⚙ data_quality_service"]
    service__data_validation_engine["⚙ data_validation_engine"]
    service__dataset_query["⚙ dataset_query ⭐"]
    service__dataset_service["⚙ dataset_service"]
    service__disclosure_engine["⚙ disclosure_engine"]
    service__docx_to_univer_doc_service["⚙ docx_to_univer_doc_service"]
    service__drilldown_service["⚙ drilldown_service"]
    service__editing_lock_service["⚙ editing_lock_service"]
    service__elimination_service["⚙ elimination_service"]
    service__encryption_service["⚙ encryption_service"]
    service__eqcr_domain_service["⚙ eqcr_domain_service"]
    service__eqcr_independence_service["⚙ eqcr_independence_service"]
    service__eqcr_memo_service["⚙ eqcr_memo_service"]
    service__eqcr_service["⚙ eqcr_service"]
    service__eqcr_shadow_compute_service["⚙ eqcr_shadow_compute_service"]
    service__eqcr_snapshot_service["⚙ eqcr_snapshot_service"]
    service__eqcr_workbench_service["⚙ eqcr_workbench_service"]
    service__equity_method_service["⚙ equity_method_service"]
    service__event_bus["⚙ event_bus ⭐"]
    service__event_cascade_health_service["⚙ event_cascade_health_service"]
    service__event_cascade_monitor["⚙ event_cascade_monitor"]
    service__event_handlers["⚙ event_handlers"]
    service__excel_html_converter["⚙ excel_html_converter"]
    service__export_integrity_service["⚙ export_integrity_service"]
    service__export_job_service["⚙ export_job_service"]
    service__export_mask_service["⚙ export_mask_service"]
    service__export_package_service["⚙ export_package_service"]
    service__export_progress_service["⚙ export_progress_service"]
    service__export_task_service["⚙ export_task_service"]
    service__fast_writer["⚙ fast_writer"]
    service__feature_flags["⚙ feature_flags"]
    service__file_scan_service["⚙ file_scan_service"]
    service__forex_service["⚙ forex_service"]
    service__formula_engine["⚙ formula_engine"]
    service__formula_parser["⚙ formula_parser"]
    service__formula_reverse_index["⚙ formula_reverse_index"]
    service__formula_unified["⚙ formula_unified"]
    service__forum_service["⚙ forum_service"]
    service__gate_engine["⚙ gate_engine ⭐"]
    service__gate_eval_store["⚙ gate_eval_store"]
    service__gate_rules_ai_content["⚙ gate_rules_ai_content"]
    service__gate_rules_chain["⚙ gate_rules_chain"]
    service__gate_rules_cross_check["⚙ gate_rules_cross_check"]
    service__gate_rules_eqcr["⚙ gate_rules_eqcr"]
    service__gate_rules_phase14["⚙ gate_rules_phase14"]
    service__gate_rules_round6["⚙ gate_rules_round6"]
    service__global_search_service["⚙ global_search_service"]
    service__goodwill_service["⚙ goodwill_service"]
    service__gt_coding_service["⚙ gt_coding_service"]
    service__gt_word_engine["⚙ gt_word_engine"]
    service__handover_service["⚙ handover_service"]
    service__i18n_service["⚙ i18n_service"]
    service__import_artifact_service["⚙ import_artifact_service"]
    service__import_artifact_storage["⚙ import_artifact_storage"]
    service__import_engine["⚙ import_engine"]
    service__import_error_formatter["⚙ import_error_formatter"]
    service__import_event_consumption_service["⚙ import_event_consumption_service"]
    service__import_event_outbox_service["⚙ import_event_outbox_service"]
    service__import_event_reliability_service["⚙ import_event_reliability_service"]
    service__import_intelligence["⚙ import_intelligence"]
    service__import_job_runner["⚙ import_job_runner"]
    service__import_job_service["⚙ import_job_service"]
    service__import_ops_audit_service["⚙ import_ops_audit_service"]
    service__import_queue_service["⚙ import_queue_service"]
    service__import_service["⚙ import_service"]
    service__import_slo_service["⚙ import_slo_service"]
    service__import_template_service["⚙ import_template_service"]
    service__import_validation_service["⚙ import_validation_service"]
    service__independence_service["⚙ independence_service"]
    service__internal_trade_service["⚙ internal_trade_service"]
    service__issue_ticket_service["⚙ issue_ticket_service"]
    service__knowledge_folder_service["⚙ knowledge_folder_service"]
    service__knowledge_index_service["⚙ knowledge_index_service"]
    service__knowledge_service["⚙ knowledge_service"]
    service__ledger_data_service["⚙ ledger_data_service"]
    service__ledger_import["⚙ ledger_import"]
    service__ledger_import_application_service["⚙ ledger_import_application_service"]
    service__ledger_import_upload_service["⚙ ledger_import_upload_service"]
    service__ledger_penetration_service["⚙ ledger_penetration_service"]
    service__linkage_graph_builder["⚙ linkage_graph_builder"]
    service__linkage_label_resolver["⚙ linkage_label_resolver"]
    service__linkage_panorama_aggregator["⚙ linkage_panorama_aggregator"]
    service__linkage_service["⚙ linkage_service"]
    service__llm_client["⚙ llm_client"]
    service__llm_metrics["⚙ llm_metrics"]
    service__llm_service["⚙ llm_service"]
    service__manager_dashboard_service["⚙ manager_dashboard_service"]
    service__mapping_service["⚙ mapping_service"]
    service__materiality_service["⚙ materiality_service"]
    service__metabase_service["⚙ metabase_service"]
    service__mineru_service["⚙ mineru_service"]
    service__minority_interest_service["⚙ minority_interest_service"]
    service__misstatement_service["⚙ misstatement_service"]
    service__my_todo_service["⚙ my_todo_service"]
    service__note_account_mapping_service["⚙ note_account_mapping_service"]
    service__note_conversion_service["⚙ note_conversion_service"]
    service__note_cross_reference_service["⚙ note_cross_reference_service"]
    service__note_custom_section_service["⚙ note_custom_section_service"]
    service__note_data_extractor["⚙ note_data_extractor"]
    service__note_data_lock_service["⚙ note_data_lock_service"]
    service__note_fill_engine["⚙ note_fill_engine"]
    service__note_formula_engine["⚙ note_formula_engine"]
    service__note_formula_generator["⚙ note_formula_generator"]
    service__note_group_template_service["⚙ note_group_template_service"]
    service__note_layer_strategy["⚙ note_layer_strategy"]
    service__note_md_template_parser["⚙ note_md_template_parser"]
    service__note_prior_year_import_service["⚙ note_prior_year_import_service"]
    service__note_rule_engine["⚙ note_rule_engine"]
    service__note_section_lock_service["⚙ note_section_lock_service"]
    service__note_stale_service["⚙ note_stale_service"]
    service__note_template_service["⚙ note_template_service"]
    service__note_trim_service["⚙ note_trim_service"]
    service__note_trim_sort_service["⚙ note_trim_sort_service"]
    service__note_validation_engine["⚙ note_validation_engine"]
    service__note_variation_analysis_service["⚙ note_variation_analysis_service"]
    service__note_wide_table_engine["⚙ note_wide_table_engine"]
    service__note_word_exporter["⚙ note_word_exporter"]
    service__note_wp_mapping_service["⚙ note_wp_mapping_service"]
    service__notification_service["⚙ notification_service"]
    service__notification_types["⚙ notification_types"]
    service__ocr_fields_service["⚙ ocr_fields_service"]
    service__ocr_service_v2["⚙ ocr_service_v2"]
    service__offline_conflict_service["⚙ offline_conflict_service"]
    service__partner_service["⚙ partner_service"]
    service__pdf_export_engine["⚙ pdf_export_engine"]
    service__performance_monitor["⚙ performance_monitor"]
    service__permission_service["⚙ permission_service"]
    service__pm_service["⚙ pm_service"]
    service__prefill_engine["⚙ prefill_engine"]
    service__prerequisite_checker["⚙ prerequisite_checker"]
    service__presence_service["⚙ presence_service"]
    service__private_storage_service["⚙ private_storage_service"]
    service__procedure_service["⚙ procedure_service"]
    service__procedure_trim_engine["⚙ procedure_trim_engine"]
    service__process_record_service["⚙ process_record_service"]
    service__project_wizard_service["⚙ project_wizard_service"]
    service__qc_annual_report_service["⚙ qc_annual_report_service"]
    service__qc_case_library_service["⚙ qc_case_library_service"]
    service__qc_dashboard_service["⚙ qc_dashboard_service"]
    service__qc_engine["⚙ qc_engine"]
    service__qc_inspection_service["⚙ qc_inspection_service"]
    service__qc_rule_definition_service["⚙ qc_rule_definition_service"]
    service__qc_rule_dry_run_service["⚙ qc_rule_dry_run_service"]
    service__qc_rule_executor["⚙ qc_rule_executor"]
    service__quality_rating_service["⚙ quality_rating_service"]
    service__rc_enhanced_service["⚙ rc_enhanced_service"]
    service__readiness_facade["⚙ readiness_facade"]
    service__reference_doc_service["⚙ reference_doc_service"]
    service__regulatory_service["⚙ regulatory_service"]
    service__report_config_service["⚙ report_config_service"]
    service__report_engine["⚙ report_engine"]
    service__report_excel_exporter["⚙ report_excel_exporter"]
    service__report_export_engine["⚙ report_export_engine"]
    service__report_formula_service["⚙ report_formula_service"]
    service__report_line_mapping_service["⚙ report_line_mapping_service"]
    service__report_mapping_service["⚙ report_mapping_service"]
    service__report_note_sync_service["⚙ report_note_sync_service"]
    service__report_placeholder_service["⚙ report_placeholder_service"]
    service__report_snapshot_service["⚙ report_snapshot_service"]
    service__report_trace_service["⚙ report_trace_service"]
    service__retry_utils["⚙ retry_utils"]
    service__review_conversation_service["⚙ review_conversation_service"]
    service__review_notification_service["⚙ review_notification_service"]
    service__review_state_machine["⚙ review_state_machine"]
    service__review_template_service["⚙ review_template_service"]
    service__reviewer_metrics_service["⚙ reviewer_metrics_service"]
    service__risk_summary_service["⚙ risk_summary_service"]
    service__role_ai_features["⚙ role_ai_features"]
    service__role_context_service["⚙ role_context_service"]
    service__rotation_check_service["⚙ rotation_check_service"]
    service__sampling_enhanced_service["⚙ sampling_enhanced_service"]
    service__sampling_service["⚙ sampling_service"]
    service__security_monitor["⚙ security_monitor"]
    service__shared_config_service["⚙ shared_config_service"]
    service__sign_service["⚙ sign_service"]
    service__smart_import_engine["⚙ smart_import_engine"]
    service__sod_guard_service["⚙ sod_guard_service"]
    service__staff_service["⚙ staff_service"]
    service__stale_propagation_engine["⚙ stale_propagation_engine"]
    service__stale_summary_aggregate["⚙ stale_summary_aggregate"]
    service__t_account_service["⚙ t_account_service"]
    service__task_center["⚙ task_center"]
    service__task_event_bus["⚙ task_event_bus"]
    service__task_event_handlers["⚙ task_event_handlers"]
    service__task_tree_service["⚙ task_tree_service"]
    service__template_engine["⚙ template_engine"]
    service__template_library_service["⚙ template_library_service"]
    service__trace_event_service["⚙ trace_event_service ⭐"]
    service__trial_balance_service["⚙ trial_balance_service"]
    service__triple_format_adapter["⚙ triple_format_adapter"]
    service__tsj_prompt_service["⚙ tsj_prompt_service"]
    service__unified_ai_service["⚙ unified_ai_service"]
    service__unified_ocr_service["⚙ unified_ocr_service"]
    service__univer_to_xlsx["⚙ univer_to_xlsx"]
    service__version_line_service["⚙ version_line_service"]
    service__wopi_service["⚙ wopi_service"]
    service__word_template_filler["⚙ word_template_filler"]
    service__workhour_approve_service["⚙ workhour_approve_service"]
    service__workhour_service["⚙ workhour_service"]
    service__working_paper_service["⚙ working_paper_service"]
    service__workpaper_fill_service["⚙ workpaper_fill_service"]
    service__workpaper_query["⚙ workpaper_query"]
    service__workpaper_remind_service["⚙ workpaper_remind_service"]
    service__workpaper_requirements_service["⚙ workpaper_requirements_service"]
    service__workpaper_summary_service["⚙ workpaper_summary_service"]
    service__wp_ai_service["⚙ wp_ai_service"]
    service__wp_audit_trail_service["⚙ wp_audit_trail_service"]
    service__wp_batch_prefill["⚙ wp_batch_prefill"]
    service__wp_cell_annotation_service["⚙ wp_cell_annotation_service"]
    service__wp_cell_lock_service["⚙ wp_cell_lock_service"]
    service__wp_chat_service["⚙ wp_chat_service"]
    service__wp_conclusion_service["⚙ wp_conclusion_service"]
    service__wp_cross_check_service["⚙ wp_cross_check_service"]
    service__wp_cross_index_service["⚙ wp_cross_index_service"]
    service__wp_data_rules["⚙ wp_data_rules"]
    service__wp_dependency_service["⚙ wp_dependency_service"]
    service__wp_download_service["⚙ wp_download_service"]
    service__wp_evidence_index["⚙ wp_evidence_index"]
    service__wp_evidence_service["⚙ wp_evidence_service"]
    service__wp_explanation_service["⚙ wp_explanation_service"]
    service__wp_fine_rule_engine["⚙ wp_fine_rule_engine"]
    service__wp_formula_dependency["⚙ wp_formula_dependency"]
    service__wp_generic_processor["⚙ wp_generic_processor"]
    service__wp_guidance_service["⚙ wp_guidance_service"]
    service__wp_header_service["⚙ wp_header_service"]
    service__wp_llm_prompts["⚙ wp_llm_prompts"]
    service__wp_manual_service["⚙ wp_manual_service"]
    service__wp_mapping_feedback_service["⚙ wp_mapping_feedback_service"]
    service__wp_mapping_service["⚙ wp_mapping_service"]
    service__wp_note_linkage_service["⚙ wp_note_linkage_service"]
    service__wp_ocr_fill_service["⚙ wp_ocr_fill_service"]
    service__wp_ocr_voucher_service["⚙ wp_ocr_voucher_service"]
    service__wp_permission_service["⚙ wp_permission_service"]
    service__wp_procedure_service["⚙ wp_procedure_service"]
    service__wp_progress_service["⚙ wp_progress_service"]
    service__wp_quality_score_linkage["⚙ wp_quality_score_linkage"]
    service__wp_quality_score_service["⚙ wp_quality_score_service"]
    service__wp_review_checklist_service["⚙ wp_review_checklist_service"]
    service__wp_review_service["⚙ wp_review_service"]
    service__wp_risk_trace_service["⚙ wp_risk_trace_service"]
    service__wp_sampling_engine["⚙ wp_sampling_engine"]
    service__wp_scripts["⚙ wp_scripts"]
    service__wp_sign_date_chain_service["⚙ wp_sign_date_chain_service"]
    service__wp_snapshot_service["⚙ wp_snapshot_service"]
    service__wp_storage_service["⚙ wp_storage_service"]
    service__wp_structure_bridge["⚙ wp_structure_bridge"]
    service__wp_template_init_service["⚙ wp_template_init_service"]
    service__wp_template_service["⚙ wp_template_service"]
    service__wp_version_search_service["⚙ wp_version_search_service"]
    service__wp_visualization_service["⚙ wp_visualization_service"]
    service__xlsx_to_univer["⚙ xlsx_to_univer"]
    router__account_chart --> service__event_bus
    router__account_chart --> service__import_ops_audit_service
    router__account_chart --> service__import_queue_service
    router__account_chart --> service__ledger_import_application_service
    router__account_chart --> service__project_wizard_service
    router__accounting_standards --> service__accounting_standard_service
    router__address_registry --> service__address_registry
    router__address_registry_v2 --> service__stale_propagation_engine
    router__adjustments --> service__adjustment_service
    router__adjustments --> service__audit_logger_enhanced
    router__adjustments --> service__mapping_service
    router__adjustments --> service__misstatement_service
    router__adjustments --> service__workpaper_query
    router__admin_event_health --> service__event_cascade_monitor
    router__aging_analysis --> service__aging_analysis_service
    router__ai_models --> service__ai_service
    router__ai_plugins --> service__ai_plugin_service
    router__ai_plugins --> service__unified_ai_service
    router__ai_unified --> service__cache_manager
    router__ai_unified --> service__unified_ai_service
    router__annotations --> service__annotation_service
    router__annotations --> service__event_bus
    router__archive --> router__password_confirm
    router__archive --> service__archive_orchestrator
    router__archive_completeness --> service__archive_completeness_service
    router__assignments --> service__assignment_service
    router__assignments --> service__sod_guard_service
    router__attachments --> service__attachment_service
    router__attachments --> service__task_center
    router__audit_logs --> service__role_context_service
    router__audit_report --> service__audit_report_service
    router__audit_types --> service__audit_type_service
    router__background_jobs --> service__background_job_service
    router__batch_assign_enhanced --> service__audit_logger_enhanced
    router__batch_assign_enhanced --> service__batch_assign_strategy
    router__batch_assign_enhanced --> service__event_bus
    router__batch_assign_enhanced --> service__notification_service
    router__batch_assign_enhanced --> service__notification_types
    router__batch_brief --> service__batch_brief_service
    router__batch_brief --> service__export_job_service
    router__batch_export_progress --> service__export_progress_service
    router__cfs_worksheet --> service__cfs_worksheet_engine
    router__chain_workflow --> service__chain_orchestrator
    router__chain_workflow --> service__consistency_gate
    router__chain_workflow --> service__data_health_monitor
    router__chain_workflow --> service__export_package_service
    router__chain_workflow --> service__note_trim_sort_service
    router__chain_workflow --> service__report_note_sync_service
    router__component_auditor --> service__component_auditor_service
    router__conflict_guard --> service__conflict_guard_service
    router__consistency --> service__consistency_check_service
    router__consistency_replay --> service__consistency_replay_engine
    router__consol_notes --> service__consol_disclosure_service
    router__consol_report --> service__consol_report_service
    router__consol_scope --> service__consol_scope_service
    router__consol_trial --> service__consol_trial_service
    router__consol_worksheet --> service__consol_aggregation_service
    router__consol_worksheet --> service__consol_drilldown_service
    router__consol_worksheet --> service__consol_pivot_service
    router__consol_worksheet --> service__consol_tree_service
    router__consol_worksheet --> service__consol_worksheet_engine
    router__consolidation --> service__elimination_service
    router__consolidation --> service__equity_method_service
    router__consolidation --> service__internal_trade_service
    router__continuous_audit --> service__continuous_audit_service
    router__cross_cycle_breakage --> service__cross_cycle_breakage_service
    router__custom_templates --> service__custom_template_service
    router__dashboard --> service__dashboard_service
    router__dashboard_aggregator --> service__dashboard_aggregator_service
    router__data_fetch_custom --> service__data_fetch_custom
    router__data_lifecycle --> service__data_lifecycle_service
    router__data_lifecycle --> service__import_queue_service
    router__data_quality --> service__data_quality_service
    router__data_validation --> service__data_validation_engine
    router__dataset_force_unbind --> service__audit_logger_enhanced
    router__disclosure_notes --> service__disclosure_engine
    router__disclosure_notes --> service__event_bus
    router__disclosure_notes --> service__mapping_service
    router__disclosure_notes --> service__note_formula_generator
    router__disclosure_notes --> service__note_validation_engine
    router__disclosure_notes --> service__note_word_exporter
    router__disclosure_notes --> service__note_wp_mapping_service
    router__disclosure_notes --> service__prerequisite_checker
    router__drilldown --> service__drilldown_service
    router__eqcr --> service__audit_logger_enhanced
    router__eqcr --> service__client_lookup
    router__eqcr --> service__eqcr_domain_service
    router__eqcr --> service__eqcr_independence_service
    router__eqcr --> service__eqcr_memo_service
    router__eqcr --> service__eqcr_service
    router__eqcr --> service__eqcr_shadow_compute_service
    router__eqcr --> service__eqcr_workbench_service
    router__eqcr --> service__gate_engine
    router__event_cascade_health --> service__event_cascade_health_service
    router__events --> service__event_bus
    router__excel_html --> service__excel_html_converter
    router__excel_html --> service__formula_unified
    router__excel_html --> service__triple_format_adapter
    router__export --> service__pdf_export_engine
    router__export_integrity --> service__export_integrity_service
    router__export_integrity --> service__trace_event_service
    router__feature_flags --> service__feature_flags
    router__forex --> service__forex_service
    router__formula --> service__formula_engine
    router__forum --> service__forum_service
    router__gate --> service__gate_engine
    router__global_search --> service__global_search_service
    router__goodwill --> service__goodwill_service
    router__gt_coding --> service__gt_coding_service
    router__i18n --> service__i18n_service
    router__import_intelligence --> service__import_intelligence
    router__import_templates --> service__adjustment_service
    router__import_templates --> service__disclosure_engine
    router__import_templates --> service__formula_unified
    router__import_templates --> service__import_template_service
    router__import_templates --> service__report_engine
    router__import_templates --> service__staff_service
    router__import_templates --> service__trial_balance_service
    router__import_templates --> service__working_paper_service
    router__independence --> service__independence_service
    router__internal_trade --> service__internal_trade_service
    router__issues --> service__issue_ticket_service
    router__knowledge_folders --> service__knowledge_folder_service
    router__ledger_data --> service__ledger_data_service
    router__ledger_datasets --> service__dataset_service
    router__ledger_datasets --> service__import_artifact_service
    router__ledger_datasets --> service__import_job_runner
    router__ledger_datasets --> service__import_job_service
    router__ledger_datasets --> service__import_queue_service
    router__ledger_import_health --> service__ledger_import
    router__ledger_import_v2 --> service__import_job_runner
    router__ledger_import_v2 --> service__import_queue_service
    router__ledger_import_v2 --> service__ledger_data_service
    router__ledger_import_v2 --> service__ledger_import
    router__ledger_import_v2 --> service__ledger_import_upload_service
    router__ledger_penetration --> service__dataset_query
    router__ledger_penetration --> service__ledger_import_application_service
    router__ledger_penetration --> service__ledger_penetration_service
    router__linkage --> service__linkage_service
    router__linkage_bus --> service__formula_reverse_index
    router__linkage_bus --> service__linkage_graph_builder
    router__linkage_bus --> service__linkage_label_resolver
    router__linkage_bus --> service__stale_propagation_engine
    router__linkage_panorama --> service__linkage_panorama_aggregator
    router__manager_dashboard --> service__manager_dashboard_service
    router__materiality --> service__materiality_service
    router__materiality --> service__trial_balance_service
    router__metabase --> service__metabase_service
    router__minority_interest --> service__minority_interest_service
    router__misstatements --> service__misstatement_service
    router__misstatements --> service__workpaper_query
    router__my_todo --> service__my_todo_service
    router__note_advanced --> service__note_cross_reference_service
    router__note_advanced --> service__note_prior_year_import_service
    router__note_advanced --> service__note_variation_analysis_service
    router__note_ai --> service__export_mask_service
    router__note_ai --> service__llm_client
    router__note_ai --> service__reference_doc_service
    router__note_conversion --> service__note_conversion_service
    router__note_custom_section --> service__note_custom_section_service
    router__note_data_lock --> service__note_data_lock_service
    router__note_export --> service__note_word_exporter
    router__note_group_template --> service__note_group_template_service
    router__note_section_lock --> service__note_section_lock_service
    router__note_templates --> service__note_formula_engine
    router__note_templates --> service__note_template_service
    router__note_trim --> service__note_trim_service
    router__note_wp_mapping --> service__note_wp_mapping_service
    router__ocr_fields --> service__ocr_fields_service
    router__office_preview --> service__attachment_service
    router__offline_conflicts --> service__offline_conflict_service
    router__partner_dashboard --> service__gate_engine
    router__partner_dashboard --> service__partner_service
    router__performance --> service__import_event_outbox_service
    router__performance --> service__import_event_reliability_service
    router__performance --> service__import_ops_audit_service
    router__performance --> service__import_slo_service
    router__performance --> service__llm_metrics
    router__performance --> service__performance_monitor
    router__pm_dashboard --> service__pm_service
    router__presence --> service__presence_service
    router__private_storage --> service__private_storage_service
    router__procedures --> service__procedure_service
    router__procedures --> service__task_event_bus
    router__procedures --> service__trace_event_service
    router__process_record --> service__process_record_service
    router__project_config --> service__report_note_sync_service
    router__project_wizard --> router__password_confirm
    router__qc --> service__qc_engine
    router__qc_annual_reports --> service__qc_annual_report_service
    router__qc_audit_log_compliance --> service__qc_rule_executor
    router__qc_cases --> service__qc_case_library_service
    router__qc_dashboard --> service__qc_dashboard_service
    router__qc_inspections --> service__qc_inspection_service
    router__qc_ratings --> service__client_quality_trend_service
    router__qc_ratings --> service__quality_rating_service
    router__qc_ratings --> service__reviewer_metrics_service
    router__qc_rules --> service__background_job_service
    router__qc_rules --> service__qc_rule_definition_service
    router__qc_rules --> service__qc_rule_dry_run_service
    router__qc_vr_heatmap --> service__consistency_gate
    router__reclassification --> service__event_bus
    router__regulatory --> service__regulatory_service
    router__report_config --> router__formula_audit_log
    router__report_config --> service__event_bus
    router__report_config --> service__formula_engine
    router__report_config --> service__formula_parser
    router__report_config --> service__report_config_service
    router__report_config --> service__report_formula_service
    router__report_export --> service__report_excel_exporter
    router__report_mapping --> service__report_mapping_service
    router__report_trace --> service__annotation_service
    router__report_trace --> service__consol_enhanced_service
    router__report_trace --> service__dataset_query
    router__report_trace --> service__llm_client
    router__report_trace --> service__report_trace_service
    router__reports --> service__event_bus
    router__reports --> service__prerequisite_checker
    router__reports --> service__report_config_service
    router__reports --> service__report_engine
    router__review_conversations --> service__rc_enhanced_service
    router__review_conversations --> service__review_conversation_service
    router__risk_summary --> service__risk_summary_service
    router__role_ai_features --> service__role_ai_features
    router__role_context --> service__role_context_service
    router__rotation --> service__rotation_check_service
    router__sampling --> service__sampling_service
    router__sampling_enhanced --> service__sampling_enhanced_service
    router__security --> service__audit_logger_enhanced
    router__security --> service__security_monitor
    router__security --> service__trace_event_service
    router__shared_config --> service__shared_config_service
    router__signatures --> router__password_confirm
    router__signatures --> service__sign_service
    router__sod --> service__sod_guard_service
    router__staff --> service__handover_service
    router__staff --> service__manager_dashboard_service
    router__staff --> service__staff_service
    router__stale_summary --> service__stale_summary_aggregate
    router__t_accounts --> service__t_account_service
    router__task_center --> service__task_center
    router__task_events --> service__task_event_bus
    router__task_tree --> service__task_tree_service
    router__tb_sync --> service__event_bus
    router__template_library --> service__template_library_service
    router__template_library_mgmt --> service__accounting_standard_service
    router__template_library_mgmt --> service__audit_report_service
    router__template_library_mgmt --> service__event_bus
    router__template_library_mgmt --> service__gt_coding_service
    router__template_library_mgmt --> service__report_config_service
    router__template_library_mgmt --> service__report_formula_service
    router__template_library_mgmt --> service__wp_template_init_service
    router__template_library_mgmt --> service__wp_template_service
    router__trace --> service__trace_event_service
    router__trial_balance --> service__cache_service
    router__trial_balance --> service__dataset_query
    router__trial_balance --> service__event_bus
    router__trial_balance --> service__mapping_service
    router__trial_balance --> service__materiality_service
    router__trial_balance --> service__prerequisite_checker
    router__trial_balance --> service__trial_balance_service
    router__validation_rules --> service__ledger_import
    router__version_line --> service__version_line_service
    router__word_export --> service__export_job_service
    router__word_export --> service__export_task_service
    router__word_export --> service__gate_engine
    router__word_export --> service__report_snapshot_service
    router__word_export --> service__word_template_filler
    router__workhour_approve --> service__manager_dashboard_service
    router__workhour_approve --> service__workhour_approve_service
    router__workhours --> service__workhour_service
    router__working_paper --> service__cache_service
    router__working_paper --> service__event_bus
    router__working_paper --> service__feature_flags
    router__working_paper --> service__gate_engine
    router__working_paper --> service__notification_service
    router__working_paper --> service__notification_types
    router__working_paper --> service__prefill_engine
    router__working_paper --> service__sod_guard_service
    router__working_paper --> service__univer_to_xlsx
    router__working_paper --> service__wopi_service
    router__working_paper --> service__working_paper_service
    router__working_paper --> service__wp_data_rules
    router__working_paper --> service__wp_download_service
    router__working_paper --> service__xlsx_to_univer
    router__workpaper_html_preview --> service__excel_html_converter
    router__workpaper_html_preview --> service__export_mask_service
    router__workpaper_prior_year --> service__continuous_audit_service
    router__workpaper_remind --> service__notification_service
    router__workpaper_remind --> service__workpaper_remind_service
    router__workpaper_requirements --> service__workpaper_requirements_service
    router__workpaper_summary --> service__workpaper_summary_service
    router__wp_ai --> service__wp_ai_service
    router__wp_ai_interview --> service__wp_ai_service
    router__wp_ai_stocktake --> service__wp_ai_service
    router__wp_batch_ops --> service__gate_engine
    router__wp_batch_ops --> service__wp_batch_prefill
    router__wp_business_pattern --> service__dataset_query
    router__wp_cell_annotations --> service__wp_cell_annotation_service
    router__wp_chat --> service__wp_chat_service
    router__wp_cross_check --> service__wp_cross_check_service
    router__wp_data_rules --> service__note_data_extractor
    router__wp_data_rules --> service__wp_data_rules
    router__wp_data_rules --> service__wp_generic_processor
    router__wp_dependencies --> service__wp_dependency_service
    router__wp_download --> service__cloud_storage_service
    router__wp_download --> service__wp_download_service
    router__wp_eqcr_evaluation --> service__audit_logger_enhanced
    router__wp_evidence --> service__wp_evidence_service
    router__wp_explanation --> service__wp_ai_service
    router__wp_explanation --> service__wp_explanation_service
    router__wp_f2_valuation --> service__dataset_query
    router__wp_fine_rules --> service__wp_fine_rule_engine
    router__wp_i_amortization --> router__wp_h_depreciation
    router__wp_k_expense_analysis --> service__llm_service
    router__wp_manuals --> service__wp_manual_service
    router__wp_mapping --> service__llm_client
    router__wp_mapping --> service__tsj_prompt_service
    router__wp_mapping --> service__wp_mapping_service
    router__wp_prefill_preview --> service__prefill_engine
    router__wp_procedure_trim --> service__procedure_trim_engine
    router__wp_procedures --> service__wp_procedure_service
    router__wp_procedures --> service__wp_quality_score_linkage
    router__wp_progress --> service__wp_progress_service
    router__wp_review --> service__review_template_service
    router__wp_review --> service__wp_review_service
    router__wp_storage --> service__wp_storage_service
    router__wp_structure --> service__address_registry
    router__wp_structure --> service__excel_html_converter
    router__wp_structure --> service__wp_structure_bridge
    router__wp_template --> service__dataset_query
    router__wp_template --> service__prerequisite_checker
    router__wp_template --> service__template_engine
    router__wp_template --> service__wp_header_service
    router__wp_template_download --> service__wp_template_init_service
    router__wp_template_files --> service__docx_to_univer_doc_service
    router__wp_template_files --> service__wp_template_init_service
    router__wp_user_formulas --> service__formula_engine
    router__wp_user_formulas --> service__prefill_engine
    router__wp_version_search --> service__wp_version_search_service
    service__account_chart_service --> service__dataset_service
    service__account_chart_service --> service__import_engine
    service__account_chart_service --> service__import_service
    service__account_chart_service --> service__smart_import_engine
    service__adjustment_impact_service --> service__wp_mapping_service
    service__adjustment_service --> service__event_bus
    service__aging_analysis_service --> service__dataset_query
    service__ai_chat_service --> service__ai_service
    service__ai_chat_service --> service__knowledge_index_service
    service__ai_service --> service__unified_ocr_service
    service__archive_generators --> service__independence_service
    service__archive_orchestrator --> service__data_lifecycle_service
    service__archive_orchestrator --> service__export_integrity_service
    service__archive_orchestrator --> service__gate_engine
    service__archive_orchestrator --> service__gate_eval_store
    service__archive_orchestrator --> service__notification_service
    service__archive_orchestrator --> service__notification_types
    service__archive_orchestrator --> service__private_storage_service
    service__archive_orchestrator --> service__wp_storage_service
    service__archive_section_registry --> service__archive_generators
    service__archive_section_registry --> service__archive_pdf_generators
    service__archive_section_registry --> service__eqcr_memo_service
    service__archive_section_registry --> service__independence_service
    service__assignment_service --> service__event_bus
    service__assignment_service --> service__notification_types
    service__assignment_service --> service__sod_guard_service
    service__attachment_service --> service__task_center
    service__audit_report_service --> service__dataset_query
    service__batch_brief_service --> service__export_job_service
    service__batch_brief_service --> service__pm_service
    service__batch_brief_service --> service__unified_ai_service
    service__chain_orchestrator --> service__disclosure_engine
    service__chain_orchestrator --> service__prefill_engine
    service__chain_orchestrator --> service__prerequisite_checker
    service__chain_orchestrator --> service__report_engine
    service__chain_orchestrator --> service__trial_balance_service
    service__chain_orchestrator --> service__wp_template_init_service
    service__confirmation_service --> service__event_bus
    service__consistency_replay_engine --> service__trace_event_service
    service__consol_aggregation_service --> service__consol_tree_service
    service__consol_disclosure_service --> service__dataset_query
    service__consol_disclosure_service --> service__goodwill_service
    service__consol_disclosure_service --> service__minority_interest_service
    service__consol_drilldown_service --> service__consol_tree_service
    service__consol_pivot_service --> service__consol_tree_service
    service__consol_report_service --> service__goodwill_service
    service__consol_report_service --> service__minority_interest_service
    service__consol_worksheet_engine --> service__consol_tree_service
    service__contract_analysis_service --> service__ai_service
    service__dashboard_aggregator_service --> service__consistency_gate
    service__data_fetch_custom --> service__dataset_query
    service__data_validation_engine --> service__dataset_query
    service__data_validation_engine --> service__trial_balance_service
    service__dataset_query --> service__dataset_service
    service__dataset_service --> service__event_bus
    service__dataset_service --> service__import_event_outbox_service
    service__dataset_service --> service__import_queue_service
    service__dataset_service --> service__ledger_import
    service__disclosure_engine --> service__dataset_query
    service__disclosure_engine --> service__llm_client
    service__disclosure_engine --> service__note_template_service
    service__disclosure_engine --> service__version_line_service
    service__drilldown_service --> service__dataset_query
    service__eqcr_service --> service__eqcr_domain_service
    service__eqcr_service --> service__eqcr_workbench_service
    service__eqcr_shadow_compute_service --> service__consistency_replay_engine
    service__event_handlers --> service__address_registry
    service__event_handlers --> service__audit_report_service
    service__event_handlers --> service__consistency_check_service
    service__event_handlers --> service__disclosure_engine
    service__event_handlers --> service__event_bus
    service__event_handlers --> service__formula_engine
    service__event_handlers --> service__linkage_service
    service__event_handlers --> service__prefill_engine
    service__event_handlers --> service__report_engine
    service__event_handlers --> service__stale_propagation_engine
    service__event_handlers --> service__trial_balance_service
    service__event_handlers --> service__wp_review_service
    service__event_handlers --> service__wp_template_init_service
    service__export_integrity_service --> service__trace_event_service
    service__export_job_service --> service__export_integrity_service
    service__export_package_service --> service__consistency_gate
    service__export_package_service --> service__note_word_exporter
    service__export_package_service --> service__report_excel_exporter
    service__export_progress_service --> service__event_bus
    service__formula_unified --> service__data_fetch_custom
    service__formula_unified --> service__excel_html_converter
    service__gate_engine --> service__trace_event_service
    service__gate_rules_ai_content --> service__gate_engine
    service__gate_rules_chain --> service__consistency_gate
    service__gate_rules_chain --> service__gate_engine
    service__gate_rules_cross_check --> service__gate_engine
    service__gate_rules_cross_check --> service__wp_cross_check_service
    service__gate_rules_eqcr --> service__gate_engine
    service__gate_rules_phase14 --> service__consistency_replay_engine
    service__gate_rules_phase14 --> service__gate_engine
    service__gate_rules_phase14 --> service__gate_rules_ai_content
    service__gate_rules_round6 --> service__gate_engine
    service__handover_service --> service__audit_logger_enhanced
    service__handover_service --> service__notification_service
    service__handover_service --> service__notification_types
    service__import_artifact_service --> service__import_artifact_storage
    service__import_error_formatter --> service__smart_import_engine
    service__import_event_outbox_service --> service__event_bus
    service__import_event_reliability_service --> service__event_bus
    service__import_event_reliability_service --> service__import_event_outbox_service
    service__import_intelligence --> service__dataset_query
    service__import_job_runner --> service__dataset_service
    service__import_job_runner --> service__feature_flags
    service__import_job_runner --> service__import_artifact_service
    service__import_job_runner --> service__import_error_formatter
    service__import_job_runner --> service__import_job_service
    service__import_job_runner --> service__import_queue_service
    service__import_job_runner --> service__ledger_import
    service__import_job_runner --> service__ledger_import_application_service
    service__import_job_runner --> service__ledger_import_upload_service
    service__import_job_runner --> service__smart_import_engine
    service__import_service --> service__dataset_query
    service__import_service --> service__event_bus
    service__import_service --> service__import_engine
    service__import_service --> service__import_queue_service
    service__independence_service --> service__audit_logger_enhanced
    service__issue_ticket_service --> service__audit_logger_enhanced
    service__issue_ticket_service --> service__notification_service
    service__issue_ticket_service --> service__trace_event_service
    service__knowledge_index_service --> service__ai_service
    service__ledger_import --> service__audit_logger_enhanced
    service__ledger_import --> service__dataset_service
    service__ledger_import --> service__fast_writer
    service__ledger_import --> service__feature_flags
    service__ledger_import --> service__import_artifact_service
    service__ledger_import --> service__smart_import_engine
    service__ledger_import_application_service --> service__import_artifact_service
    service__ledger_import_application_service --> service__import_job_runner
    service__ledger_import_application_service --> service__import_job_service
    service__ledger_import_application_service --> service__import_queue_service
    service__ledger_import_application_service --> service__ledger_import
    service__ledger_import_application_service --> service__ledger_import_upload_service
    service__ledger_import_application_service --> service__smart_import_engine
    service__ledger_import_upload_service --> service__import_artifact_service
    service__ledger_import_upload_service --> service__import_artifact_storage
    service__ledger_penetration_service --> service__dataset_query
    service__linkage_graph_builder --> service__formula_reverse_index
    service__linkage_graph_builder --> service__stale_propagation_engine
    service__llm_service --> service__llm_metrics
    service__manager_dashboard_service --> service__notification_types
    service__mapping_service --> service__dataset_query
    service__mapping_service --> service__dataset_service
    service__mapping_service --> service__event_bus
    service__misstatement_service --> service__dataset_query
    service__note_conversion_service --> service__chain_orchestrator
    service__note_data_extractor --> service__dataset_query
    service__note_data_extractor --> service__wp_data_rules
    service__note_formula_engine --> service__llm_client
    service__note_trim_service --> service__note_template_service
    service__ocr_fields_service --> service__ocr_service_v2
    service__ocr_fields_service --> service__unified_ocr_service
    service__ocr_service_v2 --> service__ai_service
    service__offline_conflict_service --> service__trace_event_service
    service__partner_service --> service__gate_engine
    service__partner_service --> service__gate_eval_store
    service__partner_service --> service__readiness_facade
    service__pm_service --> service__llm_client
    service__pm_service --> service__task_tree_service
    service__pm_service --> service__trace_event_service
    service__prefill_engine --> service__dataset_query
    service__prefill_engine --> service__formula_engine
    service__prefill_engine --> service__wp_formula_dependency
    service__prerequisite_checker --> service__dataset_query
    service__private_storage_service --> service__cloud_storage_service
    service__private_storage_service --> service__task_center
    service__procedure_trim_engine --> service__audit_logger_enhanced
    service__project_wizard_service --> service__note_template_service
    service__qc_annual_report_service --> service__ai_contribution_watermark
    service__qc_annual_report_service --> service__export_job_service
    service__qc_dashboard_service --> service__gate_engine
    service__qc_dashboard_service --> service__gate_eval_store
    service__qc_dashboard_service --> service__readiness_facade
    service__qc_rule_dry_run_service --> service__qc_engine
    service__qc_rule_dry_run_service --> service__qc_rule_executor
    service__rc_enhanced_service --> service__trace_event_service
    service__readiness_facade --> service__gate_engine
    service__reference_doc_service --> service__knowledge_service
    service__report_engine --> service__event_bus
    service__report_engine --> service__report_config_service
    service__report_engine --> service__version_line_service
    service__report_trace_service --> service__dataset_query
    service__review_conversation_service --> service__event_bus
    service__review_notification_service --> service__event_handlers
    service__role_ai_features --> service__export_mask_service
    service__role_ai_features --> service__llm_client
    service__sampling_enhanced_service --> service__dataset_query
    service__sign_service --> service__dataset_query
    service__smart_import_engine --> service__account_chart_service
    service__smart_import_engine --> service__dataset_service
    service__smart_import_engine --> service__event_bus
    service__smart_import_engine --> service__fast_writer
    service__smart_import_engine --> service__import_validation_service
    service__sod_guard_service --> service__trace_event_service
    service__stale_propagation_engine --> service__event_bus
    service__stale_propagation_engine --> service__prefill_engine
    service__task_event_bus --> service__trace_event_service
    service__task_event_handlers --> service__qc_engine
    service__task_event_handlers --> service__task_event_bus
    service__task_tree_service --> service__trace_event_service
    service__template_engine --> service__dataset_query
    service__template_engine --> service__wp_fine_rule_engine
    service__template_engine --> service__wp_header_service
    service__trial_balance_service --> service__dataset_query
    service__trial_balance_service --> service__formula_engine
    service__triple_format_adapter --> service__excel_html_converter
    service__triple_format_adapter --> service__wp_data_rules
    service__unified_ai_service --> service__ai_plugin_service
    service__unified_ai_service --> service__ai_service
    service__unified_ai_service --> service__unified_ocr_service
    service__unified_ocr_service --> service__mineru_service
    service__version_line_service --> service__trace_event_service
    service__wopi_service --> service__cloud_storage_service
    service__wopi_service --> service__event_bus
    service__wopi_service --> service__prefill_engine
    service__wopi_service --> service__trace_event_service
    service__wopi_service --> service__version_line_service
    service__wopi_service --> service__wp_fine_rule_engine
    service__wopi_service --> service__wp_structure_bridge
    service__word_template_filler --> service__consistency_replay_engine
    service__word_template_filler --> service__export_mask_service
    service__word_template_filler --> service__export_task_service
    service__word_template_filler --> service__gt_word_engine
    service__word_template_filler --> service__report_placeholder_service
    service__word_template_filler --> service__report_snapshot_service
    service__workhour_approve_service --> service__notification_service
    service__workhour_approve_service --> service__notification_types
    service__workhour_service --> service__llm_client
    service__working_paper_service --> service__wp_review_service
    service__workpaper_fill_service --> service__ai_service
    service__workpaper_fill_service --> service__dataset_query
    service__workpaper_remind_service --> service__notification_service
    service__workpaper_remind_service --> service__notification_types
    service__workpaper_remind_service --> service__trace_event_service
    service__workpaper_requirements_service --> service__wp_manual_service
    service__wp_ai_service --> service__dataset_query
    service__wp_ai_service --> service__export_mask_service
    service__wp_ai_service --> service__llm_client
    service__wp_ai_service --> service__reference_doc_service
    service__wp_ai_service --> service__task_center
    service__wp_audit_trail_service --> service__audit_logger_enhanced
    service__wp_batch_prefill --> service__prefill_engine
    service__wp_batch_prefill --> service__wp_formula_dependency
    service__wp_chat_service --> service__dataset_query
    service__wp_chat_service --> service__export_mask_service
    service__wp_chat_service --> service__llm_client
    service__wp_download_service --> service__cloud_storage_service
    service__wp_download_service --> service__event_bus
    service__wp_download_service --> service__offline_conflict_service
    service__wp_download_service --> service__prefill_engine
    service__wp_download_service --> service__task_center
    service__wp_download_service --> service__version_line_service
    service__wp_download_service --> service__wp_structure_bridge
    service__wp_explanation_service --> service__llm_client
    service__wp_explanation_service --> service__reference_doc_service
    service__wp_explanation_service --> service__wp_manual_service
    service__wp_llm_prompts --> service__llm_client
    service__wp_llm_prompts --> service__wp_ai_service
    service__wp_ocr_fill_service --> service__wp_ocr_voucher_service
    service__wp_ocr_voucher_service --> service__unified_ocr_service
    service__wp_quality_score_linkage --> service__wp_procedure_service
    service__wp_review_service --> service__event_bus
    service__wp_review_service --> service__trace_event_service
    service__wp_scripts --> service__tsj_prompt_service
    service__wp_scripts --> service__wp_explanation_service
    service__wp_scripts --> service__wp_generic_processor
    service__wp_structure_bridge --> service__address_registry
    service__wp_structure_bridge --> service__excel_html_converter
    service__wp_structure_bridge --> service__wp_fine_rule_engine

    classDef critical fill:#FFE082,stroke:#F57F17,stroke-width:2px;
    classDef router fill:#B3E5FC,stroke:#0277BD;
    classDef service fill:#E8F5E9,stroke:#2E7D32;
    class router__account_chart,router__account_note_mapping,router__accounting_standards,router__address_registry,router__address_registry_v2,router__adjustments,router__admin_event_health,router__aging_analysis,router__ai_models,router__ai_plugins,router__ai_unified,router__annotations,router__archive,router__archive_completeness,router__assignments,router__attachments,router__audit_logs,router__audit_report,router__audit_types,router__background_jobs,router__batch_assign_enhanced,router__batch_brief,router__batch_export_progress,router__batch_review,router__cfs_worksheet,router__chain_workflow,router__component_auditor,router__confirmations,router__conflict_guard,router__consistency,router__consistency_replay,router__consol_cell_comments,router__consol_note_sections,router__consol_notes,router__consol_report,router__consol_scope,router__consol_trial,router__consol_worksheet,router__consol_worksheet_data,router__consolidation,router__continuous_audit,router__cost_overview,router__cross_cycle_breakage,router__custom_query,router__custom_templates,router__dashboard,router__dashboard_aggregator,router__data_fetch_custom,router__data_import,router__data_lifecycle,router__data_quality,router__data_validation,router__dataset_force_unbind,router__disclosure_notes,router__drilldown,router__editing_lock,router__eqcr,router__eqcr_issues,router__eqcr_judgment,router__eqcr_snapshot,router__eqcr_trends,router__event_cascade_health,router__events,router__excel_html,router__export,router__export_integrity,router__feature_flags,router__forex,router__formula,router__formula_audit_log,router__forum,router__gate,router__global_search,router__goodwill,router__gt_coding,router__health_redis,router__i18n,router__import_intelligence,router__import_templates,router__independence,router__internal_trade,router__issues,router__knowledge_base,router__knowledge_folders,router__knowledge_tsj,router__ledger_data,router__ledger_datasets,router__ledger_import_health,router__ledger_import_v2,router__ledger_penetration,router__ledger_raw_extra,router__linkage,router__linkage_bus,router__linkage_panorama,router__manager_dashboard,router__mapping,router__materiality,router__metabase,router__minority_interest,router__misstatements,router__my_reviews,router__my_todo,router__note_advanced,router__note_ai,router__note_conversion,router__note_custom_section,router__note_data_lock,router__note_export,router__note_group_template,router__note_related_workpapers,router__note_section_lock,router__note_templates,router__note_trace,router__note_trim,router__note_wp_mapping,router__notifications,router__ocr_fields,router__office_preview,router__offline_conflicts,router__partner_dashboard,router__partner_urgency,router__password_confirm,router__pbc,router__penetrate_by_amount,router__performance,router__pm_dashboard,router__presence,router__private_storage,router__procedures,router__process_record,router__project_config,router__project_permissions,router__project_wizard,router__qc,router__qc_annual_reports,router__qc_audit_log_compliance,router__qc_cases,router__qc_dashboard,router__qc_inspections,router__qc_ratings,router__qc_report_export,router__qc_rotation_due,router__qc_rules,router__qc_vr_heatmap,router__query_builder,router__reclassification,router__recycle_bin,router__regulatory,router__report_config,router__report_export,router__report_line_mapping,router__report_mapping,router__report_related_workpapers,router__report_trace,router__reports,router__review_config,router__review_conversations,router__review_recommend,router__review_records_global,router__review_templates,router__risk_summary,router__role_ai_features,router__role_context,router__rotation,router__sampling,router__sampling_enhanced,router__security,router__shared_config,router__signatures,router__sod,router__staff,router__stale_summary,router__subsequent_events,router__system_dicts,router__system_settings,router__t_accounts,router__task_center,router__task_events,router__task_tree,router__tb_sync,router__template_library,router__template_library_mgmt,router__trace,router__trial_balance,router__validation_rules,router__version_line,router__vr_coverage,router__word_export,router__workflow_status,router__workhour_approval,router__workhour_approve,router__workhour_budget,router__workhour_entries,router__workhour_list,router__workhours,router__working_paper,router__workpaper_batch_status,router__workpaper_html_preview,router__workpaper_prior_year,router__workpaper_remind,router__workpaper_requirements,router__workpaper_summary,router__wp_ai,router__wp_ai_confirm,router__wp_ai_interview,router__wp_ai_stocktake,router__wp_batch_ops,router__wp_business_pattern,router__wp_cell_annotations,router__wp_chat,router__wp_cross_check,router__wp_data_rules,router__wp_dependencies,router__wp_download,router__wp_eqcr_evaluation,router__wp_evidence,router__wp_explanation,router__wp_f2_impairment,router__wp_f2_valuation,router__wp_fine_rules,router__wp_g_classification,router__wp_g_ecl,router__wp_g_fair_value,router__wp_h_depreciation,router__wp_h_impairment,router__wp_health_dashboard,router__wp_i_amortization,router__wp_i_capitalization,router__wp_i_goodwill,router__wp_j_payroll_calc,router__wp_j_share_payment,router__wp_k_expense_analysis,router__wp_k_impairment_summary,router__wp_l_bond_amortization,router__wp_l_interest_calc,router__wp_m_equity_movement,router__wp_manuals,router__wp_mapping,router__wp_n_income_tax_calc,router__wp_prefill_context,router__wp_prefill_preview,router__wp_prerequisite_status,router__wp_procedure_status,router__wp_procedure_trim,router__wp_procedures,router__wp_progress,router__wp_review,router__wp_review_status,router__wp_search,router__wp_step_mapping,router__wp_storage,router__wp_structure,router__wp_template,router__wp_template_download,router__wp_template_files,router__wp_template_metadata,router__wp_user_formulas,router__wp_version_search router;
    class service__account_chart_service,service__accounting_standard_service,service__address_registry,service__adjustment_impact_service,service__adjustment_service,service__aging_analysis_service,service__ai_chat_service,service__ai_contribution_watermark,service__ai_plugin_service,service__ai_service,service__annotation_service,service__archive_completeness_service,service__archive_generators,service__archive_orchestrator,service__archive_pdf_generators,service__archive_section_registry,service__assignment_service,service__attachment_service,service__audit_logger_enhanced,service__audit_report_service,service__audit_type_service,service__auth_service,service__availability_fallback_service,service__background_job_service,service__batch_assign_strategy,service__batch_brief_service,service__cache_manager,service__cache_service,service__cfs_worksheet_engine,service__chain_orchestrator,service__client_lookup,service__client_quality_trend_service,service__cloud_storage_service,service__component_auditor_service,service__confirmation_service,service__conflict_guard_service,service__consistency_check_service,service__consistency_gate,service__consistency_replay_engine,service__consol_aggregation_service,service__consol_disclosure_service,service__consol_drilldown_service,service__consol_enhanced_service,service__consol_pivot_service,service__consol_report_service,service__consol_scope_service,service__consol_tree_service,service__consol_trial_service,service__consol_worksheet_engine,service__continuous_audit_service,service__contract_analysis_service,service__cost_overview_service,service__cross_cycle_breakage_service,service__custom_template_service,service__dashboard_aggregator_service,service__dashboard_service,service__data_fetch_custom,service__data_health_monitor,service__data_lifecycle_service,service__data_quality_service,service__data_validation_engine,service__dataset_query,service__dataset_service,service__disclosure_engine,service__docx_to_univer_doc_service,service__drilldown_service,service__editing_lock_service,service__elimination_service,service__encryption_service,service__eqcr_domain_service,service__eqcr_independence_service,service__eqcr_memo_service,service__eqcr_service,service__eqcr_shadow_compute_service,service__eqcr_snapshot_service,service__eqcr_workbench_service,service__equity_method_service,service__event_bus,service__event_cascade_health_service,service__event_cascade_monitor,service__event_handlers,service__excel_html_converter,service__export_integrity_service,service__export_job_service,service__export_mask_service,service__export_package_service,service__export_progress_service,service__export_task_service,service__fast_writer,service__feature_flags,service__file_scan_service,service__forex_service,service__formula_engine,service__formula_parser,service__formula_reverse_index,service__formula_unified,service__forum_service,service__gate_engine,service__gate_eval_store,service__gate_rules_ai_content,service__gate_rules_chain,service__gate_rules_cross_check,service__gate_rules_eqcr,service__gate_rules_phase14,service__gate_rules_round6,service__global_search_service,service__goodwill_service,service__gt_coding_service,service__gt_word_engine,service__handover_service,service__i18n_service,service__import_artifact_service,service__import_artifact_storage,service__import_engine,service__import_error_formatter,service__import_event_consumption_service,service__import_event_outbox_service,service__import_event_reliability_service,service__import_intelligence,service__import_job_runner,service__import_job_service,service__import_ops_audit_service,service__import_queue_service,service__import_service,service__import_slo_service,service__import_template_service,service__import_validation_service,service__independence_service,service__internal_trade_service,service__issue_ticket_service,service__knowledge_folder_service,service__knowledge_index_service,service__knowledge_service,service__ledger_data_service,service__ledger_import,service__ledger_import_application_service,service__ledger_import_upload_service,service__ledger_penetration_service,service__linkage_graph_builder,service__linkage_label_resolver,service__linkage_panorama_aggregator,service__linkage_service,service__llm_client,service__llm_metrics,service__llm_service,service__manager_dashboard_service,service__mapping_service,service__materiality_service,service__metabase_service,service__mineru_service,service__minority_interest_service,service__misstatement_service,service__my_todo_service,service__note_account_mapping_service,service__note_conversion_service,service__note_cross_reference_service,service__note_custom_section_service,service__note_data_extractor,service__note_data_lock_service,service__note_fill_engine,service__note_formula_engine,service__note_formula_generator,service__note_group_template_service,service__note_layer_strategy,service__note_md_template_parser,service__note_prior_year_import_service,service__note_rule_engine,service__note_section_lock_service,service__note_stale_service,service__note_template_service,service__note_trim_service,service__note_trim_sort_service,service__note_validation_engine,service__note_variation_analysis_service,service__note_wide_table_engine,service__note_word_exporter,service__note_wp_mapping_service,service__notification_service,service__notification_types,service__ocr_fields_service,service__ocr_service_v2,service__offline_conflict_service,service__partner_service,service__pdf_export_engine,service__performance_monitor,service__permission_service,service__pm_service,service__prefill_engine,service__prerequisite_checker,service__presence_service,service__private_storage_service,service__procedure_service,service__procedure_trim_engine,service__process_record_service,service__project_wizard_service,service__qc_annual_report_service,service__qc_case_library_service,service__qc_dashboard_service,service__qc_engine,service__qc_inspection_service,service__qc_rule_definition_service,service__qc_rule_dry_run_service,service__qc_rule_executor,service__quality_rating_service,service__rc_enhanced_service,service__readiness_facade,service__reference_doc_service,service__regulatory_service,service__report_config_service,service__report_engine,service__report_excel_exporter,service__report_export_engine,service__report_formula_service,service__report_line_mapping_service,service__report_mapping_service,service__report_note_sync_service,service__report_placeholder_service,service__report_snapshot_service,service__report_trace_service,service__retry_utils,service__review_conversation_service,service__review_notification_service,service__review_state_machine,service__review_template_service,service__reviewer_metrics_service,service__risk_summary_service,service__role_ai_features,service__role_context_service,service__rotation_check_service,service__sampling_enhanced_service,service__sampling_service,service__security_monitor,service__shared_config_service,service__sign_service,service__smart_import_engine,service__sod_guard_service,service__staff_service,service__stale_propagation_engine,service__stale_summary_aggregate,service__t_account_service,service__task_center,service__task_event_bus,service__task_event_handlers,service__task_tree_service,service__template_engine,service__template_library_service,service__trace_event_service,service__trial_balance_service,service__triple_format_adapter,service__tsj_prompt_service,service__unified_ai_service,service__unified_ocr_service,service__univer_to_xlsx,service__version_line_service,service__wopi_service,service__word_template_filler,service__workhour_approve_service,service__workhour_service,service__working_paper_service,service__workpaper_fill_service,service__workpaper_query,service__workpaper_remind_service,service__workpaper_requirements_service,service__workpaper_summary_service,service__wp_ai_service,service__wp_audit_trail_service,service__wp_batch_prefill,service__wp_cell_annotation_service,service__wp_cell_lock_service,service__wp_chat_service,service__wp_conclusion_service,service__wp_cross_check_service,service__wp_cross_index_service,service__wp_data_rules,service__wp_dependency_service,service__wp_download_service,service__wp_evidence_index,service__wp_evidence_service,service__wp_explanation_service,service__wp_fine_rule_engine,service__wp_formula_dependency,service__wp_generic_processor,service__wp_guidance_service,service__wp_header_service,service__wp_llm_prompts,service__wp_manual_service,service__wp_mapping_feedback_service,service__wp_mapping_service,service__wp_note_linkage_service,service__wp_ocr_fill_service,service__wp_ocr_voucher_service,service__wp_permission_service,service__wp_procedure_service,service__wp_progress_service,service__wp_quality_score_linkage,service__wp_quality_score_service,service__wp_review_checklist_service,service__wp_review_service,service__wp_risk_trace_service,service__wp_sampling_engine,service__wp_scripts,service__wp_sign_date_chain_service,service__wp_snapshot_service,service__wp_storage_service,service__wp_structure_bridge,service__wp_template_init_service,service__wp_template_service,service__wp_version_search_service,service__wp_visualization_service,service__xlsx_to_univer service;
    class service__audit_logger_enhanced,service__dataset_query,service__event_bus,service__gate_engine,service__trace_event_service critical;
```

## 图例

- ⚙ 绿色 = service 节点
- 🛣 蓝色 = router 节点
- ⭐ 黄色高亮 = 关键路径（入度 Top 5 service）

## 孤立节点（无入边也无出边）

下列文件未被其他 service/router 引用，也未引用任何 service/router；可能是入口路由、纯模型工具或废弃代码，建议人工 review。

- router: `account_note_mapping`
- router: `batch_review`
- router: `confirmations`
- router: `consol_cell_comments`
- router: `consol_note_sections`
- router: `consol_worksheet_data`
- router: `cost_overview`
- router: `custom_query`
- router: `data_import`
- router: `editing_lock`
- router: `eqcr_issues`
- router: `eqcr_judgment`
- router: `eqcr_snapshot`
- router: `eqcr_trends`
- router: `health_redis`
- router: `knowledge_base`
- router: `knowledge_tsj`
- router: `ledger_raw_extra`
- router: `mapping`
- router: `my_reviews`
- router: `note_related_workpapers`
- router: `note_trace`
- router: `notifications`
- router: `partner_urgency`
- router: `pbc`
- router: `penetrate_by_amount`
- router: `project_permissions`
- router: `qc_report_export`
- router: `qc_rotation_due`
- router: `query_builder`
- router: `recycle_bin`
- router: `report_line_mapping`
- router: `report_related_workpapers`
- router: `review_config`
- router: `review_recommend`
- router: `review_records_global`
- router: `review_templates`
- router: `subsequent_events`
- router: `system_dicts`
- router: `system_settings`
- router: `vr_coverage`
- router: `workflow_status`
- router: `workhour_approval`
- router: `workhour_budget`
- router: `workhour_entries`
- router: `workhour_list`
- router: `workpaper_batch_status`
- router: `wp_ai_confirm`
- router: `wp_f2_impairment`
- router: `wp_g_classification`
- router: `wp_g_ecl`
- router: `wp_g_fair_value`
- router: `wp_h_impairment`
- router: `wp_health_dashboard`
- router: `wp_i_capitalization`
- router: `wp_i_goodwill`
- router: `wp_j_payroll_calc`
- router: `wp_j_share_payment`
- router: `wp_k_impairment_summary`
- router: `wp_l_bond_amortization`
- router: `wp_l_interest_calc`
- router: `wp_m_equity_movement`
- router: `wp_n_income_tax_calc`
- router: `wp_prefill_context`
- router: `wp_prerequisite_status`
- router: `wp_procedure_status`
- router: `wp_review_status`
- router: `wp_search`
- router: `wp_step_mapping`
- router: `wp_template_metadata`
- service: `auth_service`
- service: `availability_fallback_service`
- service: `cost_overview_service`
- service: `editing_lock_service`
- service: `encryption_service`
- service: `eqcr_snapshot_service`
- service: `file_scan_service`
- service: `import_event_consumption_service`
- service: `note_account_mapping_service`
- service: `note_fill_engine`
- service: `note_layer_strategy`
- service: `note_md_template_parser`
- service: `note_rule_engine`
- service: `note_stale_service`
- service: `note_wide_table_engine`
- service: `permission_service`
- service: `report_export_engine`
- service: `report_line_mapping_service`
- service: `retry_utils`
- service: `review_state_machine`
- service: `wp_cell_lock_service`
- service: `wp_conclusion_service`
- service: `wp_cross_index_service`
- service: `wp_evidence_index`
- service: `wp_guidance_service`
- service: `wp_mapping_feedback_service`
- service: `wp_note_linkage_service`
- service: `wp_permission_service`
- service: `wp_quality_score_service`
- service: `wp_review_checklist_service`
- service: `wp_risk_trace_service`
- service: `wp_sampling_engine`
- service: `wp_sign_date_chain_service`
- service: `wp_snapshot_service`
- service: `wp_visualization_service`
