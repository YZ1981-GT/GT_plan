-- V097: 创建 workpaper_snapshots 表
-- 底稿版本链通用组件：存储 field-level 数据版本快照，支持时间线展示、diff 对比、回滚

CREATE TABLE IF NOT EXISTS workpaper_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    workpaper_id UUID NOT NULL REFERENCES working_paper(id),
    user_id UUID NOT NULL,
    snapshot_type VARCHAR(50) NOT NULL,
    description TEXT,
    change_summary TEXT,
    data_json JSONB NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    data_size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wp_snapshots_wp_created
    ON workpaper_snapshots(workpaper_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_wp_snapshots_project
    ON workpaper_snapshots(project_id);
