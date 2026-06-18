-- V087: 项目审计类型 + 大型国企标记（A21~A25 复核底稿模板选择）
--
-- audit_type: financial / internal_control / combined
-- is_large_soe: 影响 A24-1 / A25-1 国企版 vs 非国企版

ALTER TABLE projects ADD COLUMN IF NOT EXISTS audit_type VARCHAR(32) DEFAULT 'financial';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS is_large_soe BOOLEAN DEFAULT false;

COMMENT ON COLUMN projects.audit_type IS 'financial/internal_control/combined — A21~A25 子码选择';
COMMENT ON COLUMN projects.is_large_soe IS '大型国企标记 — A24-1/A25-1 模板变体';
