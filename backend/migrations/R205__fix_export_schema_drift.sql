-- R205: V205 幂等回放（保护性 IF EXISTS / IF NOT EXISTS；与 V205 同口径，见其注释）

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
