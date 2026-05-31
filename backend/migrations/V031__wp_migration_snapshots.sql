-- V031: 底稿迁移快照表
-- Spec: wp-template-migration
-- Requirements: 4.1 (迁移前快照支持回滚)

CREATE TABLE IF NOT EXISTS wp_migration_snapshots (
    id UUID PRIMARY KEY,
    wp_id UUID NOT NULL,
    parsed_data_snapshot JSONB NOT NULL,
    migration_reason VARCHAR(100) NOT NULL DEFAULT 'template_upgrade',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wp_migration_snapshots_wp_id
    ON wp_migration_snapshots (wp_id);

CREATE INDEX IF NOT EXISTS idx_wp_migration_snapshots_created_at
    ON wp_migration_snapshots (created_at DESC);

COMMENT ON TABLE wp_migration_snapshots IS '底稿迁移快照（模板版本升级前保存 parsed_data）';
COMMENT ON COLUMN wp_migration_snapshots.wp_id IS '底稿 ID（关联 working_paper.id）';
COMMENT ON COLUMN wp_migration_snapshots.parsed_data_snapshot IS '迁移前的完整 parsed_data';
COMMENT ON COLUMN wp_migration_snapshots.migration_reason IS '迁移原因（template_upgrade / manual）';
