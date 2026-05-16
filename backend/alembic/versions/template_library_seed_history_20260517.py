"""Sprint 1 Task 1.4: 新增 seed_load_history 表（template-library-coordination）

记录每次 seed 加载的审计轨迹（seed_name / loaded_at / loaded_by / 计数 / 错误 / 状态）。

Revision ID: template_library_seed_history_20260517
Revises: audit_chain_sprint10_tables_20260516
Create Date: 2026-05-17

Requirements: 13.6, 14.3 (template-library-coordination)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "template_library_seed_history_20260517"
down_revision = "audit_chain_sprint10_tables_20260516"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seed_load_history",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("seed_name", sa.String(100), nullable=False),
        sa.Column(
            "loaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "loaded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("record_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("inserted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="loaded",
        ),
    )
    op.create_index(
        "idx_seed_load_history_name",
        "seed_load_history",
        ["seed_name", sa.text("loaded_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_seed_load_history_name", table_name="seed_load_history")
    op.drop_table("seed_load_history")
