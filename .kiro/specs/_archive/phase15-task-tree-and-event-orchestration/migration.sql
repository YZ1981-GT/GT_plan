-- Phase 15 migration: task tree + events + issue tickets + RC enhancements
-- 对齐 v2 4.5.15A + 5.9.16
BEGIN;

-- 四级任务树节点
CREATE TABLE IF NOT EXISTS task_tree_nodes (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    node_level VARCHAR(16) NOT NULL,   -- unit/account/workpaper/evidence
    parent_id UUID NULL,
    ref_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL,        -- pending/in_progress/blocked/done
    assignee_id UUID NULL,
    due_at TIMESTAMP NULL,
    meta JSONB NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_tree_project_level
ON task_tree_nodes(project_id, node_level, status);

CREATE INDEX IF NOT EXISTS idx_task_tree_parent
ON task_tree_nodes(parent_id);

CREATE INDEX IF NOT EXISTS idx_task_tree_assignee
ON task_tree_nodes(assignee_id, status);

-- 事件总线与补偿队列
CREATE TABLE IF NOT EXISTS task_events (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    event_type VARCHAR(64) NOT NULL,    -- trim_applied/trim_rollback/task_reassigned/issue_escalated/...
    task_node_id UUID NULL,
    payload JSONB NOT NULL,
    status VARCHAR(16) NOT NULL,        -- queued/replaying/succeeded/failed/dead_letter
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    next_retry_at TIMESTAMP NULL,       -- 下次重试时间（指数退避 1m->5m->15m）
    error_message TEXT NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_events_project_status
ON task_events(project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_task_events_trace
ON task_events(trace_id);

CREATE INDEX IF NOT EXISTS idx_task_events_dead_letter
ON task_events(status) WHERE status = 'dead_letter';

-- 统一问题单（对齐 v2 4.5.15A）
CREATE TABLE IF NOT EXISTS issue_tickets (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    wp_id UUID NULL,
    task_node_id UUID NULL,
    conversation_id UUID NULL,
    source VARCHAR(16) NOT NULL,         -- L2/L3/Q
    severity VARCHAR(16) NOT NULL,       -- blocker/major/minor/suggestion
    category VARCHAR(64) NOT NULL,       -- data_mismatch/evidence_missing/explanation_incomplete/procedure_incomplete/policy_violation
    title VARCHAR(200) NOT NULL,
    description TEXT,
    owner_id UUID NOT NULL,
    due_at TIMESTAMP NULL,
    entity_id UUID NULL,
    account_code VARCHAR(20) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',  -- open/in_fix/pending_recheck/closed/rejected
    thread_id UUID NULL,
    evidence_refs JSONB DEFAULT '[]'::jsonb,
    reason_code VARCHAR(64) NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_issue_tickets_project_status
ON issue_tickets(project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_issue_tickets_owner
ON issue_tickets(owner_id, status);

CREATE INDEX IF NOT EXISTS idx_issue_tickets_source
ON issue_tickets(source, severity);

CREATE INDEX IF NOT EXISTS idx_issue_tickets_conversation
ON issue_tickets(conversation_id);

-- RC 会话表增强（对齐 v2 5.9.16.4）
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS priority VARCHAR(16) NOT NULL DEFAULT 'medium';
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS sla_due_at TIMESTAMP NULL;
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP NULL;
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolved_by UUID NULL;
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolution_code VARCHAR(64) NULL;
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64) NULL;

CREATE INDEX IF NOT EXISTS idx_rc_project_status ON review_conversations(project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rc_project_sla ON review_conversations(project_id, sla_due_at);
CREATE INDEX IF NOT EXISTS idx_rc_trace ON review_conversations(trace_id);

-- RC 消息表增强（对齐 v2 5.9.16.3）
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS reply_to UUID NULL;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS mentions JSONB NULL DEFAULT '[]'::jsonb;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP NULL;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS redaction_flag BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS message_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64) NULL;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS reason_code VARCHAR(64) NULL;

CREATE INDEX IF NOT EXISTS idx_rm_conversation_created ON review_messages(conversation_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_rm_sender_created ON review_messages(sender_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rm_reply_to ON review_messages(reply_to);
CREATE INDEX IF NOT EXISTS idx_rm_trace ON review_messages(trace_id);

-- RC 参与者表（对齐 v2 5.9.16.1）
CREATE TABLE IF NOT EXISTS review_conversation_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL,
    user_id UUID NOT NULL,
    participant_role VARCHAR(32) NOT NULL,  -- initiator/target/reviewer/observer
    is_required_ack BOOLEAN NOT NULL DEFAULT false,
    joined_at TIMESTAMP NOT NULL DEFAULT NOW(),
    left_at TIMESTAMP NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (conversation_id, user_id, is_deleted)
);

CREATE INDEX IF NOT EXISTS idx_rcp_conversation ON review_conversation_participants(conversation_id);
CREATE INDEX IF NOT EXISTS idx_rcp_user ON review_conversation_participants(user_id);
CREATE INDEX IF NOT EXISTS idx_rcp_required_ack ON review_conversation_participants(conversation_id, is_required_ack);

-- RC 导出留痕表（对齐 v2 5.9.16.2）
CREATE TABLE IF NOT EXISTS review_conversation_exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    export_id VARCHAR(64) NOT NULL UNIQUE,
    conversation_id UUID NOT NULL,
    project_id UUID NOT NULL,
    requested_by UUID NOT NULL,
    export_scope VARCHAR(32) NOT NULL,   -- full_timeline/summary/attachments_only
    purpose VARCHAR(200) NOT NULL,
    receiver VARCHAR(200) NOT NULL,
    mask_policy VARCHAR(64) NOT NULL,
    include_hash_manifest BOOLEAN NOT NULL DEFAULT true,
    file_path TEXT NULL,
    file_hash VARCHAR(128) NULL,
    trace_id VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'created',  -- created/ready/failed
    error_code VARCHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_rce_conversation ON review_conversation_exports(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rce_project ON review_conversation_exports(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rce_trace ON review_conversation_exports(trace_id);

COMMIT;
