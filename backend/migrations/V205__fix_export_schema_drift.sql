-- V205: 修复 export 三表 + word_export_task_versions schema 漂移
-- type_mismatch: snapshot_id varchar → uuid（4 表，当前数据全 NULL，安全 cast）
-- db_extra: 删除孤立列 export_job_attempts.trigger（ORM 使用 trigger_source）

-- 1. snapshot_id varchar → uuid
ALTER TABLE export_jobs_v2
    ALTER COLUMN snapshot_id TYPE uuid USING snapshot_id::uuid;

ALTER TABLE export_job_items_v2
    ALTER COLUMN snapshot_id TYPE uuid USING snapshot_id::uuid;

ALTER TABLE export_job_attempts
    ALTER COLUMN snapshot_id TYPE uuid USING snapshot_id::uuid;

ALTER TABLE word_export_task_versions
    ALTER COLUMN snapshot_id TYPE uuid USING snapshot_id::uuid;

-- 2. 删除孤立列 trigger（ORM 使用 trigger_source，二者并存为历史产物）
ALTER TABLE export_job_attempts
    DROP COLUMN IF EXISTS trigger;
