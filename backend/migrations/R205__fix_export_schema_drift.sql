-- R205: V205 幂等回放（保护性 IF EXISTS）

DO $$
BEGIN
    -- snapshot_id varchar → uuid（跳过已是 uuid 的列）
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'export_jobs_v2'
          AND column_name = 'snapshot_id' AND udt_name != 'uuid'
    ) THEN
        ALTER TABLE export_jobs_v2 ALTER COLUMN snapshot_id TYPE uuid USING snapshot_id::uuid;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'export_job_items_v2'
          AND column_name = 'snapshot_id' AND udt_name != 'uuid'
    ) THEN
        ALTER TABLE export_job_items_v2 ALTER COLUMN snapshot_id TYPE uuid USING snapshot_id::uuid;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'export_job_attempts'
          AND column_name = 'snapshot_id' AND udt_name != 'uuid'
    ) THEN
        ALTER TABLE export_job_attempts ALTER COLUMN snapshot_id TYPE uuid USING snapshot_id::uuid;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'word_export_task_versions'
          AND column_name = 'snapshot_id' AND udt_name != 'uuid'
    ) THEN
        ALTER TABLE word_export_task_versions ALTER COLUMN snapshot_id TYPE uuid USING snapshot_id::uuid;
    END IF;
END
$$;

ALTER TABLE export_job_attempts DROP COLUMN IF EXISTS trigger;
