"""Create linkage_audit_log table — Sprint 4 Task 4.8

Revision ID: linkage_audit_log_20260517
Revises: workpaper_completion_cell_annotations_20260517
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers
revision = "linkage_audit_log_20260517"
down_revision = "workpaper_completion_cell_annotations_20260517"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linkage_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_uri", sa.String(512), nullable=False, comment="变更源 URI"),
        sa.Column("affected_count", sa.Integer, nullable=False, default=0, comment="受影响节点数"),
        sa.Column("duration_ms", sa.Integer, nullable=True, comment="传播耗时(ms)"),
        sa.Column("project_id", sa.String(64), nullable=True, comment="项目 ID"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    # 按项目+时间查询的索引
    op.create_index(
        "idx_linkage_audit_log_project_created",
        "linkage_audit_log",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_linkage_audit_log_project_created", table_name="linkage_audit_log")
    op.drop_table("linkage_audit_log")
