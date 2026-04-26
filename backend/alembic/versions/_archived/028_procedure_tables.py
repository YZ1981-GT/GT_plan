"""Phase 9 Task 9.12: procedure_instances + procedure_trim_schemes

Revision ID: 021
Revises: 020
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procedure_instances",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("audit_cycle", sa.String(10), nullable=False),
        sa.Column("procedure_code", sa.String(50), nullable=False),
        sa.Column("procedure_name", sa.String(500), nullable=False),
        sa.Column("parent_id", sa.UUID(), sa.ForeignKey("procedure_instances.id"), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0")),
        sa.Column("status", sa.String(20), server_default=sa.text("'execute'")),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("is_custom", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("assigned_to", sa.UUID(), sa.ForeignKey("staff_members.id"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=True),
        sa.Column("execution_status", sa.String(20), server_default=sa.text("'not_started'")),
        sa.Column("wp_code", sa.String(50), nullable=True),
        sa.Column("wp_id", sa.UUID(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_proc_project_cycle", "procedure_instances",
                    ["project_id", "audit_cycle"],
                    postgresql_where=sa.text("is_deleted = false"))

    op.create_table(
        "procedure_trim_schemes",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("audit_cycle", sa.String(10), nullable=False),
        sa.Column("scheme_name", sa.String(200), nullable=False),
        sa.Column("trim_data", JSONB, nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # working_paper 表新增 parsed_data 和 prefill_stale 列
    op.add_column("working_paper", sa.Column("parsed_data", JSONB, nullable=True))
    op.add_column("working_paper", sa.Column("prefill_stale", sa.Boolean(), server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("working_paper", "prefill_stale")
    op.drop_column("working_paper", "parsed_data")
    op.drop_table("procedure_trim_schemes")
    op.drop_table("procedure_instances")
