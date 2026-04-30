"""Phase 17: add import event consumption dedup table

Revision ID: phase17_005
Revises: phase17_004
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "phase17_005"
down_revision = "phase17_004"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("import_event_consumptions"):
        return

    op.create_table(
        "import_event_consumptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("handler_name", sa.String(length=200), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "uq_import_event_consumptions_event_handler",
        "import_event_consumptions",
        ["event_id", "handler_name"],
        unique=True,
    )
    op.create_index(
        "idx_import_event_consumptions_project_year",
        "import_event_consumptions",
        ["project_id", "year"],
    )


def downgrade() -> None:
    if not _has_table("import_event_consumptions"):
        return
    op.drop_index("idx_import_event_consumptions_project_year", table_name="import_event_consumptions")
    op.drop_index("uq_import_event_consumptions_event_handler", table_name="import_event_consumptions")
    op.drop_table("import_event_consumptions")
