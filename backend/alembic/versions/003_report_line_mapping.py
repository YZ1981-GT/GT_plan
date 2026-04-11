"""报表行次映射表 report_line_mapping

Revision ID: 003
Revises: 002
Create Date: 2025-01-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. 创建 PostgreSQL 枚举类型
    # ------------------------------------------------------------------
    report_type = postgresql.ENUM(
        "balance_sheet", "income_statement", "cash_flow",
        name="report_type",
        create_type=True,
    )
    report_type.create(op.get_bind(), checkfirst=True)

    report_line_mapping_type = postgresql.ENUM(
        "ai_suggested", "manual", "reference_copied",
        name="report_line_mapping_type",
        create_type=True,
    )
    report_line_mapping_type.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 2. 创建 report_line_mapping 表
    # ------------------------------------------------------------------
    op.create_table(
        "report_line_mapping",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("standard_account_code", sa.String(), nullable=False),
        sa.Column(
            "report_type",
            postgresql.ENUM(name="report_type", create_type=False),
            nullable=False,
        ),
        sa.Column("report_line_code", sa.String(), nullable=False),
        sa.Column("report_line_name", sa.String(), nullable=False),
        sa.Column("report_line_level", sa.Integer(), nullable=False),
        sa.Column("parent_line_code", sa.String(), nullable=True),
        sa.Column(
            "mapping_type",
            postgresql.ENUM(name="report_line_mapping_type", create_type=False),
            nullable=False,
        ),
        sa.Column("is_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 3. 创建复合索引
    # ------------------------------------------------------------------
    op.create_index(
        "idx_report_line_mapping_project_type_account",
        "report_line_mapping",
        ["project_id", "report_type", "standard_account_code"],
    )


def downgrade() -> None:
    op.drop_index("idx_report_line_mapping_project_type_account", table_name="report_line_mapping")
    op.drop_table("report_line_mapping")
    postgresql.ENUM(name="report_line_mapping_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="report_type").drop(op.get_bind(), checkfirst=True)
