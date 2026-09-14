CREATE TABLE IF NOT EXISTS aging_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_index_id UUID NOT NULL REFERENCES wp_index(id) ON DELETE CASCADE,
    preset VARCHAR(20) NOT NULL DEFAULT 'CUSTOM',
    segments JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_aging_segments_wp UNIQUE (wp_index_id)
);
CREATE INDEX IF NOT EXISTS ix_aging_segments_wp ON aging_segments(wp_index_id);
COMMENT ON TABLE aging_segments IS '账龄段枚举配置（每个底稿一条，关联 wp_index_id）';
