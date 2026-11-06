-- R265: V265 无损回滚预检。任一新证据存在时整单阻断；所有检查先于 DROP。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM custom_workbook_unit_authorities LIMIT 1) THEN
        RAISE EXCEPTION 'Cannot rollback V265: custom workbook unit authority exists';
    END IF;
    IF EXISTS (
        SELECT 1 FROM export_tasks
        WHERE unit_policy_snapshot IS NOT NULL OR export_year IS NOT NULL OR jsonb_array_length(document_types) > 1
        LIMIT 1
    ) THEN
        RAISE EXCEPTION 'Cannot rollback V265: export task has year, policy, or multiple document types';
    END IF;
    IF EXISTS (
        SELECT 1 FROM export_tasks
        WHERE document_type IS NOT NULL
          AND document_types <> jsonb_build_array(document_type)
        LIMIT 1
    ) THEN
        RAISE EXCEPTION 'Cannot rollback V265: singular and plural document types conflict';
    END IF;
    IF EXISTS (
        SELECT 1 FROM word_export_task_versions
        WHERE unit_policy_snapshot IS NOT NULL OR unit_policy_digest IS NOT NULL
        LIMIT 1
    ) THEN
        RAISE EXCEPTION 'Cannot rollback V265: Word version policy evidence exists';
    END IF;
    IF EXISTS (
        SELECT 1 FROM working_paper_content_version
        WHERE export_surface_class IS NOT NULL OR unit_policy_snapshot IS NOT NULL
           OR unit_policy_digest IS NOT NULL OR source_storage_unit IS NOT NULL
        LIMIT 1
    ) THEN
        RAISE EXCEPTION 'Cannot rollback V265: workpaper content version export evidence exists';
    END IF;
END
$$;

UPDATE export_tasks
SET document_type = document_types ->> 0
WHERE document_type IS NULL AND jsonb_array_length(document_types) = 1;

ALTER TABLE working_paper_content_version DROP CONSTRAINT IF EXISTS ck_wpcv_export_unit_evidence;
ALTER TABLE working_paper_content_version DROP COLUMN IF EXISTS source_storage_unit;
ALTER TABLE working_paper_content_version DROP COLUMN IF EXISTS unit_policy_digest;
ALTER TABLE working_paper_content_version DROP COLUMN IF EXISTS unit_policy_snapshot;
ALTER TABLE working_paper_content_version DROP COLUMN IF EXISTS export_surface_class;

ALTER TABLE word_export_task_versions DROP CONSTRAINT IF EXISTS ck_word_export_version_unit_policy_pair;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS unit_policy_digest;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS unit_policy_snapshot;

ALTER TABLE export_tasks DROP CONSTRAINT IF EXISTS ck_export_tasks_policy_object;
ALTER TABLE export_tasks DROP CONSTRAINT IF EXISTS ck_export_tasks_document_types_array;
ALTER TABLE export_tasks DROP COLUMN IF EXISTS unit_policy_snapshot;
ALTER TABLE export_tasks DROP COLUMN IF EXISTS document_types;
ALTER TABLE export_tasks DROP COLUMN IF EXISTS export_year;

DROP TABLE IF EXISTS custom_workbook_unit_authorities;
