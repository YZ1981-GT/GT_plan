-- R045: 回滚 projects.prior_year_project_id 列 + 索引

DROP INDEX IF EXISTS idx_projects_prior_year;

ALTER TABLE projects DROP COLUMN IF EXISTS prior_year_project_id;
