"""010 t_accounts — T型账户表 + T型账户分录表

Revision ID: 010
Revises: 009
Create Date: 2026-04-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- t_accounts ----
    op.create_table(
        "t_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("account_code", sa.String(50), nullable=False),
        sa.Column("account_name", sa.String(200), nullable=False),
        sa.Column("account_type", sa.String(50), nullable=False),
        sa.Column("opening_balance", sa.Numeric(20, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_t_accounts_project", "t_accounts", ["project_id"])
    op.create_index("idx_t_accounts_account", "t_accounts", ["account_code"])

    # ---- t_account_entries ----
    op.create_table(
        "t_account_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("t_account_id", UUID(as_uuid=True), sa.ForeignKey("t_accounts.id"), nullable=False),
        sa.Column("entry_type", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("reference_id", UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_t_account_entries_account", "t_account_entries", ["t_account_id"])


def downgrade() -> None:
    op.drop_index("idx_t_account_entries_account", table_name="t_account_entries")
    op.drop_table("t_account_entries")
    op.drop_index("idx_t_accounts_account", table_name="t_accounts")
    op.drop_index("idx_t_accounts_project", table_name="t_accounts")
    op.drop_table("t_accounts")
