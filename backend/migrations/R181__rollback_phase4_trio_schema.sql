-- R181：回滚 V181 — 删除 phase4 trio 扩展

-- 4. 删除 export_job_attempts 表
DROP TABLE IF EXISTS export_job_attempts CASCADE;

-- 3. 回滚 export_job_items_v2 新列
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS step_key;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS sequence;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS snapshot_id;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS version_id;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS file_path;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS file_size;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS file_sha256;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS attempt_count;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS last_attempt_id;

-- 2. 回滚 export_jobs_v2 新列
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS snapshot_id;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS kind;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS year;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS trio_total;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS trio_succeeded;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS started_at;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS finished_at;

-- 1. 删除 deliverable_snapshots 表
DROP TABLE IF EXISTS deliverable_snapshots CASCADE;
