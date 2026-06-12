-- V071: 底稿导入导出基础表（wp_export_snapshot + wp_version_archive）
-- Requirements: 1.5, 4.1, 6.1, 6.2, 6.3

CREATE TABLE IF NOT EXISTS wp_export_snapshot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    working_paper_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_version INT NOT NULL,
    snapshot_hash VARCHAR(64) NOT NULL,
    exported_by UUID REFERENCES users(id),
    exported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    file_format VARCHAR(10) NOT NULL DEFAULT 'xlsx',
    file_size_bytes BIGINT,
    metadata_bundle JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wp_export_snapshot_wp_version
    ON wp_export_snapshot(working_paper_id, file_version DESC);

CREATE TABLE IF NOT EXISTS wp_version_archive (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    working_paper_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version_no INT NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'import',
    content_hash VARCHAR(64),
    file_size_bytes BIGINT,
    archive_path TEXT,
    file_retained BOOLEAN NOT NULL DEFAULT true,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(working_paper_id, version_no)
);
