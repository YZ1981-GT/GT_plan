-- V095: 复核对话线程 + 消息表
-- 支持审计复核对话组件 (GtReviewDialog)，每个底稿区域一个线程

-- 1. review_threads 表（新建）
CREATE TABLE IF NOT EXISTS review_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_id UUID NOT NULL REFERENCES working_paper(id),
    section_id VARCHAR(50) NOT NULL,
    thread_key VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uix_review_threads_thread_key
    ON review_threads(thread_key);

CREATE INDEX IF NOT EXISTS ix_review_threads_wp_id
    ON review_threads(wp_id);

-- 2. review_messages 表：旧表已存在且列结构不同（conversation_id 而非 thread_id）
--    添加 thread_id 列（如果不存在），保留旧列兼容
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'review_messages' AND column_name = 'thread_id'
    ) THEN
        ALTER TABLE review_messages ADD COLUMN thread_id UUID REFERENCES review_threads(id) ON DELETE CASCADE;
    END IF;
END $$;

-- 补充缺失列
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'review_messages' AND column_name = 'sender_role'
    ) THEN
        ALTER TABLE review_messages ADD COLUMN sender_role VARCHAR(50) NOT NULL DEFAULT 'assistant';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_review_messages_thread_id
    ON review_messages(thread_id);

CREATE INDEX IF NOT EXISTS ix_review_messages_created_at
    ON review_messages(thread_id, created_at);
