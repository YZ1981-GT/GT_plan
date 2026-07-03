-- V095: 复核对话线程 + 消息表
-- 支持审计复核对话组件 (GtReviewDialog)，每个底稿区域一个线程

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

CREATE TABLE IF NOT EXISTS review_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES review_threads(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES users(id),
    sender_role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    message_type VARCHAR(20) NOT NULL DEFAULT 'text',
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_review_messages_thread_id
    ON review_messages(thread_id);

CREATE INDEX IF NOT EXISTS ix_review_messages_created_at
    ON review_messages(thread_id, created_at);
