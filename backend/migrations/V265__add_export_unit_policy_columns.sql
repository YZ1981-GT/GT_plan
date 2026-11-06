-- V265: 正式导出单位策略证据（platform-global-display-settings-closure 1C）
-- 共享库截至 2026-11-06 仍停在 V264；本文件尚未应用，可在首次落库前纠正原草稿字段漂移。
-- 全部 additive / IF NOT EXISTS；不改账套金额。

CREATE TABLE IF NOT EXISTS custom_workbook_unit_authorities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    working_paper_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    workbook_sha256 CHAR(64) NOT NULL,
    manifest JSONB NOT NULL,
    manifest_digest CHAR(64) NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_custom_wp_unit_authority_wp_hash UNIQUE (working_paper_id, workbook_sha256),
    CONSTRAINT ck_custom_wp_unit_authority_workbook_digest CHECK (workbook_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_custom_wp_unit_authority_manifest_digest CHECK (manifest_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_custom_wp_unit_authority_manifest_object CHECK (jsonb_typeof(manifest) = 'object')
);

ALTER TABLE export_tasks ADD COLUMN IF NOT EXISTS export_year INTEGER;
ALTER TABLE export_tasks ADD COLUMN IF NOT EXISTS document_types JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE export_tasks ADD COLUMN IF NOT EXISTS unit_policy_snapshot JSONB;
UPDATE export_tasks
SET document_types = jsonb_build_array(document_type)
WHERE document_type IS NOT NULL AND document_types = '[]'::jsonb;
ALTER TABLE export_tasks DROP CONSTRAINT IF EXISTS ck_export_tasks_document_types_array;
ALTER TABLE export_tasks ADD CONSTRAINT ck_export_tasks_document_types_array
    CHECK (jsonb_typeof(document_types) = 'array');
ALTER TABLE export_tasks DROP CONSTRAINT IF EXISTS ck_export_tasks_policy_object;
ALTER TABLE export_tasks ADD CONSTRAINT ck_export_tasks_policy_object
    CHECK (unit_policy_snapshot IS NULL OR jsonb_typeof(unit_policy_snapshot) = 'object');

ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS unit_policy_snapshot JSONB;
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS unit_policy_digest VARCHAR(64);
ALTER TABLE word_export_task_versions DROP CONSTRAINT IF EXISTS ck_word_export_version_unit_policy_pair;
ALTER TABLE word_export_task_versions ADD CONSTRAINT ck_word_export_version_unit_policy_pair CHECK (
    (unit_policy_snapshot IS NULL AND unit_policy_digest IS NULL)
    OR (
        unit_policy_snapshot IS NOT NULL
        AND jsonb_typeof(unit_policy_snapshot) = 'object'
        AND unit_policy_digest IS NOT NULL
        AND unit_policy_digest ~ '^[0-9a-f]{64}$'
    )
);

ALTER TABLE working_paper_content_version ADD COLUMN IF NOT EXISTS export_surface_class VARCHAR(20);
ALTER TABLE working_paper_content_version ADD COLUMN IF NOT EXISTS unit_policy_snapshot JSONB;
ALTER TABLE working_paper_content_version ADD COLUMN IF NOT EXISTS unit_policy_digest CHAR(64);
ALTER TABLE working_paper_content_version ADD COLUMN IF NOT EXISTS source_storage_unit VARCHAR(16);
ALTER TABLE working_paper_content_version DROP CONSTRAINT IF EXISTS ck_wpcv_export_unit_evidence;
ALTER TABLE working_paper_content_version ADD CONSTRAINT ck_wpcv_export_unit_evidence CHECK (
    (export_surface_class IS NULL
        AND unit_policy_snapshot IS NULL AND unit_policy_digest IS NULL AND source_storage_unit IS NULL)
    OR (export_surface_class = 'formal'
        AND unit_policy_snapshot IS NOT NULL AND jsonb_typeof(unit_policy_snapshot) = 'object'
        AND unit_policy_digest IS NOT NULL AND unit_policy_digest ~ '^[0-9a-f]{64}$'
        AND source_storage_unit IS NULL)
    OR (export_surface_class = 'data_exchange'
        AND unit_policy_snapshot IS NULL AND unit_policy_digest IS NULL
        AND source_storage_unit IS NOT NULL
        AND source_storage_unit IN ('yuan', 'qian', 'wan'))
    OR (export_surface_class IN ('template', 'non_amount')
        AND unit_policy_snapshot IS NULL AND unit_policy_digest IS NULL AND source_storage_unit IS NULL)
);
