"""Phase 17: attach imported ledger rows to dataset versions

Revision ID: phase17_002
Revises: phase17_001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "phase17_002"
down_revision = "phase17_001"
branch_labels = None
depends_on = None


_TABLES_WITH_YEAR = (
    "tb_balance",
    "tb_ledger",
    "tb_aux_balance",
    "tb_aux_ledger",
)


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    for table_name in _TABLES_WITH_YEAR:
        if not _has_column(table_name, "dataset_id"):
            op.add_column(table_name, sa.Column("dataset_id", UUID(as_uuid=True), nullable=True))
        index_name = f"idx_{table_name}_project_year_dataset_deleted"
        if not _has_index(table_name, index_name):
            op.create_index(
                index_name,
                table_name,
                ["project_id", "year", "dataset_id", "is_deleted"],
            )

    if not _has_column("account_chart", "dataset_id"):
        op.add_column("account_chart", sa.Column("dataset_id", UUID(as_uuid=True), nullable=True))
    if not _has_index("account_chart", "idx_account_chart_project_dataset_deleted"):
        op.create_index(
            "idx_account_chart_project_dataset_deleted",
            "account_chart",
            ["project_id", "dataset_id", "is_deleted"],
        )
    if not _has_index("ledger_datasets", "uq_ledger_datasets_one_active"):
        op.create_index(
            "uq_ledger_datasets_one_active",
            "ledger_datasets",
            ["project_id", "year"],
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
        )


def downgrade() -> None:
    if _has_index("ledger_datasets", "uq_ledger_datasets_one_active"):
        op.drop_index("uq_ledger_datasets_one_active", table_name="ledger_datasets")
    if _has_index("account_chart", "idx_account_chart_project_dataset_deleted"):
        op.drop_index("idx_account_chart_project_dataset_deleted", table_name="account_chart")
    if _has_column("account_chart", "dataset_id"):
        op.drop_column("account_chart", "dataset_id")

    for table_name in reversed(_TABLES_WITH_YEAR):
        index_name = f"idx_{table_name}_project_year_dataset_deleted"
        if _has_index(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if _has_column(table_name, "dataset_id"):
            op.drop_column(table_name, "dataset_id")
