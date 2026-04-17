"""Phase 10: report_format_templates + projects fields + adjustments.is_continuous

Revision ID: 025
Revises: 024
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- report_format_templates ---
    op.create_table(
        "report_format_templates",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("template_name", sa.String(200), nullable=False),
        sa.Column("template_type", sa.String(50), nullable=False),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1")),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # --- projects 新增字段 ---
    op.add_column("projects", sa.Column(
        "prior_year_project_id", PG_UUID(as_uuid=True), nullable=True))
    op.add_column("projects", sa.Column(
        "consol_lock", sa.Boolean(), server_default=sa.text("false")))
    op.add_column("projects", sa.Column(
        "consol_lock_by", PG_UUID(as_uuid=True), nullable=True))
    op.add_column("projects", sa.Column(
        "consol_lock_at", sa.DateTime(), nullable=True))
    op.add_column("projects", sa.Column(
        "auto_created", sa.Boolean(), server_default=sa.text("false")))

    # --- adjustments 新增字段 ---
    op.add_column("adjustments", sa.Column(
        "is_continuous", sa.Boolean(), server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("adjustments", "is_continuous")
    op.drop_column("projects", "auto_created")
    op.drop_column("projects", "consol_lock_at")
    op.drop_column("projects", "consol_lock_by")
    op.drop_column("projects", "consol_lock")
    op.drop_column("projects", "prior_year_project_id")
    op.drop_table("report_format_templates")
