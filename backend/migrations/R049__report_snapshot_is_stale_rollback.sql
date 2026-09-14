-- R049: 回滚 report_snapshot.is_stale 列

ALTER TABLE report_snapshot DROP COLUMN IF EXISTS is_stale;
