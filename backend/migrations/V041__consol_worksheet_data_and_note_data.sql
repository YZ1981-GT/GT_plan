-- V041: 将 consol_worksheet_data + consol_note_data 懒建表纳入 D6 迁移
-- 关联: global-modules-cleanup spec (合并模块懒建表治理)
-- Bug 条件: C5（懒建表绕 D6，drift detector 盲区）

-- 1. consol_worksheet_data — 合并工作底稿数据存储
CREATE TABLE IF NOT EXISTS consol_worksheet_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    year INT NOT NULL,
    sheet_key VARCHAR(100) NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by UUID,
    UNIQUE(project_id, year, sheet_key)
);

CREATE INDEX IF NOT EXISTS ix_cwd_project_year ON consol_worksheet_data(project_id, year);

-- 2. consol_note_data — 合并附注用户数据存储
CREATE TABLE IF NOT EXISTS consol_note_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    year INT NOT NULL,
    section_id VARCHAR(50) NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, year, section_id)
);

CREATE INDEX IF NOT EXISTS ix_cnd_proj_year ON consol_note_data(project_id, year);
