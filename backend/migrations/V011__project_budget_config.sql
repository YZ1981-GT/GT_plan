-- V011: projects 新增 budget_config JSONB 列
-- Phase 7 F8: 工时预算配置

ALTER TABLE projects ADD COLUMN IF NOT EXISTS budget_config JSONB DEFAULT NULL;
