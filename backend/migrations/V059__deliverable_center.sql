-- V059: 审计报告交付件管理中心 — 扩展 word_export_task / versions / audit_report
-- deliverable-center spec; 全部 ADD COLUMN IF NOT EXISTS，不改 PG 枚举

-- 1. word_export_task（交付物主表扩展）
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS file_size BIGINT;
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS html_path TEXT;
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS report_body_json JSONB;
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS opinion_type VARCHAR(30);
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS company_type VARCHAR(20);
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS doc_subtype VARCHAR(40);
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS is_pie BOOLEAN DEFAULT false;
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS source_snapshot_refs JSONB;
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS selected_sections JSONB;
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS report_date DATE;
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS prior_period_info VARCHAR(40);
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS approval_by UUID REFERENCES users(id);
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS approval_at TIMESTAMPTZ;
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS reject_reason TEXT;
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS signed_by UUID REFERENCES users(id);
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS signed_at TIMESTAMPTZ;
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS sign_type VARCHAR(20);
ALTER TABLE word_export_task ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

-- 2. word_export_task_versions（版本表扩展）
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS html_path TEXT;
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS file_size BIGINT;
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64);
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS hash_chain_entry_id UUID;
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS source_snapshot_refs JSONB;
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS selected_sections JSONB;
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS created_via VARCHAR(20) DEFAULT 'generate';

-- 3. audit_report（报告正文结构化主源）
ALTER TABLE audit_report ADD COLUMN IF NOT EXISTS report_body_json JSONB;
ALTER TABLE audit_report ADD COLUMN IF NOT EXISTS is_pie BOOLEAN DEFAULT false;
ALTER TABLE audit_report ADD COLUMN IF NOT EXISTS prior_period_info VARCHAR(40);

-- 4. 索引
CREATE INDEX IF NOT EXISTS idx_wet_doc_subtype ON word_export_task (project_id, doc_subtype);
CREATE INDEX IF NOT EXISTS idx_wetv_file_hash ON word_export_task_versions (file_hash);
