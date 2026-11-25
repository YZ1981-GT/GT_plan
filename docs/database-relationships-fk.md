# 外键约束与逻辑引用明细

> 生成日期：2026-11-18。外键取自本地开发库 `pg_constraint`（只含平台表），与 ORM 声明比对。
> 概览与分析见 `database-relationships.md`。「删除规则」是被引用行删除时数据库的动作。

## 1. 外键约束（831 条，按引用方表排序）

| 引用方表 | 列 | 被引用表 | 被引用列 | 删除规则 | 备注 |
|----------|----|----------|----------|----------|------|
| `account_chart` | project_id | `projects` | id | NO ACTION |  |
| `account_mapping` | project_id | `projects` | id | NO ACTION |  |
| `account_mapping` | created_by | `users` | id | NO ACTION |  |
| `account_package_program_status` | project_id | `projects` | id | NO ACTION |  |
| `account_package_program_status` | reviewer | `staff_members` | id | NO ACTION |  |
| `account_package_program_status` | updated_by | `staff_members` | id | NO ACTION |  |
| `acnr_project_overlay` | project_id | `projects` | id | NO ACTION |  |
| `acnr_project_overlay` | wp_id | `working_paper` | id | NO ACTION |  |
| `activation_records` | dataset_id | `ledger_datasets` | id | NO ACTION |  |
| `activation_records` | previous_dataset_id | `ledger_datasets` | id | NO ACTION |  |
| `activation_records` | project_id | `projects` | id | NO ACTION |  |
| `activation_records` | performed_by | `users` | id | NO ACTION |  |
| `adjustment_client_bookings` | booked_dataset_id | `ledger_datasets` | id | RESTRICT |  |
| `adjustment_client_bookings` | project_id | `projects` | id | CASCADE |  |
| `adjustment_client_bookings` | created_by | `users` | id | RESTRICT |  |
| `adjustment_collaboration` | project_id | `projects` | id | NO ACTION |  |
| `adjustment_collaboration` | assignee_id | `users` | id | NO ACTION |  |
| `adjustment_collaboration` | created_by | `users` | id | NO ACTION |  |
| `adjustment_collaboration` | initiator_id | `users` | id | NO ACTION |  |
| `adjustment_collaboration_event` | collaboration_id | `adjustment_collaboration` | id | NO ACTION |  |
| `adjustment_collaboration_event` | actor_id | `users` | id | NO ACTION |  |
| `adjustment_editing_locks` | project_id | `projects` | id | NO ACTION |  |
| `adjustment_editing_locks` | locked_by | `users` | id | NO ACTION |  |
| `adjustment_entries` | adjustment_id | `adjustments` | id | NO ACTION |  |
| `adjustment_import_batches` | parent_batch_id | `adjustment_import_batches` | id | RESTRICT |  |
| `adjustment_import_batches` | project_id | `projects` | id | CASCADE |  |
| `adjustment_import_batches` | uploaded_by | `users` | id | RESTRICT |  |
| `adjustment_import_group_results` | batch_id | `adjustment_import_batches` | id | CASCADE |  |
| `adjustment_import_group_results` | project_id | `projects` | id | CASCADE |  |
| `adjustment_review_tasks` | project_id | `projects` | id | CASCADE |  |
| `adjustment_review_tasks` | decided_by | `users` | id | RESTRICT |  |
| `adjustment_review_tasks` | submitted_by | `users` | id | RESTRICT |  |
| `adjustment_treatment_events` | client_booking_id | `adjustment_client_bookings` | id | RESTRICT |  |
| `adjustment_treatment_events` | reverses_event_id | `adjustment_treatment_events` | id | RESTRICT |  |
| `adjustment_treatment_events` | dataset_id | `ledger_datasets` | id | RESTRICT |  |
| `adjustment_treatment_events` | project_id | `projects` | id | CASCADE |  |
| `adjustment_treatment_events` | misstatement_id | `unadjusted_misstatements` | id | RESTRICT |  |
| `adjustment_treatment_events` | created_by | `users` | id | RESTRICT |  |
| `adjustments` | import_batch_id | `adjustment_import_batches` | id | SET NULL |  |
| `adjustments` | project_id | `projects` | id | NO ACTION |  |
| `adjustments` | created_by | `users` | id | NO ACTION |  |
| `adjustments` | reviewer_id | `users` | id | NO ACTION |  |
| `adjustments` | updated_by | `users` | id | NO ACTION |  |
| `aging_segments` | wp_index_id | `wp_index` | id | CASCADE |  |
| `ai_analysis_item` | report_id | `ai_analysis_report` | id | NO ACTION |  |
| `ai_analysis_report` | project_id | `projects` | id | NO ACTION |  |
| `ai_chat_action_receipts` | session_id | `ai_chat_session` | id | CASCADE |  |
| `ai_chat_action_receipts` | actor_id | `users` | id | NO ACTION |  |
| `ai_chat_attachments` | run_id | `ai_chat_runs` | id | SET NULL |  |
| `ai_chat_attachments` | session_id | `ai_chat_session` | id | CASCADE |  |
| `ai_chat_attachments` | project_id | `projects` | id | NO ACTION |  |
| `ai_chat_attachments` | owner_id | `users` | id | NO ACTION |  |
| `ai_chat_history` | project_id | `projects` | id | NO ACTION |  |
| `ai_chat_history` | user_id | `users` | id | NO ACTION |  |
| `ai_chat_message` | run_id | `ai_chat_runs` | id | SET NULL |  |
| `ai_chat_message` | session_id | `ai_chat_session` | id | NO ACTION |  |
| `ai_chat_run_resources` | run_id | `ai_chat_runs` | id | CASCADE |  |
| `ai_chat_run_resources` | session_id | `ai_chat_session` | id | CASCADE |  |
| `ai_chat_run_resources` | blob_id | `asset_blobs` | id | RESTRICT |  |
| `ai_chat_run_resources` | attachment_version_id | `attachment_versions` | id | RESTRICT |  |
| `ai_chat_run_resources` | actor_user_id | `users` | id | RESTRICT |  |
| `ai_chat_runs` | session_id | `ai_chat_session` | id | CASCADE |  |
| `ai_chat_runs` | project_id | `projects` | id | NO ACTION |  |
| `ai_chat_runs` | actor_id | `users` | id | NO ACTION |  |
| `ai_chat_session` | project_id | `projects` | id | NO ACTION |  |
| `ai_chat_session` | user_id | `users` | id | NO ACTION |  |
| `ai_chat_tool_calls` | run_id | `ai_chat_runs` | id | CASCADE |  |
| `ai_chat_tool_calls` | parent_call_id | `ai_chat_tool_calls` | id | SET NULL |  |
| `ai_confirmation_audit` | project_id | `projects` | id | NO ACTION |  |
| `ai_confirmation_audit` | user_id | `users` | id | NO ACTION |  |
| `ai_content` | project_id | `projects` | id | NO ACTION |  |
| `ai_content` | confirmed_by | `users` | id | NO ACTION |  |
| `ai_content_governance` | previous_version_id | `ai_content_governance` | id | RESTRICT |  |
| `ai_content_governance` | project_id | `projects` | id | RESTRICT |  |
| `ai_content_governance` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `ai_content_governance` | actor_user_id | `users` | id | RESTRICT |  |
| `ai_content_governance` | confirmed_by_user_id | `users` | id | RESTRICT |  |
| `ai_content_log` | source_message_id | `ai_chat_message` | id | RESTRICT |  |
| `ai_content_log` | citation_snapshot_id | `citation_snapshots` | id | RESTRICT |  |
| `ai_content_log` | evidence_ref_id | `evidence_refs` | id | RESTRICT |  |
| `ai_content_log` | project_id | `projects` | id | NO ACTION |  |
| `ai_content_log` | confirmed_by | `users` | id | NO ACTION |  |
| `ai_content_log` | undone_by | `users` | id | NO ACTION |  |
| `ai_content_log` | user_id | `users` | id | NO ACTION |  |
| `ai_evidence_chains` | project_id | `projects` | id | NO ACTION |  |
| `ai_evidence_items` | chain_id | `ai_evidence_chains` | id | NO ACTION |  |
| `ai_knowledge_base` | project_id | `projects` | id | NO ACTION |  |
| `ai_task_items` | message_id | `ai_chat_message` | id | SET NULL |  |
| `ai_task_items` | job_id | `ai_task_jobs` | id | CASCADE |  |
| `ai_task_jobs` | project_id | `projects` | id | CASCADE |  |
| `ai_task_jobs` | actor_id | `users` | id | NO ACTION |  |
| `ai_workpaper_fills` | task_id | `ai_workpaper_tasks` | id | NO ACTION |  |
| `ai_workpaper_fills` | workpaper_id | `working_paper` | id | NO ACTION |  |
| `ai_workpaper_tasks` | workpaper_id | `working_paper` | id | NO ACTION |  |
| `annual_independence_declarations` | project_id | `projects` | id | NO ACTION |  |
| `annual_independence_declarations` | declarant_id | `users` | id | NO ACTION |  |
| `archive_checklists` | project_id | `projects` | id | NO ACTION |  |
| `archive_checklists` | checked_by | `users` | id | NO ACTION |  |
| `archive_jobs` | project_id | `projects` | id | NO ACTION |  |
| `archive_jobs` | initiated_by | `users` | id | NO ACTION |  |
| `archive_manifest_edges` | archive_manifest_id | `archive_manifests` | id | RESTRICT |  |
| `archive_manifest_entries` | archive_manifest_id | `archive_manifests` | id | RESTRICT |  |
| `archive_manifests` | project_id | `projects` | id | RESTRICT |  |
| `archive_manifests` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `archive_manifests` | actor_user_id | `users` | id | RESTRICT |  |
| `archive_modifications` | project_id | `projects` | id | NO ACTION |  |
| `archive_modifications` | approved_by | `users` | id | NO ACTION |  |
| `archive_modifications` | created_by | `users` | id | NO ACTION |  |
| `asset_blobs` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `asset_blobs` | actor_user_id | `users` | id | RESTRICT |  |
| `attachment_versions` | blob_id | `asset_blobs` | id | RESTRICT |  |
| `attachment_versions` | previous_version_id, attachment_id, project_id, audit_year | `attachment_versions` | id, attachment_id, project_id, audit_year | RESTRICT | 仅数据库有，ORM 未声明 |
| `attachment_versions` | attachment_id, project_id, audit_year | `attachments` | id, project_id, audit_year | RESTRICT | 仅数据库有，ORM 未声明 |
| `attachment_versions` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `attachment_versions` | actor_user_id | `users` | id | RESTRICT |  |
| `attachment_working_paper` | attachment_id | `attachments` | id | NO ACTION |  |
| `attachment_working_paper` | created_by | `users` | id | NO ACTION |  |
| `attachment_working_paper` | wp_id | `working_paper` | id | NO ACTION |  |
| `attachments` | current_version_id, id, project_id, audit_year | `attachment_versions` | id, attachment_id, project_id, audit_year | RESTRICT | 仅数据库有，ORM 未声明 |
| `attachments` | project_id | `projects` | id | NO ACTION |  |
| `attachments` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `attachments` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `attachments` | actor_user_id | `users` | id | RESTRICT |  |
| `attachments` | actor_user_id | `users` | id | RESTRICT |  |
| `attachments` | created_by | `users` | id | NO ACTION |  |
| `attachments` | ocr_confirmed_by | `users` | id | NO ACTION |  |
| `audit_findings` | project_id | `projects` | id | NO ACTION |  |
| `audit_findings` | created_by | `users` | id | NO ACTION |  |
| `audit_plans` | project_id | `projects` | id | NO ACTION |  |
| `audit_plans` | approved_by | `users` | id | NO ACTION |  |
| `audit_plans` | created_by | `users` | id | NO ACTION |  |
| `audit_procedures` | project_id | `projects` | id | NO ACTION |  |
| `audit_procedures` | executed_by | `users` | id | NO ACTION |  |
| `audit_report` | bound_dataset_id | `ledger_datasets` | id | RESTRICT |  |
| `audit_report` | project_id | `projects` | id | NO ACTION |  |
| `audit_report` | created_by | `users` | id | NO ACTION |  |
| `audit_report` | updated_by | `users` | id | NO ACTION |  |
| `background_job_items` | job_id | `background_jobs` | id | NO ACTION |  |
| `background_job_items` | wp_id | `working_paper` | id | NO ACTION |  |
| `background_jobs` | project_id | `projects` | id | NO ACTION |  |
| `background_jobs` | initiated_by | `users` | id | NO ACTION |  |
| `bad_debt_detail_rows` | parent_row_id | `bad_debt_detail_rows` | id | CASCADE |  |
| `bad_debt_detail_rows` | wp_index_id | `wp_index` | id | CASCADE |  |
| `budget_hours` | project_id | `projects` | id | NO ACTION |  |
| `cell_annotations` | project_id | `projects` | id | NO ACTION |  |
| `cell_annotations` | author_id | `users` | id | NO ACTION |  |
| `cfs_adjustments` | project_id | `projects` | id | NO ACTION |  |
| `cfs_adjustments` | created_by | `users` | id | NO ACTION |  |
| `check_ins` | staff_id | `staff_members` | id | NO ACTION |  |
| `checklist_responses` | project_id | `projects` | id | NO ACTION | 仅数据库有，ORM 未声明 |
| `checklist_responses` | updated_by | `users` | id | NO ACTION | 仅数据库有，ORM 未声明 |
| `checklist_responses` | wp_id | `working_paper` | id | NO ACTION | 仅数据库有，ORM 未声明 |
| `citation_snapshots` | ai_content_log_id | `ai_content_log` | id | RESTRICT |  |
| `citation_snapshots` | evidence_ref_id | `evidence_refs` | id | RESTRICT |  |
| `citation_snapshots` | project_id | `projects` | id | RESTRICT |  |
| `citation_snapshots` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `citation_snapshots` | actor_user_id | `users` | id | RESTRICT |  |
| `companies` | project_id | `projects` | id | NO ACTION |  |
| `component_auditors` | project_id | `projects` | id | NO ACTION |  |
| `component_instructions` | component_auditor_id | `component_auditors` | id | NO ACTION |  |
| `component_instructions` | project_id | `projects` | id | NO ACTION |  |
| `component_instructions` | created_by | `users` | id | NO ACTION |  |
| `component_instructions` | updated_by | `users` | id | NO ACTION |  |
| `component_results` | component_auditor_id | `component_auditors` | id | NO ACTION |  |
| `component_results` | project_id | `projects` | id | NO ACTION |  |
| `config_references` | project_id | `projects` | id | NO ACTION |  |
| `config_references` | template_id | `shared_config_templates` | id | NO ACTION |  |
| `config_references` | applied_by | `users` | id | NO ACTION |  |
| `confirmation_ai_check` | confirmation_list_id | `confirmation_lists` | id | NO ACTION |  |
| `confirmation_ai_check` | confirmed_by | `users` | id | NO ACTION |  |
| `confirmation_attachment_link` | attachment_id | `attachments` | id | CASCADE |  |
| `confirmation_attachment_link` | confirmation_id | `confirmations` | id | CASCADE |  |
| `confirmation_attachments` | confirmation_list_id | `confirmation_lists` | id | NO ACTION |  |
| `confirmation_attachments` | uploaded_by | `users` | id | NO ACTION |  |
| `confirmation_letters` | confirmation_list_id | `confirmation_lists` | id | NO ACTION |  |
| `confirmation_lists` | project_id | `projects` | id | NO ACTION |  |
| `confirmation_lists` | approved_by | `users` | id | NO ACTION |  |
| `confirmation_lists` | created_by | `users` | id | NO ACTION |  |
| `confirmation_results` | confirmation_list_id | `confirmation_lists` | id | NO ACTION |  |
| `confirmation_results` | received_by | `users` | id | NO ACTION |  |
| `confirmation_summaries` | confirmation_list_id | `confirmation_lists` | id | NO ACTION |  |
| `confirmation_summaries` | prepared_by | `users` | id | NO ACTION |  |
| `confirmations` | project_id | `projects` | id | NO ACTION |  |
| `confirmations` | created_by | `users` | id | NO ACTION |  |
| `confirmations` | wp_id | `working_paper` | id | NO ACTION |  |
| `consol_artifact` | operation_id | `consol_operation` | id | SET NULL |  |
| `consol_artifact` | project_id | `projects` | id | CASCADE |  |
| `consol_artifact` | report_run_id | `report_generation_run` | id | RESTRICT |  |
| `consol_artifact` | created_by | `users` | id | SET NULL |  |
| `consol_note_detail_template` | created_by | `users` | id | SET NULL |  |
| `consol_note_detail_template_version` | template_id | `consol_note_detail_template` | id | CASCADE |  |
| `consol_note_detail_template_version` | created_by | `users` | id | SET NULL |  |
| `consol_note_mapping_binding` | rule_id | `consol_note_mapping_rule` | id | CASCADE |  |
| `consol_note_mapping_binding` | project_id | `projects` | id | CASCADE |  |
| `consol_note_mapping_rule` | template_version_id | `consol_note_detail_template_version` | id | RESTRICT |  |
| `consol_note_mapping_rule` | project_id | `projects` | id | CASCADE |  |
| `consol_note_mapping_rule` | confirmed_by | `users` | id | SET NULL |  |
| `consol_note_template_binding` | template_version_id | `consol_note_detail_template_version` | id | RESTRICT |  |
| `consol_note_template_binding` | project_id | `projects` | id | CASCADE |  |
| `consol_note_template_binding` | bound_by | `users` | id | SET NULL |  |
| `consol_operation` | superseded_by | `consol_operation` | id | SET NULL |  |
| `consol_operation` | project_id | `projects` | id | CASCADE |  |
| `consol_operation` | triggered_by | `users` | id | SET NULL |  |
| `consol_push_run` | operation_id | `consol_operation` | id | SET NULL |  |
| `consol_push_run` | project_id | `projects` | id | CASCADE |  |
| `consol_query_template` | project_id | `projects` | id | NO ACTION |  |
| `consol_scope` | project_id | `projects` | id | NO ACTION |  |
| `consol_scope_confirmation_nodes` | confirmation_id | `consol_scope_confirmations` | id | CASCADE |  |
| `consol_scope_confirmation_nodes` | host_project_id | `projects` | id | SET NULL |  |
| `consol_scope_confirmation_nodes` | project_id | `projects` | id | SET NULL |  |
| `consol_scope_confirmations` | project_id | `projects` | id | CASCADE |  |
| `consol_scope_confirmations` | confirmed_by | `users` | id | RESTRICT |  |
| `consol_snapshots` | project_id | `projects` | id | NO ACTION |  |
| `consol_snapshots` | created_by | `users` | id | NO ACTION |  |
| `consol_trial` | project_id | `projects` | id | NO ACTION |  |
| `consol_workpaper_instance` | latest_artifact_id | `consol_artifact` | id | SET NULL |  |
| `consol_workpaper_instance` | latest_operation_id | `consol_operation` | id | SET NULL |  |
| `consol_workpaper_instance` | project_id | `projects` | id | CASCADE |  |
| `consol_workpaper_instance` | working_paper_id | `working_paper` | id | CASCADE |  |
| `consol_workpaper_instance` | wp_index_id | `wp_index` | id | CASCADE |  |
| `consol_worksheet` | project_id | `projects` | id | NO ACTION |  |
| `cross_check_results` | project_id | `projects` | id | NO ACTION |  |
| `cross_module_conflicts` | project_id | `projects` | id | NO ACTION |  |
| `cross_module_conflicts` | resolved_by | `users` | id | NO ACTION |  |
| `custom_query_templates` | created_by | `users` | id | NO ACTION |  |
| `custom_query_templates` | creator_id | `users` | id | CASCADE |  |
| `custom_workbook_unit_authorities` | created_by | `users` | id | RESTRICT |  |
| `custom_workbook_unit_authorities` | working_paper_id | `working_paper` | id | RESTRICT |  |
| `deliverable_snapshots` | project_id | `projects` | id | NO ACTION |  |
| `direction_override` | project_id | `projects` | id | NO ACTION |  |
| `direction_override` | override_by | `staff_members` | id | NO ACTION |  |
| `disclosure_notes` | bound_dataset_id | `ledger_datasets` | id | RESTRICT |  |
| `disclosure_notes` | project_id | `projects` | id | NO ACTION |  |
| `disclosure_notes` | last_sync_user_id | `users` | id | SET NULL |  |
| `disclosure_notes` | updated_by | `users` | id | NO ACTION |  |
| `disclosure_notes` | last_sync_wp_id | `working_paper` | id | SET NULL |  |
| `dispatch_records` | project_id | `projects` | id | NO ACTION |  |
| `dispatch_records` | dispatched_by | `users` | id | NO ACTION |  |
| `document_extracted` | document_scan_id | `document_scan` | id | NO ACTION |  |
| `document_extracted` | confirmed_by | `users` | id | NO ACTION |  |
| `document_match` | document_scan_id | `document_scan` | id | NO ACTION |  |
| `document_scan` | project_id | `projects` | id | NO ACTION |  |
| `document_scan` | uploaded_by | `users` | id | NO ACTION |  |
| `draft_refresh_snapshot` | refresh_id | `draft_refresh_audit` | id | NO ACTION |  |
| `editing_locks` | holder_id | `users` | id | NO ACTION |  |
| `elimination_entries` | project_id | `projects` | id | NO ACTION |  |
| `elimination_entries` | created_by | `users` | id | NO ACTION |  |
| `elimination_entries` | reviewer_id | `users` | id | NO ACTION |  |
| `elimination_entries` | updated_by | `users` | id | NO ACTION |  |
| `eqcr_disagreement_resolutions` | eqcr_opinion_id | `eqcr_opinions` | id | NO ACTION |  |
| `eqcr_disagreement_resolutions` | project_id | `projects` | id | NO ACTION |  |
| `eqcr_opinions` | project_id | `projects` | id | NO ACTION |  |
| `eqcr_opinions` | created_by | `users` | id | NO ACTION |  |
| `eqcr_review_notes` | project_id | `projects` | id | NO ACTION |  |
| `eqcr_review_notes` | created_by | `users` | id | NO ACTION |  |
| `eqcr_shadow_computations` | project_id | `projects` | id | NO ACTION |  |
| `eqcr_shadow_computations` | created_by | `users` | id | NO ACTION |  |
| `eqcr_snapshots` | project_id | `projects` | id | NO ACTION |  |
| `eqcr_snapshots` | created_by | `users` | id | NO ACTION |  |
| `event_outbox_dlq` | original_event_id | `import_event_outbox` | id | SET NULL |  |
| `event_outbox_dlq` | project_id | `projects` | id | NO ACTION |  |
| `event_outbox_dlq` | resolved_by | `users` | id | NO ACTION |  |
| `evidence_audit_command_roots` | project_id | `projects` | id | RESTRICT |  |
| `evidence_audit_command_roots` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `evidence_audit_command_roots` | actor_user_id | `users` | id | RESTRICT |  |
| `evidence_audit_transitions` | command_root_id | `evidence_audit_command_roots` | id | RESTRICT |  |
| `evidence_audit_transitions` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `evidence_audit_transitions` | actor_user_id | `users` | id | RESTRICT |  |
| `evidence_chain` | project_id | `projects` | id | NO ACTION |  |
| `evidence_dependencies` | evidence_ref_id | `evidence_refs` | id | RESTRICT |  |
| `evidence_dependencies` | project_id | `projects` | id | RESTRICT |  |
| `evidence_dependencies` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `evidence_dependencies` | actor_user_id | `users` | id | RESTRICT |  |
| `evidence_inbox` | project_id | `projects` | id | RESTRICT |  |
| `evidence_inbox` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `evidence_inbox` | actor_user_id | `users` | id | RESTRICT |  |
| `evidence_links` | attachment_id | `attachments` | id | NO ACTION |  |
| `evidence_links` | wp_id | `working_paper` | id | NO ACTION |  |
| `evidence_migration_checkpoints` | project_id | `projects` | id | RESTRICT |  |
| `evidence_migration_checkpoints` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `evidence_migration_checkpoints` | actor_user_id | `users` | id | RESTRICT |  |
| `evidence_outbox` | command_root_id | `evidence_audit_command_roots` | id | RESTRICT |  |
| `evidence_outbox` | project_id | `projects` | id | RESTRICT |  |
| `evidence_outbox` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `evidence_outbox` | actor_user_id | `users` | id | RESTRICT |  |
| `evidence_quality_snapshots` | project_id | `projects` | id | RESTRICT |  |
| `evidence_quality_snapshots` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `evidence_quality_snapshots` | actor_user_id | `users` | id | RESTRICT |  |
| `evidence_quarantine_handles` | upload_attempt_id | `evidence_upload_attempts` | id | RESTRICT |  |
| `evidence_quarantine_handles` | project_id | `projects` | id | RESTRICT |  |
| `evidence_quarantine_handles` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `evidence_quarantine_handles` | actor_user_id | `users` | id | RESTRICT |  |
| `evidence_refs` | attachment_version_id | `attachment_versions` | id | RESTRICT |  |
| `evidence_refs` | project_id | `projects` | id | RESTRICT |  |
| `evidence_refs` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `evidence_refs` | actor_user_id | `users` | id | RESTRICT |  |
| `evidence_refs` | created_by | `users` | id | RESTRICT |  |
| `evidence_tombstones` | project_id | `projects` | id | RESTRICT |  |
| `evidence_tombstones` | purged_by_user_id | `users` | id | RESTRICT |  |
| `evidence_upload_attempts` | command_root_id | `evidence_audit_command_roots` | id | RESTRICT | 仅数据库有，ORM 未声明 |
| `evidence_upload_attempts` | project_id | `projects` | id | RESTRICT |  |
| `evidence_upload_attempts` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `evidence_upload_attempts` | actor_user_id | `users` | id | RESTRICT |  |
| `export_job_attempts` | item_id | `export_job_items_v2` | id | NO ACTION |  |
| `export_job_attempts` | job_id | `export_jobs_v2` | id | NO ACTION |  |
| `export_job_items_v2` | job_id | `export_jobs_v2` | id | NO ACTION |  |
| `export_job_items_v2` | word_export_task_id | `word_export_task` | id | NO ACTION |  |
| `export_jobs_v2` | project_id | `projects` | id | NO ACTION |  |
| `export_jobs_v2` | initiated_by | `users` | id | NO ACTION |  |
| `export_tasks` | project_id | `projects` | id | NO ACTION |  |
| `export_tasks` | created_by | `users` | id | NO ACTION |  |
| `fill_preview_sessions` | project_id | `projects` | id | NO ACTION |  |
| `fill_preview_sessions` | user_id | `users` | id | NO ACTION |  |
| `financial_report` | project_id | `projects` | id | NO ACTION |  |
| `financial_report` | run_id | `report_generation_run` | id | SET NULL |  |
| `financial_report` | run_id | `report_generation_run` | id | SET NULL |  |
| `forex_translation` | project_id | `projects` | id | NO ACTION |  |
| `formula_push_run` | project_id | `projects` | id | CASCADE |  |
| `formula_push_state` | last_run_id | `formula_push_run` | id | SET NULL |  |
| `formula_push_state` | project_id | `projects` | id | CASCADE |  |
| `formula_push_state` | wp_id | `working_paper` | id | CASCADE |  |
| `formula_runtime_outbox` | run_id | `draft_refresh_audit` | id | NO ACTION |  |
| `formula_setting` | template_id | `formula_template` | id | CASCADE |  |
| `formula_setting` | project_id | `projects` | id | CASCADE |  |
| `formula_sync_item` | project_id | `projects` | id | CASCADE |  |
| `formula_template` | owner_project_id | `projects` | id | SET NULL |  |
| `formula_template` | owner_user_id | `users` | id | NO ACTION |  |
| `formula_template_subscription` | template_id | `formula_template` | id | NO ACTION |  |
| `formula_template_subscription` | project_id | `projects` | id | CASCADE |  |
| `formula_template_version` | template_id | `formula_template` | id | CASCADE |  |
| `forum_comments` | post_id | `forum_posts` | id | NO ACTION |  |
| `forum_comments` | author_id | `users` | id | NO ACTION |  |
| `forum_posts` | author_id | `users` | id | NO ACTION |  |
| `going_concern_evaluations` | project_id | `projects` | id | NO ACTION |  |
| `going_concern_evaluations` | created_by | `users` | id | NO ACTION |  |
| `going_concern_indicators` | evaluation_id | `going_concern_evaluations` | id | NO ACTION |  |
| `goodwill_calc` | project_id | `projects` | id | NO ACTION |  |
| `group_note_template_baseline` | parent_baseline_id | `group_note_template_baseline` | id | NO ACTION |  |
| `group_note_template_baseline` | parent_project_id | `projects` | id | NO ACTION |  |
| `group_note_template_baseline` | created_by | `users` | id | NO ACTION |  |
| `guidance_exemption_record` | project_id | `projects` | id | CASCADE |  |
| `guidance_handoff_visibility` | superseded_by | `guidance_handoff_visibility` | id | SET NULL | 仅数据库有，ORM 未声明 |
| `guidance_publication` | superseded_by | `guidance_publication` | id | SET NULL |  |
| `guidance_publication_event` | publication_id | `guidance_publication` | id | CASCADE |  |
| `handover_records` | executed_by | `users` | id | NO ACTION |  |
| `handover_records` | from_staff_id | `users` | id | NO ACTION |  |
| `handover_records` | to_staff_id | `users` | id | NO ACTION |  |
| `import_artifacts` | project_id | `projects` | id | NO ACTION |  |
| `import_artifacts` | created_by | `users` | id | NO ACTION |  |
| `import_batches` | project_id | `projects` | id | NO ACTION |  |
| `import_batches` | created_by | `users` | id | NO ACTION |  |
| `import_column_mapping_history` | override_parent_id | `import_column_mapping_history` | id | SET NULL |  |
| `import_column_mapping_history` | project_id | `projects` | id | CASCADE |  |
| `import_event_consumptions` | project_id | `projects` | id | NO ACTION |  |
| `import_event_outbox` | project_id | `projects` | id | NO ACTION |  |
| `import_jobs` | artifact_id | `import_artifacts` | id | NO ACTION |  |
| `import_jobs` | project_id | `projects` | id | NO ACTION |  |
| `import_jobs` | created_by | `users` | id | NO ACTION |  |
| `interim_survival_checks` | project_id | `projects` | id | NO ACTION |  |
| `internal_ar_ap` | project_id | `projects` | id | NO ACTION |  |
| `internal_trade` | project_id | `projects` | id | NO ACTION |  |
| `knowledge_documents` | blob_id | `asset_blobs` | id | RESTRICT |  |
| `knowledge_documents` | folder_id | `knowledge_folders` | id | NO ACTION |  |
| `knowledge_documents` | created_by | `users` | id | NO ACTION |  |
| `knowledge_evidence_promotions` | source_blob_id | `asset_blobs` | id | RESTRICT |  |
| `knowledge_evidence_promotions` | target_attachment_version_id | `attachment_versions` | id | RESTRICT |  |
| `knowledge_evidence_promotions` | target_attachment_id | `attachments` | id | RESTRICT |  |
| `knowledge_evidence_promotions` | source_document_id | `knowledge_documents` | id | RESTRICT |  |
| `knowledge_evidence_promotions` | project_id | `projects` | id | RESTRICT |  |
| `knowledge_evidence_promotions` | actor_user_id | `users` | id | RESTRICT |  |
| `knowledge_folders` | parent_id | `knowledge_folders` | id | NO ACTION |  |
| `knowledge_folders` | created_by | `users` | id | NO ACTION |  |
| `ledger_datasets` | job_id | `import_jobs` | id | NO ACTION |  |
| `ledger_datasets` | previous_dataset_id | `ledger_datasets` | id | NO ACTION |  |
| `ledger_datasets` | project_id | `projects` | id | NO ACTION |  |
| `ledger_datasets` | activated_by | `users` | id | NO ACTION |  |
| `ledger_datasets` | created_by | `users` | id | NO ACTION |  |
| `ledger_import_attempts` | base_dataset_id | `ledger_datasets` | id | SET NULL |  |
| `ledger_import_attempts` | dataset_id | `ledger_datasets` | id | SET NULL |  |
| `ledger_import_attempts` | project_id | `projects` | id | CASCADE |  |
| `ledger_import_attempts` | created_by | `users` | id | SET NULL |  |
| `legacy_attachment_alias` | attachment_version_id, attachment_id, project_id, audit_year | `attachment_versions` | id, attachment_id, project_id, audit_year | RESTRICT | 仅数据库有，ORM 未声明 |
| `legacy_attachment_alias` | attachment_id, project_id, audit_year | `attachments` | id, project_id, audit_year | RESTRICT | 仅数据库有，ORM 未声明 |
| `legacy_attachment_alias` | project_id | `projects` | id | RESTRICT |  |
| `legal_hold_scopes` | legal_hold_id | `legal_holds` | id | RESTRICT |  |
| `legal_hold_scopes` | project_id | `projects` | id | RESTRICT |  |
| `legal_holds` | project_id | `projects` | id | RESTRICT |  |
| `legal_holds` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `legal_holds` | actor_user_id | `users` | id | RESTRICT |  |
| `legal_holds` | released_by_user_id | `users` | id | RESTRICT |  |
| `logs` | user_id | `users` | id | NO ACTION |  |
| `management_letters` | project_id | `projects` | id | NO ACTION |  |
| `management_letters` | created_by | `users` | id | NO ACTION |  |
| `materiality` | project_id | `projects` | id | NO ACTION |  |
| `materiality` | calculated_by | `users` | id | NO ACTION |  |
| `minority_interest` | project_id | `projects` | id | NO ACTION |  |
| `note_content_template_versions` | template_id | `note_content_templates` | id | RESTRICT |  |
| `note_content_template_versions` | source_project_id | `projects` | id | RESTRICT |  |
| `note_content_template_versions` | created_by | `users` | id | SET NULL |  |
| `note_content_templates` | current_version_id | `note_content_template_versions` | id | SET NULL |  |
| `note_content_templates` | owner_group_project_id | `projects` | id | RESTRICT |  |
| `note_content_templates` | created_by | `users` | id | SET NULL |  |
| `note_content_templates` | owner_user_id | `users` | id | RESTRICT |  |
| `note_formula_run` | project_id | `projects` | id | CASCADE |  |
| `note_formula_run` | triggered_by | `users` | id | SET NULL |  |
| `note_section_instances` | project_id | `projects` | id | NO ACTION |  |
| `note_section_version_tree` | parent_node_id | `note_section_version_tree` | id | NO ACTION |  |
| `note_section_version_tree` | project_id | `projects` | id | NO ACTION |  |
| `note_section_version_tree` | created_by | `users` | id | NO ACTION |  |
| `note_text_batch_applications` | template_version_id | `note_content_template_versions` | id | RESTRICT |  |
| `note_text_batch_applications` | target_project_id | `projects` | id | RESTRICT |  |
| `note_text_batch_applications` | applied_by | `users` | id | SET NULL |  |
| `note_trim_schemes` | project_id | `projects` | id | NO ACTION |  |
| `note_trim_schemes` | created_by | `users` | id | NO ACTION |  |
| `note_validation_results` | project_id | `projects` | id | NO ACTION |  |
| `note_validation_results` | validated_by | `users` | id | NO ACTION |  |
| `notifications` | recipient_id | `users` | id | NO ACTION |  |
| `notifications` | recipient_user_id | `users` | id | NO ACTION |  |
| `ocr_confirmations` | ocr_job_id | `ocr_jobs` | id | RESTRICT |  |
| `ocr_confirmations` | ocr_result_id | `ocr_results` | id | RESTRICT |  |
| `ocr_confirmations` | project_id | `projects` | id | RESTRICT |  |
| `ocr_confirmations` | confirmed_by_user_id | `users` | id | RESTRICT |  |
| `ocr_job_transitions` | command_root_id | `evidence_audit_command_roots` | id | RESTRICT |  |
| `ocr_job_transitions` | ocr_job_id | `ocr_jobs` | id | RESTRICT |  |
| `ocr_job_transitions` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `ocr_job_transitions` | actor_user_id | `users` | id | RESTRICT |  |
| `ocr_jobs` | attachment_version_id | `attachment_versions` | id | RESTRICT |  |
| `ocr_jobs` | command_root_id | `evidence_audit_command_roots` | id | RESTRICT |  |
| `ocr_jobs` | project_id | `projects` | id | RESTRICT |  |
| `ocr_jobs` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `ocr_jobs` | actor_user_id | `users` | id | RESTRICT |  |
| `ocr_results` | attachment_version_id | `attachment_versions` | id | RESTRICT |  |
| `ocr_results` | ocr_job_id | `ocr_jobs` | id | RESTRICT |  |
| `ocr_results` | project_id | `projects` | id | RESTRICT |  |
| `ocr_results` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `ocr_results` | actor_user_id | `users` | id | RESTRICT |  |
| `ocr_writeback_staging` | ocr_writeback_id | `ocr_writebacks` | id | RESTRICT |  |
| `ocr_writeback_staging` | project_id | `projects` | id | RESTRICT |  |
| `ocr_writebacks` | command_root_id | `evidence_audit_command_roots` | id | RESTRICT |  |
| `ocr_writebacks` | ocr_job_id | `ocr_jobs` | id | RESTRICT |  |
| `ocr_writebacks` | project_id | `projects` | id | RESTRICT |  |
| `ocr_writebacks` | written_by_user_id | `users` | id | RESTRICT |  |
| `partner_rotation_overrides` | approved_by_chief_risk_partner | `users` | id | NO ACTION |  |
| `partner_rotation_overrides` | approved_by_compliance_partner | `users` | id | NO ACTION |  |
| `partner_rotation_overrides` | staff_id | `users` | id | NO ACTION |  |
| `pbc_checklist` | project_id | `projects` | id | NO ACTION |  |
| `pbc_checklist` | received_by | `users` | id | NO ACTION |  |
| `pbc_checklist` | requested_by | `users` | id | NO ACTION |  |
| `platform_job_attempts` | job_id | `platform_jobs` | id | CASCADE |  |
| `platform_jobs` | project_id | `projects` | id | CASCADE |  |
| `platform_jobs` | actor_id | `users` | id | RESTRICT |  |
| `procedure_instance_identity_v217_backup` | instance_id | `procedure_instances` | id | CASCADE | 仅数据库有，ORM 未声明 |
| `procedure_instances` | parent_id | `procedure_instances` | id | NO ACTION |  |
| `procedure_instances` | project_id | `projects` | id | NO ACTION |  |
| `procedure_instances` | assigned_to | `staff_members` | id | NO ACTION |  |
| `procedure_operation_previews` | project_id | `projects` | id | NO ACTION |  |
| `procedure_operation_previews` | actor_user_id | `users` | id | NO ACTION |  |
| `procedure_row_definition_revisions` | definition_key | `procedure_row_definitions` | definition_key | NO ACTION |  |
| `procedure_row_task_history` | task_id | `procedure_row_tasks` | id | NO ACTION |  |
| `procedure_row_task_history` | project_id | `projects` | id | NO ACTION |  |
| `procedure_row_task_history` | new_assignee_staff_id | `staff_members` | id | NO ACTION |  |
| `procedure_row_task_history` | new_reviewer_staff_id | `staff_members` | id | NO ACTION |  |
| `procedure_row_task_history` | old_assignee_staff_id | `staff_members` | id | NO ACTION |  |
| `procedure_row_task_history` | old_reviewer_staff_id | `staff_members` | id | NO ACTION |  |
| `procedure_row_task_history` | actor_user_id | `users` | id | NO ACTION |  |
| `procedure_row_tasks` | definition_key | `procedure_row_definitions` | definition_key | NO ACTION |  |
| `procedure_row_tasks` | project_id | `projects` | id | NO ACTION |  |
| `procedure_row_tasks` | assignee_staff_id | `staff_members` | id | NO ACTION |  |
| `procedure_row_tasks` | reviewer_staff_id | `staff_members` | id | NO ACTION |  |
| `procedure_row_tasks` | wp_id | `working_paper` | id | NO ACTION |  |
| `procedure_row_tasks` | wp_index_id | `wp_index` | id | NO ACTION |  |
| `procedure_template_revisions` | activated_by | `users` | id | NO ACTION |  |
| `procedure_trim_cycle_confirmations` | source_preview_id | `procedure_operation_previews` | id | RESTRICT |  |
| `procedure_trim_cycle_confirmations` | project_id | `projects` | id | CASCADE |  |
| `procedure_trim_cycle_confirmations` | confirmed_by | `users` | id | RESTRICT |  |
| `procedure_trim_schemes` | project_id | `projects` | id | NO ACTION |  |
| `procedure_trim_schemes` | created_by | `users` | id | NO ACTION |  |
| `project_assignments` | project_id | `projects` | id | NO ACTION |  |
| `project_assignments` | staff_id | `staff_members` | id | NO ACTION |  |
| `project_assignments` | assigned_by | `users` | id | NO ACTION |  |
| `project_batch_import_plans` | actor_user_id | `users` | id | RESTRICT |  |
| `project_classification_v219_backup` | project_id | `projects` | id | CASCADE | 仅数据库有，ORM 未声明 |
| `project_creation_grants` | granted_by | `users` | id | RESTRICT |  |
| `project_creation_grants` | grantee_user_id | `users` | id | RESTRICT |  |
| `project_creation_grants` | revoked_by | `users` | id | RESTRICT |  |
| `project_guidance_supplement` | base_publication_id | `guidance_publication` | id | SET NULL |  |
| `project_guidance_supplement` | project_id | `projects` | id | CASCADE |  |
| `project_sync` | project_id | `projects` | id | NO ACTION |  |
| `project_sync` | last_synced_by | `users` | id | NO ACTION |  |
| `project_sync` | locked_by | `users` | id | NO ACTION |  |
| `project_template_selections` | project_id | `projects` | id | NO ACTION |  |
| `project_template_selections` | template_id | `template_library` | id | NO ACTION |  |
| `project_template_selections` | selected_by | `users` | id | NO ACTION |  |
| `project_timeline` | project_id | `projects` | id | NO ACTION |  |
| `project_users` | project_id | `projects` | id | NO ACTION |  |
| `project_users` | user_id | `users` | id | NO ACTION |  |
| `project_workbook_sheet_entry` | workbook_instance_id | `project_workbook_instance` | workbook_instance_id | CASCADE | 仅数据库有，ORM 未声明 |
| `project_workpaper_sheet_override` | project_id | `projects` | id | CASCADE |  |
| `project_workpaper_sheet_override` | created_by | `users` | id | NO ACTION |  |
| `projects` | accounting_standard_id | `accounting_standards` | id | NO ACTION |  |
| `projects` | parent_project_id | `projects` | id | NO ACTION |  |
| `projects` | budgeted_by | `users` | id | NO ACTION |  |
| `projects` | consol_lock_by | `users` | id | NO ACTION |  |
| `projects` | created_by | `users` | id | NO ACTION |  |
| `projects` | manager_id | `users` | id | NO ACTION |  |
| `projects` | partner_id | `users` | id | NO ACTION |  |
| `projects` | updated_by | `users` | id | NO ACTION |  |
| `qc_inspection_items` | inspection_id | `qc_inspections` | id | NO ACTION |  |
| `qc_inspection_records` | inspection_item_id | `qc_inspection_items` | id | NO ACTION |  |
| `qc_inspections` | project_id | `projects` | id | NO ACTION |  |
| `query_artifacts` | project_id | `projects` | id | CASCADE |  |
| `query_artifacts` | run_id | `query_runs` | id | SET NULL |  |
| `query_artifacts` | user_id | `users` | id | RESTRICT |  |
| `query_runs` | project_id | `projects` | id | CASCADE |  |
| `query_runs` | user_id | `users` | id | RESTRICT |  |
| `regulatory_filing` | project_id | `projects` | id | NO ACTION |  |
| `related_party_registry` | project_id | `projects` | id | NO ACTION |  |
| `related_party_transactions` | project_id | `projects` | id | NO ACTION |  |
| `related_party_transactions` | related_party_id | `related_party_registry` | id | NO ACTION |  |
| `report_generation_run` | operation_id | `consol_operation` | id | SET NULL |  |
| `report_generation_run` | project_id | `projects` | id | CASCADE |  |
| `report_generation_run` | triggered_by | `users` | id | SET NULL |  |
| `report_line_mapping` | project_id | `projects` | id | NO ACTION |  |
| `report_line_mapping` | created_by | `users` | id | NO ACTION |  |
| `report_snapshot` | project_id | `projects` | id | NO ACTION |  |
| `report_snapshot` | created_by | `users` | id | NO ACTION |  |
| `review_closes` | command_root_id | `evidence_audit_command_roots` | id | RESTRICT |  |
| `review_closes` | project_id | `projects` | id | RESTRICT |  |
| `review_closes` | closed_by_user_id | `users` | id | RESTRICT |  |
| `review_conversations` | project_id | `projects` | id | NO ACTION |  |
| `review_conversations` | initiator_id | `users` | id | NO ACTION |  |
| `review_conversations` | target_id | `users` | id | NO ACTION |  |
| `review_evidence_snapshots` | evidence_ref_id | `evidence_refs` | id | RESTRICT |  |
| `review_evidence_snapshots` | project_id | `projects` | id | RESTRICT |  |
| `review_evidence_snapshots` | actor_service_identity_id | `service_identities` | id | RESTRICT |  |
| `review_evidence_snapshots` | actor_user_id | `users` | id | RESTRICT |  |
| `review_messages` | conversation_id | `review_conversations` | id | NO ACTION |  |
| `review_messages` | sender_id | `users` | id | NO ACTION |  |
| `review_messages` | target_user_id | `users` | id | NO ACTION |  |
| `review_records` | conversation_id | `review_conversations` | id | NO ACTION |  |
| `review_records` | commenter_id | `users` | id | NO ACTION |  |
| `review_records` | replier_id | `users` | id | NO ACTION |  |
| `review_records` | resolved_by | `users` | id | NO ACTION |  |
| `review_records` | working_paper_id | `working_paper` | id | NO ACTION |  |
| `review_templates` | created_by | `users` | id | NO ACTION |  |
| `review_threads` | project_id | `projects` | id | NO ACTION |  |
| `review_threads` | created_by | `users` | id | NO ACTION |  |
| `review_threads` | wp_id | `working_paper` | id | NO ACTION |  |
| `risk_assessments` | project_id | `projects` | id | NO ACTION |  |
| `risk_assessments` | created_by | `users` | id | NO ACTION |  |
| `risk_matrix_records` | project_id | `projects` | id | NO ACTION |  |
| `sampled_vouchers` | project_id | `projects` | id | NO ACTION |  |
| `sampled_vouchers` | sampled_by | `users` | id | NO ACTION |  |
| `sampling_config` | project_id | `projects` | id | NO ACTION |  |
| `sampling_config` | created_by | `users` | id | NO ACTION |  |
| `sampling_records` | project_id | `projects` | id | NO ACTION |  |
| `sampling_records` | sampling_config_id | `sampling_config` | id | NO ACTION |  |
| `sampling_records` | created_by | `users` | id | NO ACTION |  |
| `sampling_records` | working_paper_id | `working_paper` | id | NO ACTION |  |
| `se_checklist` | project_id | `projects` | id | NO ACTION |  |
| `se_checklist` | completed_by | `users` | id | NO ACTION |  |
| `share_change_event` | project_id | `projects` | id | CASCADE |  |
| `shared_config_templates` | owner_project_id | `projects` | id | NO ACTION |  |
| `shared_config_templates` | owner_user_id | `users` | id | NO ACTION |  |
| `signature_records` | signer_id | `users` | id | NO ACTION |  |
| `staff_members` | partner_id | `staff_members` | id | NO ACTION |  |
| `staff_members` | user_id | `users` | id | NO ACTION |  |
| `subsequent_events` | project_id | `projects` | id | NO ACTION |  |
| `subsequent_events` | created_by | `users` | id | NO ACTION |  |
| `sync_logs` | project_id | `projects` | id | NO ACTION |  |
| `sync_logs` | user_id | `users` | id | NO ACTION |  |
| `sys_dept` | parent_id | `sys_dept` | id | SET NULL |  |
| `sys_dept` | head_id | `users` | id | SET NULL |  |
| `sys_role_project` | project_id | `projects` | id | CASCADE |  |
| `sys_role_project` | role_id | `sys_role` | id | CASCADE |  |
| `sys_user_role` | role_id | `sys_role` | id | CASCADE |  |
| `sys_user_role` | user_id | `users` | id | CASCADE |  |
| `t_account_entries` | t_account_id | `t_accounts` | id | NO ACTION |  |
| `t_accounts` | project_id | `projects` | id | NO ACTION |  |
| `t_accounts` | created_by | `users` | id | NO ACTION |  |
| `tb_aux_balance` | import_batch_id | `import_batches` | id | NO ACTION |  |
| `tb_aux_balance` | project_id | `projects` | id | NO ACTION |  |
| `tb_aux_ledger` | import_batch_id | `import_batches` | id | NO ACTION |  |
| `tb_aux_ledger` | project_id | `projects` | id | NO ACTION |  |
| `tb_balance` | import_batch_id | `import_batches` | id | NO ACTION |  |
| `tb_balance` | project_id | `projects` | id | NO ACTION |  |
| `tb_change_history` | project_id | `projects` | id | NO ACTION |  |
| `tb_change_history` | operator_id | `users` | id | NO ACTION |  |
| `tb_ledger` | import_batch_id | `import_batches` | id | NO ACTION |  |
| `tb_ledger` | project_id | `projects` | id | NO ACTION |  |
| `template_library` | project_id | `projects` | id | NO ACTION |  |
| `template_library` | source_template_id | `template_library` | id | NO ACTION |  |
| `template_library` | created_by | `users` | id | NO ACTION |  |
| `time_machine_snapshots` | project_id | `projects` | id | NO ACTION |  |
| `time_machine_snapshots` | parent_snapshot_id | `time_machine_snapshots` | id | NO ACTION |  |
| `time_machine_snapshots` | user_id | `users` | id | NO ACTION |  |
| `trial_balance` | project_id | `projects` | id | NO ACTION |  |
| `trial_balance_snapshots` | project_id | `projects` | id | NO ACTION |  |
| `unadjusted_misstatements` | source_adjustment_id | `adjustments` | id | NO ACTION |  |
| `unadjusted_misstatements` | bound_dataset_id | `ledger_datasets` | id | RESTRICT |  |
| `unadjusted_misstatements` | project_id | `projects` | id | NO ACTION |  |
| `unadjusted_misstatements` | prior_year_id | `unadjusted_misstatements` | id | NO ACTION |  |
| `unadjusted_misstatements` | created_by | `users` | id | NO ACTION |  |
| `user_display_preferences` | user_id | `users` | id | CASCADE |  |
| `users` | created_by | `users` | id | NO ACTION |  |
| `users` | parent_partner_id | `users` | id | SET NULL |  |
| `users` | updated_by | `users` | id | NO ACTION |  |
| `word_export_task` | project_id | `projects` | id | NO ACTION |  |
| `word_export_task` | approval_by | `users` | id | NO ACTION |  |
| `word_export_task` | confirmed_by | `users` | id | NO ACTION |  |
| `word_export_task` | created_by | `users` | id | NO ACTION |  |
| `word_export_task` | signed_by | `users` | id | NO ACTION |  |
| `word_export_task_versions` | created_by | `users` | id | NO ACTION |  |
| `word_export_task_versions` | edited_by | `users` | id | NO ACTION |  |
| `word_export_task_versions` | word_export_task_id | `word_export_task` | id | NO ACTION |  |
| `work_hour_entries` | project_id | `projects` | id | NO ACTION |  |
| `work_hour_entries` | approved_by | `users` | id | NO ACTION |  |
| `work_hour_entries` | user_id | `users` | id | NO ACTION |  |
| `work_hours` | project_id | `projects` | id | NO ACTION |  |
| `work_hours` | staff_id | `staff_members` | id | NO ACTION |  |
| `work_hours` | approved_by | `users` | id | NO ACTION |  |
| `working_paper` | bound_dataset_id | `ledger_datasets` | id | RESTRICT |  |
| `working_paper` | project_id | `projects` | id | NO ACTION |  |
| `working_paper` | assigned_to | `users` | id | NO ACTION |  |
| `working_paper` | created_by | `users` | id | NO ACTION |  |
| `working_paper` | partner_reviewed_by | `users` | id | NO ACTION |  |
| `working_paper` | rejected_by | `users` | id | NO ACTION |  |
| `working_paper` | reviewer | `users` | id | NO ACTION |  |
| `working_paper` | updated_by | `users` | id | NO ACTION |  |
| `working_paper` | current_content_version_id | `working_paper_content_version` | id | RESTRICT | 仅数据库有，ORM 未声明 |
| `working_paper` | wp_index_id | `wp_index` | id | NO ACTION |  |
| `working_paper_artifact` | project_id | `projects` | id | NO ACTION |  |
| `working_paper_artifact` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_artifact` | source_delivery_id | `working_paper_callback_delivery` | id | NO ACTION |  |
| `working_paper_artifact` | source_delivery_id | `working_paper_callback_delivery` | id | RESTRICT |  |
| `working_paper_artifact` | created_by_operation_id | `working_paper_sync_operation` | id | NO ACTION |  |
| `working_paper_artifact` | created_by_operation_id | `working_paper_sync_operation` | id | RESTRICT |  |
| `working_paper_callback_delivery` | project_id | `projects` | id | NO ACTION |  |
| `working_paper_callback_delivery` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_callback_delivery` | incoming_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_callback_delivery` | callback_recovery_case_id | `working_paper_callback_recovery_case` | id | NO ACTION |  |
| `working_paper_callback_delivery` | application_id | `working_paper_content_application` | id | NO ACTION |  |
| `working_paper_callback_delivery` | forcesave_request_id | `working_paper_forcesave_request` | id | NO ACTION |  |
| `working_paper_callback_delivery` | room_id | `working_paper_oo_room` | id | NO ACTION |  |
| `working_paper_callback_delivery` | operation_id | `working_paper_sync_operation` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | project_id | `projects` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | incoming_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | application_id | `working_paper_content_application` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | application_id | `working_paper_content_application` | id | RESTRICT |  |
| `working_paper_callback_recovery_case` | recovery_request_id | `working_paper_forcesave_request` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | prior_confirmation_id | `working_paper_oo_client_confirmation` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | claimed_by_participant_id | `working_paper_oo_participant` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | room_id | `working_paper_oo_room` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | claimed_definition_bundle_id | `working_paper_sync_definition_bundle` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | operation_id | `working_paper_sync_operation` | id | NO ACTION |  |
| `working_paper_callback_recovery_case` | operation_id | `working_paper_sync_operation` | id | RESTRICT |  |
| `working_paper_callback_recovery_case_event` | case_id | `working_paper_callback_recovery_case` | id | NO ACTION |  |
| `working_paper_callback_recovery_case_event` | prior_confirmation_id | `working_paper_oo_client_confirmation` | id | NO ACTION |  |
| `working_paper_content_application` | project_id | `projects` | id | NO ACTION |  |
| `working_paper_content_application` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_content_application` | incoming_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_content_application` | superseded_by_application_id | `working_paper_content_application` | id | NO ACTION |  |
| `working_paper_content_application` | base_representation_id | `working_paper_content_representation` | id | NO ACTION |  |
| `working_paper_content_application` | result_representation_id | `working_paper_content_representation` | id | NO ACTION |  |
| `working_paper_content_application` | base_version_id | `working_paper_content_version` | id | NO ACTION |  |
| `working_paper_content_application` | origin_request_id | `working_paper_forcesave_request` | id | NO ACTION |  |
| `working_paper_content_application` | room_id | `working_paper_oo_room` | id | NO ACTION |  |
| `working_paper_content_application` | authority_model_definition_id | `working_paper_sync_definition_artifact` | id | NO ACTION |  |
| `working_paper_content_application` | definition_bundle_id | `working_paper_sync_definition_bundle` | id | NO ACTION |  |
| `working_paper_content_application_event` | application_id | `working_paper_content_application` | id | NO ACTION |  |
| `working_paper_content_application_event` | folded_request_id | `working_paper_forcesave_request` | id | NO ACTION |  |
| `working_paper_content_representation` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_content_representation` | artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_content_representation` | parent_representation_id | `working_paper_content_representation` | id | NO ACTION |  |
| `working_paper_content_representation` | content_version_id | `working_paper_content_version` | id | NO ACTION |  |
| `working_paper_content_representation` | authority_model_definition_id | `working_paper_sync_definition_artifact` | id | NO ACTION |  |
| `working_paper_content_representation` | definition_bundle_id | `working_paper_sync_definition_bundle` | id | NO ACTION |  |
| `working_paper_content_revision_backfill_ledger` | project_id | `projects` | id | NO ACTION |  |
| `working_paper_content_revision_backfill_ledger` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_content_version` | actor_id | `users` | id | NO ACTION |  |
| `working_paper_content_version` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_content_version` | authoritative_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_content_version` | projection_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_content_version` | parent_version_id | `working_paper_content_version` | id | NO ACTION |  |
| `working_paper_content_version` | operation_id | `working_paper_sync_operation` | id | NO ACTION |  |
| `working_paper_content_version` | operation_id | `working_paper_sync_operation` | id | RESTRICT |  |
| `working_paper_entry_evidence_scenario` | trace_bundle_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_entry_evidence_scenario` | run_id | `working_paper_sync_test_run` | id | NO ACTION |  |
| `working_paper_forcesave_request` | client_base_representation_id | `working_paper_content_representation` | id | NO ACTION |  |
| `working_paper_forcesave_request` | client_base_version_id | `working_paper_content_version` | id | NO ACTION |  |
| `working_paper_forcesave_request` | initiated_by_participant_id | `working_paper_oo_participant` | id | NO ACTION |  |
| `working_paper_forcesave_request` | room_id | `working_paper_oo_room` | id | NO ACTION |  |
| `working_paper_forcesave_request` | authority_model_definition_id | `working_paper_sync_definition_artifact` | id | NO ACTION |  |
| `working_paper_forcesave_request` | definition_bundle_id | `working_paper_sync_definition_bundle` | id | NO ACTION |  |
| `working_paper_oo_client_confirmation` | representation_id | `working_paper_content_representation` | id | NO ACTION |  |
| `working_paper_oo_client_confirmation` | content_version_id | `working_paper_content_version` | id | NO ACTION |  |
| `working_paper_oo_client_confirmation` | participant_id | `working_paper_oo_participant` | id | NO ACTION |  |
| `working_paper_oo_client_confirmation` | room_id | `working_paper_oo_room` | id | NO ACTION |  |
| `working_paper_oo_client_confirmation` | definition_bundle_id | `working_paper_sync_definition_bundle` | id | NO ACTION |  |
| `working_paper_oo_close_intent` | ordinary_forcesave_request_id | `working_paper_forcesave_request` | id | NO ACTION |  |
| `working_paper_oo_close_intent` | promoted_request_id | `working_paper_forcesave_request` | id | NO ACTION |  |
| `working_paper_oo_close_intent` | client_confirmation_id | `working_paper_oo_client_confirmation` | id | NO ACTION |  |
| `working_paper_oo_close_intent` | participant_id | `working_paper_oo_participant` | id | NO ACTION |  |
| `working_paper_oo_close_intent` | room_id | `working_paper_oo_room` | id | NO ACTION |  |
| `working_paper_oo_close_intent_event` | intent_id | `working_paper_oo_close_intent` | id | NO ACTION |  |
| `working_paper_oo_participant` | user_id | `users` | id | NO ACTION |  |
| `working_paper_oo_participant` | room_id | `working_paper_oo_room` | id | NO ACTION |  |
| `working_paper_oo_room` | project_id | `projects` | id | NO ACTION |  |
| `working_paper_oo_room` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_oo_room` | latest_durable_application_id | `working_paper_content_application` | id | NO ACTION |  |
| `working_paper_oo_room` | latest_durable_application_id | `working_paper_content_application` | id | RESTRICT |  |
| `working_paper_oo_room` | client_confirmed_representation_id | `working_paper_content_representation` | id | NO ACTION |  |
| `working_paper_oo_room` | client_confirmed_base_version_id | `working_paper_content_version` | id | NO ACTION |  |
| `working_paper_oo_room` | last_applied_version_id | `working_paper_content_version` | id | NO ACTION |  |
| `working_paper_oo_room` | opened_base_version_id | `working_paper_content_version` | id | NO ACTION |  |
| `working_paper_oo_room` | close_leader_intent_id | `working_paper_oo_close_intent` | id | NO ACTION |  |
| `working_paper_oo_room` | close_leader_intent_id | `working_paper_oo_close_intent` | id | RESTRICT |  |
| `working_paper_oo_room` | client_confirmed_definition_bundle_id | `working_paper_sync_definition_bundle` | id | NO ACTION |  |
| `working_paper_pending_mutation` | project_id | `projects` | id | NO ACTION |  |
| `working_paper_pending_mutation` | user_id | `users` | id | NO ACTION |  |
| `working_paper_pending_mutation` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_pending_mutation` | payload_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_pending_mutation` | result_content_version_id | `working_paper_content_version` | id | NO ACTION |  |
| `working_paper_pending_mutation` | result_operation_id | `working_paper_sync_operation` | id | NO ACTION |  |
| `working_paper_pending_mutation` | result_operation_id | `working_paper_sync_operation` | id | RESTRICT |  |
| `working_paper_representation_candidate_event` | actor_id | `users` | id | NO ACTION |  |
| `working_paper_representation_candidate_event` | candidate_id | `working_paper_representation_upgrade_candidate` | id | NO ACTION |  |
| `working_paper_representation_candidate_event` | contract_definition_id | `working_paper_sync_definition_artifact` | id | NO ACTION |  |
| `working_paper_representation_candidate_event` | definition_bundle_id | `working_paper_sync_definition_bundle` | id | NO ACTION |  |
| `working_paper_representation_upgrade_candidate` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_representation_upgrade_candidate` | staged_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_representation_upgrade_candidate` | finalized_representation_id | `working_paper_content_representation` | id | NO ACTION |  |
| `working_paper_representation_upgrade_candidate` | source_representation_id | `working_paper_content_representation` | id | NO ACTION |  |
| `working_paper_representation_upgrade_candidate` | content_version_id | `working_paper_content_version` | id | NO ACTION |  |
| `working_paper_representation_upgrade_candidate` | instrumentation_definition_id | `working_paper_sync_definition_artifact` | id | NO ACTION |  |
| `working_paper_representation_upgrade_candidate` | target_contract_definition_id | `working_paper_sync_definition_artifact` | id | NO ACTION |  |
| `working_paper_representation_upgrade_candidate` | template_definition_id | `working_paper_sync_definition_artifact` | id | NO ACTION |  |
| `working_paper_representation_upgrade_candidate` | target_definition_bundle_id | `working_paper_sync_definition_bundle` | id | NO ACTION |  |
| `working_paper_sync_conflict` | resolved_by | `users` | id | NO ACTION |  |
| `working_paper_sync_conflict` | canonical_application_id | `working_paper_content_application` | id | NO ACTION |  |
| `working_paper_sync_conflict` | operation_id | `working_paper_sync_operation` | id | NO ACTION |  |
| `working_paper_sync_definition_artifact` | blob_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_sync_definition_artifact` | supersedes_id | `working_paper_sync_definition_artifact` | id | NO ACTION |  |
| `working_paper_sync_definition_bundle` | canonical_payload_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `working_paper_sync_definition_bundle` | authority_model_definition_id | `working_paper_sync_definition_artifact` | id | NO ACTION |  |
| `working_paper_sync_entry_state` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_sync_entry_state` | current_representation_id | `working_paper_content_representation` | id | NO ACTION |  |
| `working_paper_sync_operation` | project_id | `projects` | id | NO ACTION |  |
| `working_paper_sync_operation` | created_by | `users` | id | NO ACTION |  |
| `working_paper_sync_operation` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_sync_operation` | application_id | `working_paper_content_application` | id | NO ACTION |  |
| `working_paper_sync_operation` | forcesave_request_id | `working_paper_forcesave_request` | id | NO ACTION |  |
| `working_paper_sync_operation` | initiated_by_participant_id | `working_paper_oo_participant` | id | NO ACTION |  |
| `working_paper_sync_operation` | room_id | `working_paper_oo_room` | id | NO ACTION |  |
| `working_paper_sync_operation` | authority_model_definition_id | `working_paper_sync_definition_artifact` | id | NO ACTION |  |
| `working_paper_sync_operation` | definition_bundle_id | `working_paper_sync_definition_bundle` | id | NO ACTION |  |
| `working_paper_sync_operation` | duplicate_of_operation_id | `working_paper_sync_operation` | id | NO ACTION |  |
| `working_paper_sync_operation_contributor` | user_id | `users` | id | NO ACTION |  |
| `working_paper_sync_operation_contributor` | participant_id | `working_paper_oo_participant` | id | NO ACTION |  |
| `working_paper_sync_operation_contributor` | operation_id | `working_paper_sync_operation` | id | NO ACTION |  |
| `working_paper_sync_operation_event` | operation_id | `working_paper_sync_operation` | id | NO ACTION |  |
| `working_paper_sync_scope_index` | project_id | `projects` | id | NO ACTION |  |
| `working_paper_sync_scope_index` | wp_id | `working_paper` | id | NO ACTION |  |
| `working_paper_sync_test_run` | run_manifest_artifact_id | `working_paper_artifact` | id | NO ACTION |  |
| `workpaper_delegation_history` | task_id | `procedure_row_tasks` | id | NO ACTION |  |
| `workpaper_delegation_history` | project_id | `projects` | id | NO ACTION |  |
| `workpaper_delegation_history` | new_staff_id | `staff_members` | id | NO ACTION |  |
| `workpaper_delegation_history` | old_staff_id | `staff_members` | id | NO ACTION |  |
| `workpaper_delegation_history` | actor_user_id | `users` | id | NO ACTION |  |
| `workpaper_delegation_history` | new_user_id | `users` | id | NO ACTION |  |
| `workpaper_delegation_history` | old_user_id | `users` | id | NO ACTION |  |
| `workpaper_delegation_history` | wp_id | `working_paper` | id | NO ACTION |  |
| `workpaper_delegation_history` | wp_index_id | `wp_index` | id | NO ACTION |  |
| `workpaper_extraction_log` | project_id | `projects` | id | NO ACTION |  |
| `workpaper_extraction_log` | user_id | `users` | id | NO ACTION | 仅数据库有，ORM 未声明 |
| `workpaper_extraction_log` | workpaper_id | `working_paper` | id | NO ACTION |  |
| `workpaper_field_overrides` | updated_by | `users` | id | NO ACTION |  |
| `workpaper_generation_items` | operation_id | `workpaper_generation_operations` | id | CASCADE |  |
| `workpaper_generation_operations` | project_id | `projects` | id | CASCADE |  |
| `workpaper_generation_operations` | actor_user_id | `users` | id | RESTRICT |  |
| `workpaper_generation_operations` | template_set_id | `wp_template_set` | id | SET NULL |  |
| `workpaper_lifecycle_events` | project_id | `projects` | id | NO ACTION |  |
| `workpaper_procedures` | project_id | `projects` | id | NO ACTION |  |
| `workpaper_procedures` | wp_id | `working_paper` | id | NO ACTION |  |
| `workpaper_review_records` | project_id | `projects` | id | NO ACTION |  |
| `workpaper_review_records` | reviewer_id | `users` | id | NO ACTION |  |
| `workpaper_row_name_mapping` | confirmed_by | `users` | id | NO ACTION |  |
| `workpaper_row_name_mapping` | superseded_from | `workpaper_row_name_mapping` | id | NO ACTION |  |
| `workpaper_row_name_mapping_target` | mapping_id | `workpaper_row_name_mapping` | id | CASCADE |  |
| `workpaper_sheet_classification` | template_version_id | `workpaper_template_version` | id | NO ACTION |  |
| `workpaper_snapshots` | project_id | `projects` | id | NO ACTION |  |
| `workpaper_snapshots` | workpaper_id | `working_paper` | id | NO ACTION |  |
| `workpaper_template_override_version` | project_id | `projects` | id | RESTRICT | 仅数据库有，ORM 未声明 |
| `workpaper_template_override_version` | created_by | `users` | id | SET NULL | 仅数据库有，ORM 未声明 |
| `workpaper_template_override_version` | parent_version_id | `workpaper_template_override_version` | id | RESTRICT | 仅数据库有，ORM 未声明 |
| `workpaper_template_version` | parent_version_id | `workpaper_template_version` | id | SET NULL |  |
| `wp_access_security_outbox` | project_id | `projects` | id | NO ACTION |  |
| `wp_access_security_outbox` | actor_user_id | `users` | id | NO ACTION |  |
| `wp_access_security_outbox` | wp_id | `working_paper` | id | NO ACTION |  |
| `wp_access_security_outbox` | wp_index_id | `wp_index` | id | NO ACTION |  |
| `wp_ai_generations` | confirmed_by | `users` | id | NO ACTION |  |
| `wp_ai_generations` | created_by | `users` | id | NO ACTION |  |
| `wp_ai_generations` | wp_id | `working_paper` | id | NO ACTION |  |
| `wp_cross_ref` | project_id | `projects` | id | NO ACTION |  |
| `wp_cross_ref` | source_wp_id | `working_paper` | id | NO ACTION |  |
| `wp_edit_sessions` | user_id | `users` | id | NO ACTION |  |
| `wp_edit_sessions` | wp_id | `working_paper` | id | NO ACTION |  |
| `wp_export_snapshot` | project_id | `projects` | id | CASCADE |  |
| `wp_export_snapshot` | exported_by | `users` | id | NO ACTION |  |
| `wp_export_snapshot` | working_paper_id | `working_paper` | id | CASCADE |  |
| `wp_formula` | project_id | `projects` | id | NO ACTION |  |
| `wp_formula` | created_by | `users` | id | NO ACTION |  |
| `wp_formula` | wp_id | `working_paper` | id | NO ACTION |  |
| `wp_index` | project_id | `projects` | id | NO ACTION |  |
| `wp_index` | assigned_to | `users` | id | NO ACTION |  |
| `wp_index` | reviewer | `users` | id | NO ACTION |  |
| `wp_qc_results` | checked_by | `users` | id | NO ACTION |  |
| `wp_qc_results` | working_paper_id | `working_paper` | id | NO ACTION |  |
| `wp_recommendation_feedback` | project_id | `projects` | id | NO ACTION |  |
| `wp_recommendation_feedback` | action_by | `users` | id | NO ACTION |  |
| `wp_template` | created_by | `users` | id | NO ACTION |  |
| `wp_template_custom` | user_id | `users` | id | NO ACTION |  |
| `wp_template_meta` | template_id | `wp_template` | id | NO ACTION |  |
| `wp_template_metadata` | template_id | `wp_template` | id | NO ACTION |  |
| `wp_version_archive` | project_id | `projects` | id | CASCADE |  |
| `wp_version_archive` | created_by | `users` | id | NO ACTION |  |
| `wp_version_archive` | working_paper_id | `working_paper` | id | CASCADE |  |
| `wp_visibility_invalidation_outbox` | project_id | `projects` | id | NO ACTION |  |
| `wp_visibility_invalidation_outbox` | actor_user_id | `users` | id | NO ACTION |  |
| `wp_visibility_policy_epoch` | project_id | `projects` | id | NO ACTION |  |

## 2. 无外键约束的引用列

列名以 `_id` 结尾、按名称能对应到平台表，但数据库和 ORM 都没有外键。完整性由服务层保证。

### 指向 `projects`（33 列）

`account_note_mapping.project_id`、`acnr_invalidation_outbox.project_id`、`advanced_query_writeback.project_id`、`attachment_lineage.project_id`、`audit_check_signoff.project_id`、`cf_verification_results.project_id`、`chain_executions.project_id`、`confirmation_action_log.project_id`、`consistency_gate_acknowledgements.project_id`、`consol_cell_comments.project_id`、`consol_note_data.project_id`、`consol_worksheet_data.project_id`、`deliverable_section_state.project_id`、`draft_marker.project_id`、`draft_refresh_audit.project_id`、`event_cascade_log.project_id`、`gate_decisions.project_id`、`guidance_handoff_visibility.project_id`、`independence_signing_tasks.project_id`、`issue_tickets.project_id`、`knowledge_index.project_id`、`offline_conflicts.project_id`、`project_quality_ratings.project_id`、`project_workbook_instance.project_id`、`review_checklist_records.project_id`、`task_events.project_id`、`task_tree_nodes.project_id`、`tb_publish_ack.project_id`、`temporary_grants.project_id`、`trace_events.project_id`、`version_line_stamps.project_id`、`workpaper_field_overrides.project_id`、`workpaper_row_name_mapping.project_id`

### 指向 `users`（26 列）

`audit_log_entries.user_id`、`confirmation_attachment_link.created_by`、`consol_cell_comments.created_by`、`consol_note_formula.updated_by`、`consol_worksheet_data.created_by`、`deliverable_snapshots.created_by`、`enum_dict_overrides.updated_by`、`evidence_links.created_by`、`export_job_attempts.created_by`、`formula_push_state.updated_by`、`formula_setting.created_by`、`formula_setting.updated_by`、`formula_template.created_by`、`formula_template.updated_by`、`gate_rule_configs.updated_by`、`independence_signing_tasks.user_id`、`qc_inspection_records.created_by`、`qc_inspections.reviewer_id`、`qc_rule_definitions.created_by`、`report_config.updated_by`、`review_checklist_records.reviewer_id`、`reviewer_metrics_snapshots.reviewer_id`、`share_change_event.created_by`、`task_tree_nodes.assignee_id`、`time_machine_snapshots.created_by`、`workpaper_snapshots.user_id`

### 指向 `working_paper`（15 列）

`acnr_invalidation_outbox.wp_id`、`advanced_query_writeback.wp_id`、`ai_content_governance.wp_id`、`ai_content_log.wp_id`、`attachment_working_paper.working_paper_id`、`gate_decisions.wp_id`、`interim_survival_checks.working_paper_id`、`issue_tickets.wp_id`、`offline_conflicts.wp_id`、`pbc_checklist.wp_id`、`procedure_instances.wp_id`、`project_workbook_instance.wp_id`、`qc_inspection_items.wp_id`、`sampled_vouchers.working_paper_id`、`workpaper_generation_items.wp_id`

### 指向 `ledger_datasets`（10 列）

`account_chart.dataset_id`、`direction_override.dataset_id`、`interim_survival_checks.dataset_id`、`sampling_records.dataset_id`、`tb_aux_balance.dataset_id`、`tb_aux_ledger.dataset_id`、`tb_balance.dataset_id`、`tb_ledger.dataset_id`、`workpaper_row_name_mapping_target.dataset_id`、`workpaper_snapshots.bound_dataset_id`

### 指向 `attachments`（3 列）

`attachment_lineage.attachment_id`、`confirmation_action_log.attachment_id`、`ocr_jobs.attachment_id`

### 指向 `wp_index`（2 列）

`workpaper_generation_items.wp_index_id`、`workpaper_lifecycle_events.wp_index_id`

### 分录组业务键 `entry_group_id`（10 列）

`adjustment_client_bookings.entry_group_id`、`adjustment_collaboration.entry_group_id`、`adjustment_editing_locks.entry_group_id`、`adjustment_entries.entry_group_id`、`adjustment_import_group_results.entry_group_id`、`adjustment_review_tasks.entry_group_id`、`adjustment_treatment_events.entry_group_id`、`adjustments.entry_group_id`、`cfs_adjustments.entry_group_id`、`elimination_entries.entry_group_id`

### 无法按名称对应到单一表的 `_id` 列（216 列）

多为多态引用（配 `*_type` / `object_type` 列）、外部系统 id、追踪 id 或业务键，需看所在服务的写法。

`account_note_mapping.section_id`、`account_package_program_status.account_package_id`、`advanced_query_writeback.addr_id`、`advanced_query_writeback.operator_id`、`ai_chat_action_receipts.result_resource_id`、`ai_chat_history.conversation_id`、`ai_chat_run_resources.resource_id`、`ai_chat_runs.host_id`、`ai_chat_runs.request_id`、`ai_chat_session.host_id`、`ai_chat_tool_calls.tool_call_id`、`ai_content.workpaper_id`、`ai_content_log.generation_id`、`ai_evidence_chains.source_id`、`ai_evidence_items.document_id`、`ai_plugins.plugin_id`、`ai_task_items.generation_id`、`ai_task_items.target_id`、`annual_independence_declarations.reviewed_by_qc_id`、`archive_jobs.gate_eval_id`、`archive_manifest_edges.source_id`、`archive_manifest_edges.target_id`、`archive_manifest_entries.node_id`、`attachment_lineage.target_id`、`attachments.paperless_document_id`、`attachments.previous_version_id`、`attachments.reference_id`、`audit_chain_head.tail_entry_id`、`audit_log_entries.object_id`、`audit_log_entries.session_id`、`audit_log_entries.trace_id`、`audit_procedures.related_risk_id`、`cell_annotations.conversation_id`、`cell_annotations.linked_annotation_id`、`cell_annotations.object_id`、`confirmation_action_log.actor_user_id`、`confirmation_attachment_link.paired_outbound_attachment_id`、`consistency_gate_acknowledgements.branch_id`、`consol_note_data.last_formula_run_id`、`consol_note_data.section_id`、`consol_note_data.source_operation_id`、`consol_note_detail_template.section_id`、`consol_note_formula.section_id`、`consol_note_mapping_binding.entity_project_id`、`consol_note_mapping_binding.section_id`、`consol_note_mapping_rule.section_id`、`consol_note_template_binding.section_id`、`consol_note_template_push_log.consol_project_id`、`consol_note_template_push_log.section_id`、`consol_note_template_push_log.template_version_id`、`cross_check_results.rule_id`、`cross_module_conflicts.source_id`、`cross_module_conflicts.target_id`、`direction_override.record_id`、`disclosure_notes.parent_section_id`、`disclosure_notes.section_id`、`disclosure_notes.source_project_id`、`draft_marker.refresh_id`、`draft_refresh_audit.operator_id`、`draft_refresh_snapshot.editor_id`、`draft_refresh_snapshot.source_formula_id`、`editing_locks.resource_id`、`elimination_entries.prior_year_entry_id`、`evidence_audit_command_roots.trace_id`、`evidence_chain.source_document_id`、`evidence_chain.target_document_id`、`evidence_dependencies.acnr_addr_id`、`evidence_dependencies.source_id`、`evidence_dependencies.target_id`、`evidence_hash_checks.export_id`、`evidence_inbox.event_id`、`evidence_outbox.event_id`、`evidence_refs.evidence_id`、`evidence_refs.source_id`、`evidence_tombstones.legal_hold_release_id`、`evidence_tombstones.original_object_id`、`export_job_attempts.snapshot_id`、`export_job_attempts.version_id`、`export_job_items_v2.last_attempt_id`、`export_job_items_v2.snapshot_id`、`export_job_items_v2.version_id`、`export_jobs_v2.snapshot_id`、`formula_publish.request_id`、`formula_publish.source_project_id`、`formula_push_state.addr_id`、`formula_push_state.rule_id`、`formula_setting.base_template_id`、`formula_sync_item.publish_id`、`formula_sync_item.upstream_template_id`、`gate_decisions.actor_id`、`gate_decisions.trace_id`、`gate_rule_configs.tenant_id`、`guidance_consumer_ack.ack_id`、`guidance_consumer_ack.handoff_id`、`guidance_exemption_record.approver_user_id`、`guidance_exemption_record.entry_id`、`guidance_exemption_record.owner_user_id`、`guidance_handoff_visibility.decisive_ack_id`、`guidance_handoff_visibility.entry_id`、`guidance_handoff_visibility.handoff_id`、`guidance_handoff_visibility.organization_id`、`guidance_publication.author_user_id`、`guidance_publication.lineage_id`、`guidance_publication.reviewer_user_id`、`guidance_publication_event.actor_user_id`、`guidance_publication_event.reviewer_user_id`、`import_event_consumptions.event_id`、`issue_tickets.conversation_id`、`issue_tickets.entity_id`、`issue_tickets.owner_id`、`issue_tickets.source_ref_id`、`issue_tickets.task_node_id`、`issue_tickets.thread_id`、`issue_tickets.trace_id`、`knowledge_documents.previous_version_id`、`knowledge_index.source_id`、`ledger_datasets.tenant_id`、`legal_hold_scopes.node_id`、`logs.object_id`、`management_letters.prior_year_item_id`、`note_section_version_tree.note_section_id`、`note_text_batch_applications.mutation_id`、`notifications.event_id`、`notifications.related_object_id`、`ocr_writeback_staging.target_id`、`ocr_writebacks.target_id`、`offline_conflicts.procedure_id`、`offline_conflicts.qc_replay_job_id`、`offline_conflicts.resolver_id`、`offline_conflicts.trace_id`、`platform_job_attempts.worker_id`、`procedure_operation_previews.consumed_request_id`、`procedure_row_task_history.request_id`、`procedure_trim_cycle_confirmations.request_id`、`project_guidance_supplement.author_user_id`、`project_guidance_supplement.entry_id`、`project_guidance_supplement.reviewer_user_id`、`project_workbook_instance.current_artifact_id`、`project_workbook_instance.onlyoffice_room_id`、`project_workbook_instance.organization_id`、`project_workbook_instance.pinned_template_version_id`、`project_workbook_instance.workbook_instance_id`、`project_workbook_instance.workbook_lineage_id`、`project_workbook_sheet_entry.entry_id`、`projects.prior_year_project_id`、`report_config.base_template_id`、`report_config_baseline.source_project_id`、`review_closes.review_id`、`review_conversations.related_object_id`、`review_conversations.trace_id`、`review_evidence_snapshots.review_id`、`review_messages.finding_id`、`review_messages.thread_id`、`review_messages.trace_id`、`review_threads.section_id`、`sampled_vouchers.batch_id`、`sampling_records.batch_id`、`share_change_event.source_row_id`、`signature_records.object_id`、`t_account_entries.reference_id`、`task_events.aggregate_id`、`task_events.delegation_batch_id`、`task_events.task_node_id`、`task_events.trace_id`、`task_tree_nodes.parent_id`、`task_tree_nodes.ref_id`、`tb_aux_balance.tenant_id`、`tb_aux_ledger.tenant_id`、`tb_balance.tenant_id`、`tb_change_history.source_adjustment_id`、`tb_ledger.tenant_id`、`template_library.group_id`、`time_machine_snapshots.instance_id`、`trace_events.actor_id`、`trace_events.object_id`、`trace_events.trace_id`、`trial_balance_snapshots.actor_id`、`users.dept_id`、`version_line_stamps.object_id`、`version_line_stamps.source_snapshot_id`、`version_line_stamps.trace_id`、`word_export_task.snapshot_id`、`word_export_task_versions.hash_chain_entry_id`、`word_export_task_versions.snapshot_id`、`working_paper_callback_delivery.entry_id`、`working_paper_callback_delivery.route_credential_id`、`working_paper_callback_recovery_case.entry_id`、`working_paper_callback_recovery_case_event.actor_id`、`working_paper_content_application.adapter_id`、`working_paper_content_application.entry_id`、`working_paper_content_application_event.actor_id`、`working_paper_content_representation.adapter_id`、`working_paper_content_representation.entry_id`、`working_paper_entry_evidence_scenario.scenario_id`、`working_paper_oo_close_intent_event.actor_id`、`working_paper_oo_room.entry_id`、`working_paper_pending_mutation.entry_id`、`working_paper_representation_candidate_event.correlation_id`、`working_paper_representation_upgrade_candidate.entry_id`、`working_paper_sync_definition_artifact.logical_id`、`working_paper_sync_operation.entry_id`、`working_paper_sync_operation_event.actor_id`、`working_paper_sync_operation_event.correlation_id`、`working_paper_sync_scope_index.entry_id`、`working_paper_sync_scope_index.room_id`、`working_paper_sync_test_run.entry_id`、`workpaper_delegation_history.request_id`、`workpaper_extraction_log.batch_id`、`workpaper_lifecycle_events.actor_user_id`、`workpaper_lifecycle_events.request_id`、`workpaper_procedures.procedure_id`、`workpaper_review_records.workpaper_id`、`wp_access_security_outbox.request_id`、`wp_formula.base_template_id`、`wp_formula.reference_formula_id`、`wp_visibility_invalidation_outbox.request_id`

