-- 复核对话关联 A21~A25 检查要点
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS checklist_ref VARCHAR(20);

COMMENT ON COLUMN review_conversations.checklist_ref IS '关联复核检查项（如 A22-1:5 表示A22-1模板第5项）';

CREATE INDEX IF NOT EXISTS idx_review_conversations_checklist_ref
    ON review_conversations(checklist_ref) WHERE checklist_ref IS NOT NULL;
