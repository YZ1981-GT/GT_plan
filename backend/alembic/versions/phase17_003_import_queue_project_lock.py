"""Phase 17: enforce one active smart import per project

Revision ID: phase17_003
Revises: phase17_002
"""

from alembic import op
import sqlalchemy as sa


revision = "phase17_003"
down_revision = "phase17_002"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_import_batches_one_processing_smart_job"


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _has_index("import_batches", INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            "import_batches",
            ["project_id"],
            unique=True,
            postgresql_where=sa.text("data_type = '__smart_import_job__' AND status = 'processing'"),
            sqlite_where=sa.text("data_type = '__smart_import_job__' AND status = 'processing'"),
        )


def downgrade() -> None:
    if _has_index("import_batches", INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="import_batches")
