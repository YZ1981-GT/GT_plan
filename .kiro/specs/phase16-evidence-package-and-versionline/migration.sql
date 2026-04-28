-- Phase 16 migration draft: version line, integrity checks, offline conflicts
BEGIN;

CREATE TABLE IF NOT EXISTS version_line_stamps (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    object_type VARCHAR(32) NOT NULL,
    object_id UUID NOT NULL,
    version_no INT NOT NULL,
    source_snapshot_id VARCHAR(64) NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_version_line_project_object
ON version_line_stamps(project_id, object_type, object_id, version_no DESC);

CREATE TABLE IF NOT EXISTS evidence_hash_checks (
    id UUID PRIMARY KEY,
    export_id UUID NOT NULL,
    file_path TEXT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    signature_digest VARCHAR(128) NULL,
    check_status VARCHAR(16) NOT NULL,
    checked_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_hash_export
ON evidence_hash_checks(export_id, checked_at DESC);

CREATE TABLE IF NOT EXISTS offline_conflicts (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    wp_id UUID NOT NULL,
    procedure_id UUID NOT NULL,
    field_name VARCHAR(64) NOT NULL,
    local_value JSONB NULL,
    remote_value JSONB NULL,
    status VARCHAR(16) NOT NULL,
    resolver_id UUID NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_offline_conflicts_project_status
ON offline_conflicts(project_id, status, created_at DESC);

COMMIT;
