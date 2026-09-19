-- V093: 创建 dispatch_records 表（D0-1 跨底稿分发持久化）
-- Feature: cross-workpaper-dispatch-persistence

CREATE TABLE IF NOT EXISTS dispatch_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    confirm_index VARCHAR(50) NOT NULL,
    target VARCHAR(10) NOT NULL,
    entity_name VARCHAR(255),
    account_type VARCHAR(50),
    amount NUMERIC(20,2),
    reason TEXT,
    dispatched_by UUID NOT NULL REFERENCES users(id),
    dispatched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_dispatch_dedup UNIQUE (project_id, confirm_index, target)
);

CREATE INDEX IF NOT EXISTS ix_dispatch_project_target
    ON dispatch_records(project_id, target);
