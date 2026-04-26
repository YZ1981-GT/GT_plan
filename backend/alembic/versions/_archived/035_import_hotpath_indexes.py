"""Add hot-path indexes for large import cleanup and rollback.

Revision ID: 035
Revises: 034
Create Date: 2026-04-26
"""

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # Speeds up rollback_import(batch_id) on all four tables.
    op.create_index("idx_tb_balance_import_batch", "tb_balance", ["import_batch_id"])
    op.create_index("idx_tb_ledger_import_batch", "tb_ledger", ["import_batch_id"])
    op.create_index("idx_tb_aux_balance_import_batch", "tb_aux_balance", ["import_batch_id"])
    op.create_index("idx_tb_aux_ledger_import_batch", "tb_aux_ledger", ["import_batch_id"])

    # Speeds up same-year overwrite soft-delete path (project_id + year + is_deleted).
    op.create_index(
        "idx_tb_ledger_project_year_deleted",
        "tb_ledger",
        ["project_id", "year", "is_deleted"],
    )
    op.create_index(
        "idx_tb_aux_balance_project_year_deleted",
        "tb_aux_balance",
        ["project_id", "year", "is_deleted"],
    )
    op.create_index(
        "idx_tb_aux_ledger_project_year_deleted",
        "tb_aux_ledger",
        ["project_id", "year", "is_deleted"],
    )


def downgrade() -> None:
    op.drop_index("idx_tb_aux_ledger_project_year_deleted", table_name="tb_aux_ledger")
    op.drop_index("idx_tb_aux_balance_project_year_deleted", table_name="tb_aux_balance")
    op.drop_index("idx_tb_ledger_project_year_deleted", table_name="tb_ledger")

    op.drop_index("idx_tb_aux_ledger_import_batch", table_name="tb_aux_ledger")
    op.drop_index("idx_tb_aux_balance_import_batch", table_name="tb_aux_balance")
    op.drop_index("idx_tb_ledger_import_batch", table_name="tb_ledger")
    op.drop_index("idx_tb_balance_import_batch", table_name="tb_balance")
