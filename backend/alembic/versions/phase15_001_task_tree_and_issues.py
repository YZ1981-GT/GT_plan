"""Phase 15: task_tree_nodes + task_events + issue_tickets + RC enhancements"""
from alembic import op

revision = 'phase15_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS task_tree_nodes (
        id UUID PRIMARY KEY, project_id UUID NOT NULL,
        node_level VARCHAR(16) NOT NULL, parent_id UUID NULL,
        ref_id UUID NOT NULL, status VARCHAR(16) NOT NULL DEFAULT 'pending',
        assignee_id UUID NULL, due_at TIMESTAMP NULL, meta JSONB NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(), updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_tree_project_level ON task_tree_nodes(project_id, node_level, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_tree_parent ON task_tree_nodes(parent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_tree_assignee ON task_tree_nodes(assignee_id, status)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS task_events (
        id UUID PRIMARY KEY, project_id UUID NOT NULL,
        event_type VARCHAR(64) NOT NULL, task_node_id UUID NULL,
        payload JSONB NOT NULL, status VARCHAR(16) NOT NULL DEFAULT 'queued',
        retry_count INT NOT NULL DEFAULT 0, max_retries INT NOT NULL DEFAULT 3,
        next_retry_at TIMESTAMP NULL, error_message TEXT NULL,
        trace_id VARCHAR(64) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_events_project_status ON task_events(project_id, status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_events_trace ON task_events(trace_id)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS issue_tickets (
        id UUID PRIMARY KEY, project_id UUID NOT NULL,
        wp_id UUID NULL, task_node_id UUID NULL, conversation_id UUID NULL,
        source VARCHAR(16) NOT NULL, severity VARCHAR(16) NOT NULL,
        category VARCHAR(64) NOT NULL, title VARCHAR(200) NOT NULL,
        description TEXT NULL, owner_id UUID NOT NULL, due_at TIMESTAMP NULL,
        entity_id UUID NULL, account_code VARCHAR(20) NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'open', thread_id UUID NULL,
        evidence_refs JSONB DEFAULT '[]'::jsonb, reason_code VARCHAR(64) NULL,
        trace_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(), updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        closed_at TIMESTAMP NULL
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_issue_tickets_project_status ON issue_tickets(project_id, status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_issue_tickets_owner ON issue_tickets(owner_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_issue_tickets_source ON issue_tickets(source, severity)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_issue_tickets_conversation ON issue_tickets(conversation_id)")

    # RC enhancements
    for col in [
        "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS priority VARCHAR(16) DEFAULT 'medium'",
        "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS sla_due_at TIMESTAMP NULL",
        "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP NULL",
        "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolved_by UUID NULL",
        "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolution_code VARCHAR(64) NULL",
        "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64) NULL",
        "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS reply_to UUID NULL",
        "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS mentions JSONB DEFAULT '[]'::jsonb",
        "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP NULL",
        "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS redaction_flag BOOLEAN DEFAULT false",
        "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS message_version INTEGER DEFAULT 1",
        "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64) NULL",
        "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS reason_code VARCHAR(64) NULL",
    ]:
        op.execute(col)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS issue_tickets")
    op.execute("DROP TABLE IF EXISTS task_events")
    op.execute("DROP TABLE IF EXISTS task_tree_nodes")
