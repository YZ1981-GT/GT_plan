-- R017__v3_refinement_tables_rollback.sql
-- 回滚 V017__v3_refinement_tables.sql
-- 删除 3 张表及其所有索引（索引随表自动删除，显式 DROP 保持清晰）

-- time_machine_snapshots 索引
DROP INDEX IF EXISTS idx_time_machine_snapshots_project;
DROP INDEX IF EXISTS idx_time_machine_snapshots_instance;

-- time_machine_snapshots 表
DROP TABLE IF EXISTS time_machine_snapshots;

-- cross_module_conflicts 索引
DROP INDEX IF EXISTS idx_cross_module_conflicts_target;
DROP INDEX IF EXISTS idx_cross_module_conflicts_project_status;

-- cross_module_conflicts 表
DROP TABLE IF EXISTS cross_module_conflicts;

-- ai_content_log 索引
DROP INDEX IF EXISTS idx_ai_content_log_wp;
DROP INDEX IF EXISTS idx_ai_content_log_project_action;
DROP INDEX IF EXISTS idx_ai_content_log_project;

-- ai_content_log 表
DROP TABLE IF EXISTS ai_content_log;
