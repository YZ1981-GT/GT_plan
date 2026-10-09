-- R174：回滚 V174（合并签字冻结快照）
-- 注意：回滚会删除全部 consol_snapshots 历史快照。
DROP INDEX IF EXISTS idx_consol_snapshots_project_year_created;
DROP TABLE IF EXISTS consol_snapshots;
