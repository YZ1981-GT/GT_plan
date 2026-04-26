"""009 gt_wp_coding — 致同底稿编码体系表

Revision ID: 009
Revises: 008
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
    # ---- 枚举类型 ----
    wp_type_enum = sa.Enum(
        "preliminary", "risk_assessment", "control_test",
        "substantive", "completion", "specific", "general", "permanent",
        name="gt_wp_type",
    )
    wp_type_enum.create(op.get_bind(), checkfirst=True)

    # ---- gt_wp_coding 表 ----
    op.create_table(
        "gt_wp_coding",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code_prefix", sa.String, nullable=False),
        sa.Column("code_range", sa.String, nullable=False),
        sa.Column("cycle_name", sa.String, nullable=False),
        sa.Column(
            "wp_type",
            sa.Enum(
                "preliminary", "risk_assessment", "control_test",
                "substantive", "completion", "specific", "general", "permanent",
                name="gt_wp_type", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("parent_cycle", sa.String, nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_gt_wp_coding_prefix", "gt_wp_coding", ["code_prefix"])
    op.create_index("idx_gt_wp_coding_type", "gt_wp_coding", ["wp_type"])
    op.create_index("idx_gt_wp_coding_active", "gt_wp_coding", ["is_active"])


def downgrade() -> None:
    op.drop_index("idx_gt_wp_coding_active", table_name="gt_wp_coding")
    op.drop_index("idx_gt_wp_coding_type", table_name="gt_wp_coding")
    op.drop_index("idx_gt_wp_coding_prefix", table_name="gt_wp_coding")
    op.drop_table("gt_wp_coding")
    sa.Enum(name="gt_wp_type").drop(op.get_bind(), checkfirst=True)
