-- V046: 补建 4 张「曾按需建/实际从未建」的附注相关表
-- 背景：以下 4 表有 service INSERT/SELECT 路径但从未有迁移建表，
--   真实 PG 缺表 → 对应只读端点 UndefinedTable 500：
--   - group_note_templates       (notes/group-template/list)
--   - note_section_locks         (notes/locks/active)
--   - data_snapshots             (data-lock/snapshots)
--   - note_section_templates     (notes/custom-sections/templates)
-- 列定义对齐各 service 的 INSERT 语句。

CREATE TABLE IF NOT EXISTS group_note_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    template_data JSONB NOT NULL,
    created_by UUID,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS note_section_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    template_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS note_section_locks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    year INT NOT NULL,
    section_code VARCHAR(100) NOT NULL,
    locked_by UUID,
    locked_by_name VARCHAR(150),
    acquired_at TIMESTAMPTZ DEFAULT now(),
    heartbeat_at TIMESTAMPTZ DEFAULT now(),
    released_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_note_section_locks_active
    ON note_section_locks (project_id, year, section_code)
    WHERE released_at IS NULL;

CREATE TABLE IF NOT EXISTS data_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    year INT NOT NULL,
    snapshot_data JSONB NOT NULL,
    data_hash VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_data_snapshots_project_year
    ON data_snapshots (project_id, year, created_at DESC);
