-- Phase 16 migration: version line, integrity checks, offline conflicts
-- 对齐 v2 5.9.3 D-03/D-04 + WP-ENT-07
BEGIN;

-- 版本链统一戳记表
CREATE TABLE IF NOT EXISTS version_line_stamps (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    object_type VARCHAR(32) NOT NULL,   -- report/note/workpaper/procedure
    object_id UUID NOT NULL,
    version_no INT NOT NULL,
    source_snapshot_id VARCHAR(64) NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_version_line_project_object
ON version_line_stamps(project_id, object_type, object_id, version_no DESC);

CREATE INDEX IF NOT EXISTS idx_version_line_trace
ON version_line_stamps(trace_id);

-- 取证包完整性校验表（对齐 v2 5.9.3 D-04）
-- 注：export_id 应关联到导出任务表（export_tasks 或 word_export_tasks），
-- 此处不加硬 FK 以兼容多种导出来源，但应用层必须校验 export_id 有效性
CREATE TABLE IF NOT EXISTS evidence_hash_checks (
    id UUID PRIMARY KEY,
    export_id UUID NOT NULL,            -- 关联导出任务ID
    file_path TEXT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    signature_digest VARCHAR(128) NULL, -- 可选签名摘要
    check_status VARCHAR(16) NOT NULL,  -- passed/failed
    checked_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_hash_export
ON evidence_hash_checks(export_id, checked_at DESC);

-- 离线冲突与人工合并队列表（对齐 v2 5.9.3 D-03）
CREATE TABLE IF NOT EXISTS offline_conflicts (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    wp_id UUID NOT NULL,
    procedure_id UUID NOT NULL,
    field_name VARCHAR(64) NOT NULL,
    local_value JSONB NULL,
    remote_value JSONB NULL,
    merged_value JSONB NULL,            -- 人工合并后的最终值
    status VARCHAR(16) NOT NULL,        -- open/resolved/rejected
    resolver_id UUID NULL,
    reason_code VARCHAR(64) NULL,       -- 处置原因码（对齐 v2 4.5.6 统一原因码）
    qc_replay_job_id UUID NULL,         -- 合并后触发的 QC 重跑任务ID
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_offline_conflicts_project_status
ON offline_conflicts(project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_offline_conflicts_wp
ON offline_conflicts(wp_id, status);

CREATE INDEX IF NOT EXISTS idx_offline_conflicts_trace
ON offline_conflicts(trace_id);

COMMIT;
