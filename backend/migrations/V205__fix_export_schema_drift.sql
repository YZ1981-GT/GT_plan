-- V205: 修复 export 三表 + word_export_task_versions schema 漂移
-- ① 补 ORM 已有、库里缺的列：export_jobs_v2.readiness、word_export_task_versions.snapshot_id / file_sha256。
--    磁盘上没有任何迁移加过这 3 列（/api/health schema_drift 报 orm_extra）；原 V205 直接
--    `ALTER TABLE word_export_task_versions ALTER COLUMN snapshot_id TYPE uuid`，在没有该列的库上必报 42703，
--    整个迁移从未在本地库应用过（spec note-pull-followup-closure R24，2026-10-27 改为可重入）。
-- ② snapshot_id varchar → uuid：只在列存在且仍不是 uuid 时转（当前数据全 NULL，安全 cast）。
-- ③ 删除孤立列 export_job_attempts.trigger（ORM 使用 trigger_source）。

ALTER TABLE export_jobs_v2 ADD COLUMN IF NOT EXISTS readiness JSONB;
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS snapshot_id UUID;
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS file_sha256 VARCHAR(64);

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['export_jobs_v2', 'export_job_items_v2', 'export_job_attempts', 'word_export_task_versions'] LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = t
              AND column_name = 'snapshot_id' AND udt_name <> 'uuid'
        ) THEN
            EXECUTE format('ALTER TABLE %I ALTER COLUMN snapshot_id TYPE uuid USING snapshot_id::uuid', t);
        END IF;
    END LOOP;
END
$$;

ALTER TABLE export_job_attempts DROP COLUMN IF EXISTS trigger;
