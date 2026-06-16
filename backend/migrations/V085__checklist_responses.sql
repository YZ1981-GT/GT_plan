-- V085: 核对表填写响应表（checklist_responses）
-- 存储用户对 A1-15/A1-16 核对表条目的填写数据（Y/N/NA + 备注 + 底稿索引）
-- 章节适用性也存于此表，使用特殊 item_id 前缀 TOC-S01, TOC-S02 等

CREATE TABLE IF NOT EXISTS checklist_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_id UUID NOT NULL REFERENCES working_paper(id),
    item_id VARCHAR(20) NOT NULL,       -- 如 "S01-001" 或 "TOC-S01"(章节适用性)
    conclusion VARCHAR(5),              -- 'Y'/'N'/'NA'/null
    remark TEXT,
    wp_ref VARCHAR(100),                -- 底稿索引引用
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(wp_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_checklist_resp_project ON checklist_responses(project_id);
CREATE INDEX IF NOT EXISTS idx_checklist_resp_wp ON checklist_responses(wp_id);
