-- R180：回滚 V180（交付中心三件套 attempt + 三层一致字段）
-- 逆序删除：先 attempt 表及其索引，再版本/明细/主表新增列。全部 IF EXISTS 幂等。

-- 4. export_job_attempts 表及索引
DROP INDEX IF EXISTS idx_export_job_attempts_job;
DROP INDEX IF EXISTS uq_export_job_attempt_item_no;
DROP TABLE IF EXISTS export_job_attempts;

-- 3. word_export_task_versions 新增列
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS snapshot_id;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS file_sha256;

-- 2. export_job_items_v2 新增列与约束
DROP INDEX IF EXISTS uq_export_job_item_step;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS last_attempt_id;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS attempt_count;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS file_sha256;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS file_size;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS file_path;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS version_id;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS snapshot_id;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS sequence;
ALTER TABLE export_job_items_v2 DROP COLUMN IF EXISTS step_key;

-- 1. export_jobs_v2 新增列
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS finished_at;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS started_at;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS readiness;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS trio_succeeded;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS trio_total;
ALTER TABLE export_jobs_v2 DROP COLUMN IF EXISTS snapshot_id;
