-- V029: 附件入网 — attachment_lineage 表
-- wp-traceability-panel Task 2.1
-- 将附件关联到具体位置（wp_cell / report_row / note_section），使附件进入溯源网络

CREATE TABLE IF NOT EXISTS attachment_lineage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attachment_id UUID NOT NULL,
    target_type VARCHAR(50) NOT NULL,   -- wp_cell / report_row / note_section
    target_id UUID,                      -- 关联对象的 UUID（可选）
    target_ref VARCHAR(200),             -- 精确位置引用，如 "D2-3!B5"
    created_at TIMESTAMP DEFAULT now()
);

-- 注意：attachment_id 逻辑关联 attachments 表，但不加 FK 约束
-- （attachments 表结构可能变化，且 attachment_id 也可能来自其他附件存储）

-- 索引：按 attachment_id 查询
CREATE INDEX IF NOT EXISTS idx_attachment_lineage_attachment_id
    ON attachment_lineage(attachment_id);

-- 索引：按 target_type + target_ref 查询（溯源查询主路径）
CREATE INDEX IF NOT EXISTS idx_attachment_lineage_target
    ON attachment_lineage(target_type, target_ref);

-- 索引：按 target_id 查询
CREATE INDEX IF NOT EXISTS idx_attachment_lineage_target_id
    ON attachment_lineage(target_id);
