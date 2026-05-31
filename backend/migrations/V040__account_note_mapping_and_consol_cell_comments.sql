-- V040: 将 account_note_mapping + consol_cell_comments 懒建表纳入 D6 迁移
-- Bug 条件: C5（懒建表绕 D6，drift detector 盲区）
-- 属性: H4（懒建表入 D6，三层一致）

-- 1. account_note_mapping — 科目→附注行映射
CREATE TABLE IF NOT EXISTS account_note_mapping (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    account_name VARCHAR(200) NOT NULL,
    section_id VARCHAR(50) NOT NULL,
    row_name VARCHAR(200) NOT NULL,
    col_index INT NOT NULL DEFAULT 1,
    mapping_type VARCHAR(20) NOT NULL DEFAULT 'exact',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, account_name, section_id, row_name)
);

CREATE INDEX IF NOT EXISTS ix_anm_proj ON account_note_mapping(project_id);

-- 2. consol_cell_comments — 单元格批注与复核标记
CREATE TABLE IF NOT EXISTS consol_cell_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    year INT NOT NULL,
    module VARCHAR(50) NOT NULL,
    sheet_key VARCHAR(100) NOT NULL,
    row_idx INT NOT NULL,
    col_idx INT NOT NULL,
    comment_type VARCHAR(20) NOT NULL DEFAULT 'comment',
    comment TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT '',
    row_name VARCHAR(200) NOT NULL DEFAULT '',
    col_name VARCHAR(200) NOT NULL DEFAULT '',
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, year, module, sheet_key, row_idx, col_idx, comment_type)
);

CREATE INDEX IF NOT EXISTS ix_cc_proj_year_mod ON consol_cell_comments(project_id, year, module);
