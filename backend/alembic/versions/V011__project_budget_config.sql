-- V011: projects 新增 budget_config JSONB 列（Phase 7 F8: 工时预算对比）

ALTER TABLE projects ADD COLUMN IF NOT EXISTS budget_config JSONB DEFAULT NULL;

COMMENT ON COLUMN projects.budget_config IS
  '工时预算配置: {"by_cycle":{"D":100,"E":80,...},"by_user":{"user_id":160,...},"total":800}';
