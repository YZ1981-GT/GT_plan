"""Phase 14: trace_events + gate_decisions tables

对齐 v2 5.9.3 D-01/D-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'phase14_001'
down_revision = None  # 独立迁移，不依赖 Alembic 链
branch_labels = None
depends_on = None


def upgrade() -> None:
    # trace_events
    op.execute("""
    CREATE TABLE IF NOT EXISTS trace_events (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        object_type VARCHAR(32) NOT NULL,
        object_id UUID NOT NULL,
        actor_id UUID NOT NULL,
        actor_role VARCHAR(32),
        action VARCHAR(100) NOT NULL,
        decision VARCHAR(16),
        reason_code VARCHAR(64),
        from_status VARCHAR(32),
        to_status VARCHAR(32),
        before_snapshot JSONB,
        after_snapshot JSONB,
        content_hash VARCHAR(64),
        version_no INTEGER,
        trace_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_trace_events_project ON trace_events(project_id, event_type, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trace_events_object ON trace_events(object_type, object_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trace_events_trace_id ON trace_events(trace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trace_events_actor ON trace_events(actor_id, created_at DESC)")

    # gate_decisions
    op.execute("""
    CREATE TABLE IF NOT EXISTS gate_decisions (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL,
        wp_id UUID,
        gate_type VARCHAR(32) NOT NULL,
        decision VARCHAR(16) NOT NULL,
        hit_rules JSONB NOT NULL,
        actor_id UUID NOT NULL,
        trace_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_gate_decisions_project_gate ON gate_decisions(project_id, gate_type, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_gate_decisions_trace ON gate_decisions(trace_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gate_decisions")
    op.execute("DROP TABLE IF EXISTS trace_events")
