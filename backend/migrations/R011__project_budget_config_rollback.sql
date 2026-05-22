-- R011: 回滚 budget_config 列
ALTER TABLE projects DROP COLUMN IF EXISTS budget_config;
