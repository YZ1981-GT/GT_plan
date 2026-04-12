"""004 adjustment_entries 明细行表

Revision ID: 004
Revises: 003
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adjustment_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("adjustment_id", UUID(as_uuid=True), sa.ForeignKey("adjustments.id"), nullable=False),
        sa.Column("entry_group_id", UUID(as_uuid=True), nullable=False),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("standard_account_code", sa.String, nullable=False),
        sa.Column("account_name", sa.String, nullable=True),
        sa.Column("report_line_code", sa.String, nullable=True),
        sa.Column("debit_amount", sa.Numeric(20, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("credit_amount", sa.Numeric(20, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_adjustment_entries_adjustment_id", "adjustment_entries", ["adjustment_id"])
    op.create_index("idx_adjustment_entries_entry_group_id", "adjustment_entries", ["entry_group_id"])


def downgrade() -> None:
    op.drop_index("idx_adjustment_entries_entry_group_id", table_name="adjustment_entries")
    op.drop_index("idx_adjustment_entries_adjustment_id", table_name="adjustment_entries")
    op.drop_table("adjustment_entries")
