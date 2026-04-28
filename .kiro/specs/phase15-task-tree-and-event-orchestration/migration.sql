-- Phase 15 migration draft: task tree and events
BEGIN;

CREATE TABLE IF NOT EXISTS task_tree_nodes (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    node_level VARCHAR(16) NOT NULL,
    parent_id UUID NULL,
    ref_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL,
    assignee_id UUID NULL,
    due_at TIMESTAMP NULL,
    meta JSONB NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_tree_project_level
ON task_tree_nodes(project_id, node_level, status);

CREATE TABLE IF NOT EXISTS task_events (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    task_node_id UUID NULL,
    payload JSONB NOT NULL,
    status VARCHAR(16) NOT NULL,
    retry_count INT NOT NULL DEFAULT 0,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_events_project_status
ON task_events(project_id, status, created_at DESC);

COMMIT;
