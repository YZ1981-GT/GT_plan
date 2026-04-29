"""Phase 15: review_conversation_participants + review_conversation_exports"""
from alembic import op

revision = 'phase15_002'
down_revision = 'phase15_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS review_conversation_participants (
        id UUID PRIMARY KEY,
        conversation_id UUID NOT NULL,
        user_id UUID NOT NULL,
        participant_role VARCHAR(32) NOT NULL DEFAULT 'viewer',
        is_required_ack BOOLEAN NOT NULL DEFAULT false,
        joined_at TIMESTAMP NOT NULL DEFAULT NOW(),
        left_at TIMESTAMP NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_rc_participants_conv ON review_conversation_participants(conversation_id, is_deleted)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_rc_participants_user ON review_conversation_participants(user_id, is_deleted)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS review_conversation_exports (
        id UUID PRIMARY KEY,
        export_id VARCHAR(64) NOT NULL UNIQUE,
        conversation_id UUID NOT NULL,
        project_id UUID NOT NULL,
        requested_by UUID NOT NULL,
        export_scope VARCHAR(32) NOT NULL DEFAULT 'full_timeline',
        purpose TEXT NOT NULL,
        receiver VARCHAR(200) NOT NULL,
        mask_policy VARCHAR(32) NOT NULL DEFAULT 'none',
        include_hash_manifest BOOLEAN NOT NULL DEFAULT false,
        file_hash VARCHAR(64) NULL,
        trace_id VARCHAR(64) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'ready',
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_rc_exports_conv ON review_conversation_exports(conversation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_rc_exports_project ON review_conversation_exports(project_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_conversation_exports")
    op.execute("DROP TABLE IF EXISTS review_conversation_participants")
