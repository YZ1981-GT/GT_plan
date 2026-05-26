"""Create workpaper_template_version table + seed initial v2025-R5 record.

按 design §4.2 DDL ① 创建模板版本表，支持多版本共存。
插入初始版本记录 v2025-R5（is_current=TRUE）。
创建 partial unique index 保证同一时刻只有一个 is_current=TRUE 的版本。

Revision ID: wp_template_version_20260525
Revises: view_refactor_retention_class_20260526
Create Date: 2026-05-25

Requirements: 3.0.4（模板版本管理）
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers
revision = "wp_template_version_20260525"
down_revision = "view_refactor_retention_class_20260526"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── DDL: Create workpaper_template_version table ────────────────────
    op.create_table(
        "workpaper_template_version",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version", sa.String(20), nullable=False, unique=True),
        sa.Column("release_date", sa.Date, nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default=sa.text("'致同总所'")),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "parent_version_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("workpaper_template_version.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("changelog", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(is_current = FALSE) OR (is_current = TRUE)",
            name="chk_only_one_current",
        ),
    )

    # ─── Partial unique index: 保证同一时刻只有一个 is_current=TRUE ──────
    op.create_index(
        "uq_workpaper_template_version_current",
        "workpaper_template_version",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current = TRUE"),
    )

    # ─── Seed: 插入初始版本 v2025-R5 ────────────────────────────────────
    table = sa.table(
        "workpaper_template_version",
        sa.column("version", sa.String),
        sa.column("release_date", sa.Date),
        sa.column("source", sa.String),
        sa.column("is_current", sa.Boolean),
        sa.column("changelog", sa.Text),
    )
    op.bulk_insert(table, [
        {
            "version": "v2025-R5",
            "release_date": "2025-01-01",
            "source": "致同总所",
            "is_current": True,
            "changelog": "致同 2025 修订版第 5 次发布，覆盖 D/F/K/N 循环 206 条底稿编码",
        },
    ])


def downgrade() -> None:
    op.drop_index("uq_workpaper_template_version_current", table_name="workpaper_template_version")
    op.drop_table("workpaper_template_version")
