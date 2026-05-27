-- V018__fix_schema_drift_full.sql
-- 自动生成：补齐 ORM-vs-PG 全部缺列与缺表（idempotent）

BEGIN;

-- 10 missing tables, 65 missing columns

CREATE TABLE IF NOT EXISTS event_outbox_dlq (
	id UUID NOT NULL, 
	original_event_id UUID, 
	event_type VARCHAR(100) NOT NULL, 
	project_id UUID NOT NULL, 
	year INTEGER, 
	payload JSONB, 
	failure_reason TEXT, 
	attempt_count INTEGER DEFAULT 0 NOT NULL, 
	moved_to_dlq_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	resolved_by UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(original_event_id) REFERENCES import_event_outbox (id) ON DELETE SET NULL, 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(resolved_by) REFERENCES users (id)
);
CREATE INDEX IF NOT EXISTS idx_event_outbox_dlq_unresolved ON event_outbox_dlq (moved_to_dlq_at) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_event_outbox_dlq_project_year ON event_outbox_dlq (project_id, year, moved_to_dlq_at);

CREATE TABLE IF NOT EXISTS workpaper_sheet_classification (
	id UUID NOT NULL, 
	wp_code VARCHAR(50) NOT NULL, 
	sheet_name VARCHAR(255) NOT NULL, 
	class_code VARCHAR(20), 
	class VARCHAR(20), 
	is_real_workpaper BOOLEAN DEFAULT true NOT NULL, 
	exclude_from_archive BOOLEAN DEFAULT false NOT NULL, 
	exclude_from_progress BOOLEAN DEFAULT false NOT NULL, 
	is_static_doc BOOLEAN DEFAULT false NOT NULL, 
	scope VARCHAR(20) DEFAULT 'standalone' NOT NULL, 
	delegated_module VARCHAR(50), 
	template_version_id UUID, 
	render_schema_path VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_wpsc_wp_code_sheet_name UNIQUE (wp_code, sheet_name), 
	FOREIGN KEY(template_version_id) REFERENCES workpaper_template_version (id)
);
CREATE INDEX IF NOT EXISTS idx_wpsc_wp_code_version ON workpaper_sheet_classification (wp_code, template_version_id);
CREATE INDEX IF NOT EXISTS idx_wpsc_class_scope ON workpaper_sheet_classification (class, scope);

CREATE TABLE IF NOT EXISTS workpaper_template_version (
	id UUID NOT NULL, 
	version VARCHAR(20) NOT NULL, 
	release_date DATE NOT NULL, 
	source VARCHAR(50) DEFAULT '致同总所' NOT NULL, 
	is_current BOOLEAN DEFAULT false NOT NULL, 
	parent_version_id UUID, 
	changelog TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (version), 
	FOREIGN KEY(parent_version_id) REFERENCES workpaper_template_version (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS project_workpaper_sheet_override (
	id UUID NOT NULL, 
	project_id UUID NOT NULL, 
	wp_code VARCHAR(50) NOT NULL, 
	sheet_name VARCHAR(255) NOT NULL, 
	class_override VARCHAR(20), 
	scope_override VARCHAR(20), 
	schema_override JSONB, 
	reason TEXT, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_pwpso_project_wp_sheet UNIQUE (project_id, wp_code, sheet_name), 
	FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE INDEX IF NOT EXISTS idx_pwpso_project_wp ON project_workpaper_sheet_override (project_id, wp_code);

CREATE TABLE IF NOT EXISTS eqcr_snapshots (
	id UUID NOT NULL, 
	project_id UUID NOT NULL, 
	year INTEGER NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	snapshot_data JSONB, 
	is_current BOOLEAN DEFAULT true NOT NULL, 
	judgments JSONB, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE INDEX IF NOT EXISTS idx_eqcr_snapshots_project_year ON eqcr_snapshots (project_id, year);

CREATE TABLE IF NOT EXISTS annual_independence_declarations (
	id UUID NOT NULL, 
	project_id UUID, 
	declarant_id UUID NOT NULL, 
	declaration_year INTEGER NOT NULL, 
	answers JSONB, 
	attachments JSONB, 
	risk_flagged_count INTEGER NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	submitted_at TIMESTAMP WITH TIME ZONE, 
	signed_at TIMESTAMP WITH TIME ZONE, 
	signature_record_id UUID, 
	reviewed_by_qc_id UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	is_deleted BOOLEAN NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_annual_independence_declarant_year UNIQUE (declarant_id, declaration_year), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(declarant_id) REFERENCES users (id)
);
CREATE INDEX IF NOT EXISTS idx_annual_independence_year ON annual_independence_declarations (declaration_year) WHERE is_deleted = false;
CREATE INDEX IF NOT EXISTS idx_independence_project_declarant ON annual_independence_declarations (project_id, declarant_id) WHERE is_deleted = false;

CREATE TABLE IF NOT EXISTS qc_rule_definitions (
	id UUID NOT NULL, 
	rule_code VARCHAR(30) NOT NULL, 
	severity VARCHAR(20) NOT NULL, 
	scope VARCHAR(30) NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT, 
	standard_ref JSONB, 
	expression_type VARCHAR(20) NOT NULL, 
	expression TEXT, 
	parameters_schema JSONB, 
	enabled BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (rule_code)
);
CREATE INDEX IF NOT EXISTS idx_qc_rule_definitions_scope ON qc_rule_definitions (scope);
CREATE INDEX IF NOT EXISTS idx_qc_rule_definitions_enabled ON qc_rule_definitions (enabled);

CREATE TABLE IF NOT EXISTS adjustment_editing_locks (
	id UUID NOT NULL, 
	project_id UUID NOT NULL, 
	entry_group_id UUID NOT NULL, 
	locked_by UUID NOT NULL, 
	locked_by_name VARCHAR(100), 
	acquired_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	heartbeat_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	released_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(locked_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS tb_change_history (
	id UUID NOT NULL, 
	project_id UUID NOT NULL, 
	year INTEGER NOT NULL, 
	row_code VARCHAR(20) NOT NULL, 
	operation_type VARCHAR(30) NOT NULL, 
	operator_id UUID NOT NULL, 
	operator_name VARCHAR(100), 
	delta_amount NUMERIC(20, 2), 
	audited_after NUMERIC(20, 2), 
	source_adjustment_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(operator_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS event_cascade_log (
	id UUID NOT NULL, 
	project_id UUID NOT NULL, 
	year INTEGER, 
	trigger_event VARCHAR(50) NOT NULL, 
	trigger_payload JSONB, 
	steps JSONB DEFAULT '[]' NOT NULL, 
	status VARCHAR(20) DEFAULT 'running' NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	total_duration_ms INTEGER, 
	PRIMARY KEY (id)
);

ALTER TABLE projects ADD COLUMN IF NOT EXISTS risk_level_updated_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS contract_amount NUMERIC(20, 2) NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS review_config JSONB NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS retention_until TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS budget_config JSONB NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS budgeted_by UUID NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS budget_hours INTEGER NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS scenario VARCHAR(20) NOT NULL DEFAULT 'normal';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS budgeted_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS risk_level VARCHAR(10) NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS has_foreign_currency BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS read_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default';
ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS raw_extra JSONB NULL;
ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default';
ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS raw_extra JSONB NULL;
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default';
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS level INTEGER NULL;
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS raw_extra JSONB NULL;
ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default';
ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS raw_extra JSONB NULL;
ALTER TABLE unadjusted_misstatements ADD COLUMN IF NOT EXISTS bound_dataset_id UUID NULL;
ALTER TABLE unadjusted_misstatements ADD COLUMN IF NOT EXISTS dataset_bound_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE ledger_datasets ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default';
ALTER TABLE import_artifacts ADD COLUMN IF NOT EXISTS retention_class VARCHAR(20) NOT NULL DEFAULT 'transient';
ALTER TABLE import_artifacts ADD COLUMN IF NOT EXISTS retention_expires_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE activation_records ADD COLUMN IF NOT EXISTS before_row_counts JSONB NULL;
ALTER TABLE activation_records ADD COLUMN IF NOT EXISTS after_row_counts JSONB NULL;
ALTER TABLE activation_records ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64) NULL;
ALTER TABLE activation_records ADD COLUMN IF NOT EXISTS duration_ms INTEGER NULL;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS last_sync_source VARCHAR(50) NULL;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS last_sync_user_id UUID NULL;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS dataset_bound_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS bound_dataset_id UUID NULL;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS last_sync_wp_id UUID NULL;
ALTER TABLE audit_report ADD COLUMN IF NOT EXISTS bound_dataset_id UUID NULL;
ALTER TABLE audit_report ADD COLUMN IF NOT EXISTS dataset_bound_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS review_status wp_review_status NOT NULL DEFAULT 'not_submitted';
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS rejection_reason TEXT NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS workflow_status VARCHAR(30) NOT NULL DEFAULT 'draft';
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS dataset_bound_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS last_parsed_sync_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS parsed_data JSONB NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS rejected_by UUID NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS bound_dataset_id UUID NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS partner_reviewed_by UUID NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS consistency_status VARCHAR(30) NOT NULL DEFAULT 'unknown';
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS explanation_status VARCHAR(30) NOT NULL DEFAULT 'not_started';
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS prefill_tb_snapshot JSONB NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS partner_reviewed_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS prefill_stale BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS conversation_id UUID NULL;
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS target_cell VARCHAR(50) NULL;
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS source_sheet VARCHAR(100) NULL;
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS review_layer VARCHAR(20) NULL;
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS target_sheet VARCHAR(100) NULL;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ocr_fields_cache JSON NULL;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS previous_version_id UUID NULL;
ALTER TABLE attachment_working_paper ADD COLUMN IF NOT EXISTS notes TEXT NULL;
ALTER TABLE attachment_working_paper ADD COLUMN IF NOT EXISTS created_by UUID NULL;
ALTER TABLE attachment_working_paper ADD COLUMN IF NOT EXISTS wp_id UUID NULL;

COMMIT;