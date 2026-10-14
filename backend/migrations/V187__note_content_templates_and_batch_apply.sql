-- V187: 附注内容模板不可变版本与正文批量应用审计
-- spec: disclosure-note-doc-upload-and-batch-fill Phase 1

CREATE TABLE IF NOT EXISTS note_content_templates (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    VARCHAR(200) NOT NULL,
    description             TEXT,
    owner_scope             VARCHAR(16) NOT NULL,
    owner_user_id           UUID REFERENCES users(id) ON DELETE RESTRICT,
    owner_group_project_id  UUID REFERENCES projects(id) ON DELETE RESTRICT,
    current_version_id      UUID,
    is_deleted              BOOLEAN NOT NULL DEFAULT false,
    deleted_at              TIMESTAMPTZ,
    created_by              UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_nct_owner_scope CHECK (owner_scope IN ('personal', 'group')),
    CONSTRAINT ck_nct_owner_shape CHECK (
        (owner_scope = 'personal' AND owner_user_id IS NOT NULL AND owner_group_project_id IS NULL)
        OR
        (owner_scope = 'group' AND owner_user_id IS NULL AND owner_group_project_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_nct_personal_active_name
    ON note_content_templates (owner_user_id, lower(name))
    WHERE is_deleted = false AND owner_scope = 'personal';

CREATE UNIQUE INDEX IF NOT EXISTS ux_nct_group_active_name
    ON note_content_templates (owner_group_project_id, lower(name))
    WHERE is_deleted = false AND owner_scope = 'group';

CREATE INDEX IF NOT EXISTS idx_nct_group_visible
    ON note_content_templates (owner_group_project_id, updated_at DESC)
    WHERE is_deleted = false;

CREATE TABLE IF NOT EXISTS note_content_template_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id         UUID NOT NULL REFERENCES note_content_templates(id) ON DELETE RESTRICT,
    version_no          INTEGER NOT NULL,
    schema_version      INTEGER NOT NULL DEFAULT 1,
    source_project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    source_year         INTEGER NOT NULL,
    source_project_name VARCHAR(255) NOT NULL,
    template_type       VARCHAR(20) NOT NULL,
    report_scope        VARCHAR(20) NOT NULL,
    sections_data       JSONB NOT NULL DEFAULT '[]'::jsonb,
    quality_summary     JSONB NOT NULL DEFAULT '{}'::jsonb,
    content_hash        VARCHAR(64) NOT NULL,
    byte_size           INTEGER NOT NULL,
    created_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_nctv_version_positive CHECK (version_no > 0),
    CONSTRAINT ck_nctv_schema_positive CHECK (schema_version > 0),
    CONSTRAINT ck_nctv_hash_length CHECK (length(content_hash) = 64),
    CONSTRAINT ck_nctv_byte_size_nonnegative CHECK (byte_size >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_nctv_template_version
    ON note_content_template_versions (template_id, version_no);

CREATE UNIQUE INDEX IF NOT EXISTS ux_nctv_template_hash
    ON note_content_template_versions (template_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_nctv_source
    ON note_content_template_versions (source_project_id, source_year);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_nct_current_version'
    ) THEN
        ALTER TABLE note_content_templates
            ADD CONSTRAINT fk_nct_current_version
            FOREIGN KEY (current_version_id)
            REFERENCES note_content_template_versions(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS note_text_batch_applications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_kind         VARCHAR(24) NOT NULL,
    template_version_id UUID REFERENCES note_content_template_versions(id) ON DELETE RESTRICT,
    source_metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    target_project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    target_year         INTEGER NOT NULL,
    mutation_id         VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(64) NOT NULL,
    preview_digest      VARCHAR(64) NOT NULL,
    applied_count       INTEGER NOT NULL,
    mode_summary        JSONB NOT NULL DEFAULT '{}'::jsonb,
    detail              JSONB NOT NULL DEFAULT '[]'::jsonb,
    status              VARCHAR(16) NOT NULL DEFAULT 'succeeded',
    applied_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    applied_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ntba_source_kind CHECK (
        source_kind IN ('upload', 'knowledge', 'content_template')
    ),
    CONSTRAINT ck_ntba_source_template CHECK (
        (source_kind = 'content_template' AND template_version_id IS NOT NULL)
        OR (source_kind <> 'content_template' AND template_version_id IS NULL)
    ),
    CONSTRAINT ck_ntba_request_hash CHECK (length(request_fingerprint) = 64),
    CONSTRAINT ck_ntba_preview_hash CHECK (length(preview_digest) = 64),
    CONSTRAINT ck_ntba_applied_count CHECK (applied_count >= 0),
    CONSTRAINT ck_ntba_status CHECK (status = 'succeeded')
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ntba_project_mutation
    ON note_text_batch_applications (target_project_id, mutation_id);

CREATE INDEX IF NOT EXISTS idx_ntba_target_year
    ON note_text_batch_applications (target_project_id, target_year, applied_at DESC);

CREATE INDEX IF NOT EXISTS idx_ntba_template_version
    ON note_text_batch_applications (template_version_id)
    WHERE template_version_id IS NOT NULL;

COMMENT ON TABLE note_content_templates IS '附注富文本内容模板目录（个人/集团，软删除）';
COMMENT ON TABLE note_content_template_versions IS '附注内容模板不可变版本，不包含 table_data';
COMMENT ON TABLE note_text_batch_applications IS '附注正文上传/知识库/内容模板的原子批量应用审计';