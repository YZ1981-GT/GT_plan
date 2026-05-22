-- R006__rollback_eqcr_snapshots.sql
-- 回滚 V006__eqcr_snapshots.sql
-- 删除 eqcr_snapshots 表及其所有索引

DROP INDEX IF EXISTS idx_eqcr_snapshots_created_at;
DROP INDEX IF EXISTS idx_eqcr_snapshots_project_year;
DROP INDEX IF EXISTS idx_eqcr_snapshots_current;
DROP TABLE IF EXISTS eqcr_snapshots;
