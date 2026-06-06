-- R059: 回滚 deliverable-center 扩展列

DROP INDEX IF EXISTS idx_wetv_file_hash;
DROP INDEX IF EXISTS idx_wet_doc_subtype;

ALTER TABLE audit_report DROP COLUMN IF EXISTS prior_period_info;
ALTER TABLE audit_report DROP COLUMN IF EXISTS is_pie;
ALTER TABLE audit_report DROP COLUMN IF EXISTS report_body_json;

ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS created_via;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS selected_sections;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS source_snapshot_refs;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS hash_chain_entry_id;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS file_hash;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS file_size;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS html_path;

ALTER TABLE word_export_task DROP COLUMN IF EXISTS archived_at;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS sign_type;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS signed_at;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS signed_by;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS reject_reason;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS approval_at;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS approval_by;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS prior_period_info;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS report_date;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS selected_sections;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS source_snapshot_refs;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS is_pie;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS doc_subtype;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS company_type;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS opinion_type;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS report_body_json;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS html_path;
ALTER TABLE word_export_task DROP COLUMN IF EXISTS file_size;
