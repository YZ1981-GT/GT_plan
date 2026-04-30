"""Phase 17: add import event outbox

Revision ID: phase17_004
Revises: phase17_003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "phase17_004"
down_revision = "phase17_003"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("import_event_outbox"):
        return

    op.create_table(
        "import_event_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.Enum("pending", "published", "failed", name="import_event_outbox_status"), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_import_event_outbox_status", "import_event_outbox", ["status", "created_at"])
    op.create_index("idx_import_event_outbox_project_year", "import_event_outbox", ["project_id", "year"])


def downgrade() -> None:
    if not _has_table("import_event_outbox"):
        return
    op.drop_index("idx_import_event_outbox_project_year", table_name="import_event_outbox")
    op.drop_index("idx_import_event_outbox_status", table_name="import_event_outbox")
    op.drop_table("import_event_outbox")
    op.execute("DROP TYPE IF EXISTS import_event_outbox_status")
