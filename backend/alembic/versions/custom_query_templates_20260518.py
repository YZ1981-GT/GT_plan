"""Sprint 6 Task 6.6: 新增 custom_query_templates 表（template-library-coordination）

支持自定义查询的模板保存（私有/全局共享）。

Revision ID: custom_query_templates_20260518
Revises: template_library_seed_history_20260517
Create Date: 2026-05-18

Requirements: 22.7, 22.8 (template-library-coordination)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "custom_query_templates_20260518"
down_revision = "template_library_seed_history_20260517"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_query_templates",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("data_source", sa.String(50), nullable=False),
        sa.Column("config", JSONB, nullable=False),
        sa.Column(
            "scope",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'private'"),
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_custom_query_templates_scope",
        "custom_query_templates",
        ["scope", "updated_at"],
    )
    op.create_index(
        "idx_custom_query_templates_creator",
        "custom_query_templates",
        ["created_by", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_custom_query_templates_creator",
        table_name="custom_query_templates",
    )
    op.drop_index(
        "idx_custom_query_templates_scope",
        table_name="custom_query_templates",
    )
    op.drop_table("custom_query_templates")
