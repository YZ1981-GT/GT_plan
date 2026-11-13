-- R264: 回滚 V264（working_paper_sync_conflict.schema_anomaly）
--
-- 删列即丢掉已记录的成因，读侧会退回「全部 schema 冲突不可裁决」的旧行为。
-- 这正是 V264 要修的缺陷，故回滚只在需要整体退版时执行。
ALTER TABLE working_paper_sync_conflict
    DROP COLUMN IF EXISTS schema_anomaly;
