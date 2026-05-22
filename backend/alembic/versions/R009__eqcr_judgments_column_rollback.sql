-- R009: 回滚 eqcr_snapshots judgments 列
DROP INDEX IF EXISTS idx_eqcr_snapshots_judgments_gin;
ALTER TABLE eqcr_snapshots DROP COLUMN IF EXISTS judgments;
