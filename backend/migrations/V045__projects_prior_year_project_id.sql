-- V045: projects 加 prior_year_project_id 列（连续审计跨年关联）
-- 背景：continuous_audit_service.create_next_year 用 raw SQL
--   `UPDATE projects SET prior_year_project_id = ...` 写本年→上年关联，
--   且 prior-year-data / find_prior_year_workpaper 端点按此列查上年数据，
--   但该列从未建过 → UndefinedColumn 致 prior-year-data 端点 500、
--   create-next-year 写入失败。本迁移补齐该意图列。

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS prior_year_project_id UUID;

-- 自引用外键（指向上年项目），按编码加索引便于跨年查询
CREATE INDEX IF NOT EXISTS idx_projects_prior_year
    ON projects (prior_year_project_id)
    WHERE prior_year_project_id IS NOT NULL;
