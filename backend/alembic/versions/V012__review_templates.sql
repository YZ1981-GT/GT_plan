-- V012: 新增 review_templates 表
-- Phase 7 F4: 复核意见模板库

CREATE TABLE IF NOT EXISTS review_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    applicable_cycles JSONB NOT NULL DEFAULT '[]',
    priority_tag VARCHAR(20) NOT NULL DEFAULT 'suggest',
    use_count INTEGER NOT NULL DEFAULT 0,
    created_by UUID REFERENCES users(id),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_templates_priority
ON review_templates (priority_tag)
WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_review_templates_cycles_gin
ON review_templates USING GIN (applicable_cycles);

COMMENT ON TABLE review_templates IS '复核意见模板库';
