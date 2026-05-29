-- V021: Add row_ref column to attachment_working_paper for row-level attachment binding
-- Supports US-4: 底稿证据链 → 附件模块打通（行级绑定）

ALTER TABLE attachment_working_paper ADD COLUMN IF NOT EXISTS row_ref VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_awp_row_ref ON attachment_working_paper(wp_id, row_ref);
