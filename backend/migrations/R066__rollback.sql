-- R066: 回滚审计报告模板填充字段
-- 对应 V066__template_fill_columns.sql

-- 1. Drop fill_preview_sessions 表（含索引随表一并删除）
DROP TABLE IF EXISTS fill_preview_sessions;

-- 2. audit_report: 移除模板版本/详简版/企业子类型
ALTER TABLE audit_report DROP COLUMN IF EXISTS template_version;
ALTER TABLE audit_report DROP COLUMN IF EXISTS template_variant;
ALTER TABLE audit_report DROP COLUMN IF EXISTS company_subtype;

-- 3. projects: 移除企业子类型
ALTER TABLE projects DROP COLUMN IF EXISTS company_subtype;
