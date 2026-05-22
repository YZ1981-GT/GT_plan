-- V009: eqcr_snapshots 新增 judgments JSONB 列
-- Phase 7 F1: EQCR 结构化判断模板

ALTER TABLE eqcr_snapshots
ADD COLUMN IF NOT EXISTS judgments JSONB DEFAULT NULL;

COMMENT ON COLUMN eqcr_snapshots.judgments IS
  'EQCR 5 维度结构化判断: {"dimensions":[{key,conclusion,rationale,referenced_wps,risk_level},...], "submitted_at","submitted_by"}';

CREATE INDEX IF NOT EXISTS idx_eqcr_snapshots_judgments_gin
ON eqcr_snapshots USING GIN (judgments);
