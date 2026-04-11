"""005 unadjusted_misstatements 未更正错报汇总表

Revision ID: 005
Revises: 004
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 misstatement_type 枚举
    misstatement_type_enum = sa.Enum(
        "factual", "judgmental", "projected",
        name="misstatement_type",
    )
    misstatement_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "unadjusted_misstatements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("source_adjustment_id", UUID(as_uuid=True), sa.ForeignKey("adjustments.id"), nullable=True),
        sa.Column("misstatement_description", sa.Text, nullable=False),
        sa.Column("affected_account_code", sa.String, nullable=True),
        sa.Column("affected_account_name", sa.String, nullable=True),
        sa.Column("misstatement_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column(
            "misstatement_type",
            sa.Enum("factual", "judgmental", "projected", name="misstatement_type", create_type=False),
            nullable=False,
        ),
        sa.Column("management_reason", sa.Text, nullable=True),
        sa.Column("auditor_evaluation", sa.Text, nullable=True),
        sa.Column("is_carried_forward", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("prior_year_id", UUID(as_uuid=True), sa.ForeignKey("unadjusted_misstatements.id"), nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(
        "idx_unadjusted_misstatements_project_year",
        "unadjusted_misstatements",
        ["project_id", "year"],
    )
    op.create_index(
        "idx_unadjusted_misstatements_source_adj",
        "unadjusted_misstatements",
        ["source_adjustment_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_unadjusted_misstatements_source_adj", table_name="unadjusted_misstatements")
    op.drop_index("idx_unadjusted_misstatements_project_year", table_name="unadjusted_misstatements")
    op.drop_table("unadjusted_misstatements")
    sa.Enum(name="misstatement_type").drop(op.get_bind(), checkfirst=True)
