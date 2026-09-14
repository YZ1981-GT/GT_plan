-- V055__project_creation_enhancement.sql
ALTER TABLE projects ADD COLUMN IF NOT EXISTS short_name VARCHAR(100);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS audit_year INT;

-- 回填 audit_year（从 wizard_state JSONB）
UPDATE projects SET audit_year = (wizard_state->'steps'->'basic_info'->'data'->>'audit_year')::int
WHERE audit_year IS NULL
  AND wizard_state->'steps'->'basic_info'->'data'->>'audit_year' IS NOT NULL;

-- 回填 audit_year（从 audit_period_end）
UPDATE projects SET audit_year = EXTRACT(YEAR FROM audit_period_end)::int
WHERE audit_year IS NULL AND audit_period_end IS NOT NULL;

-- 唯一性约束：company_code + audit_year + report_scope（仅非删除 + 非空 company_code）
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_company_year_scope
ON projects (company_code, audit_year, report_scope)
WHERE is_deleted = false AND company_code IS NOT NULL AND audit_year IS NOT NULL;
