-- V066: 审计报告模板填充 — projects/audit_report 企业子类型与模板版本字段 + fill_preview_sessions 预览会话表
-- Requirements: 1.1, 1.2, 2.9, 8.2, 6.1
-- 所有 DDL 使用 IF NOT EXISTS，保证幂等可重入

-- ============================================================================
-- 1. projects: 企业子类型（type_a/type_b/type_c/type_d，nullable）
-- ============================================================================

ALTER TABLE projects ADD COLUMN IF NOT EXISTS company_subtype VARCHAR(10);

-- ============================================================================
-- 2. audit_report: 企业子类型 + 模板详简版 + manifest 模板版本
-- ============================================================================

ALTER TABLE audit_report ADD COLUMN IF NOT EXISTS company_subtype VARCHAR(10);
ALTER TABLE audit_report ADD COLUMN IF NOT EXISTS template_variant VARCHAR(10) DEFAULT 'simple';
ALTER TABLE audit_report ADD COLUMN IF NOT EXISTS template_version VARCHAR(20);

-- ============================================================================
-- 3. fill_preview_sessions: 报告正文两阶段生成的 preview 会话（TTL 24h）
--    TimestampMixin 对应列须显式写 created_at/updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- ============================================================================

CREATE TABLE IF NOT EXISTS fill_preview_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    user_id UUID NOT NULL REFERENCES users(id),
    year INTEGER NOT NULL,
    opinion_type VARCHAR(30),
    company_subtype VARCHAR(10),
    template_variant VARCHAR(10),
    template_version VARCHAR(20),
    working_path TEXT,
    optional_sections_json JSONB,
    missing_fields JSONB,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for querying sessions by project + year
CREATE INDEX IF NOT EXISTS idx_fill_preview_sessions_project_year
    ON fill_preview_sessions(project_id, year);

-- Index for TTL cleanup by expiry
CREATE INDEX IF NOT EXISTS idx_fill_preview_sessions_expires_at
    ON fill_preview_sessions(expires_at);
