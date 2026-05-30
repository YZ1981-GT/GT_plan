-- V028: projects 表新增结构化统一准则状态源 applicable_standard_v2
-- Requirements: 1.1 — 多准则状态统一（multi-standard-unification）
-- JSON 结构: {entity_type: "soe"|"listed"|"private",
--             scope: "standalone"|"consolidated",
--             stage: "normal"|"ipo"|"transfer"|"restructure"|"fraud_response"}

ALTER TABLE projects ADD COLUMN IF NOT EXISTS applicable_standard_v2 JSONB;
