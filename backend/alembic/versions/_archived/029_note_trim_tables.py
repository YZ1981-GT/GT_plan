"""Phase 9 Task 9.27: note_section_instances + note_trim_schemes

Revision ID: 022
Revises: 021
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note_section_instances",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("template_type", sa.String(20), nullable=False),
        sa.Column("section_number", sa.String(20), nullable=False),
        sa.Column("section_title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'retain'")),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0")),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_note_section_project", "note_section_instances",
                    ["project_id", "template_type"],
                    postgresql_where=sa.text("is_deleted = false"))

    op.create_table(
        "note_trim_schemes",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("template_type", sa.String(20), nullable=False),
        sa.Column("scheme_name", sa.String(200), nullable=False),
        sa.Column("trim_data", JSONB, nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("note_trim_schemes")
    op.drop_table("note_section_instances")
