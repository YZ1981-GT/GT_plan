"""Create workpaper_sheet_version_mapping table (P1 cross-version mapping).

按 design §4.2 DDL ⑤：
- 跨版本 sheet 映射表（模板升级时 sheet 对应关系 + 字段映射 + 迁移策略）
- UNIQUE (from_version_id, to_version_id, from_wp_code, from_sheet_name)
- CHECK (migration_strategy IN ('auto_map', 'user_confirm', 'fresh_start'))

本阶段仅建表不填数据。

Revision ID: workpaper_sheet_version_mapping_20260525
Revises: project_override_template_version_20260525
Create Date: 2026-05-25

Requirements: 3.0.4（跨版本映射 P1）
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

# revision identifiers
revision = "workpaper_sheet_version_mapping_20260525"
down_revision = "project_override_template_version_20260525"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workpaper_sheet_version_mapping",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "from_version_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("workpaper_template_version.id"),
            nullable=False,
        ),
        sa.Column(
            "to_version_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("workpaper_template_version.id"),
            nullable=False,
        ),
        sa.Column("from_wp_code", sa.String(50), nullable=False),
        sa.Column("from_sheet_name", sa.String(255), nullable=False),
        sa.Column("to_wp_code", sa.String(50), nullable=True),          # NULL = 删除
        sa.Column("to_sheet_name", sa.String(255), nullable=True),
        sa.Column("field_mapping", JSONB, nullable=True),               # {"old_cell": "new_cell"}
        sa.Column(
            "migration_strategy",
            sa.String(50),
            nullable=False,
        ),
        sa.Column("notes", sa.Text, nullable=True),
        # UNIQUE constraint
        sa.UniqueConstraint(
            "from_version_id",
            "to_version_id",
            "from_wp_code",
            "from_sheet_name",
            name="uq_wsvm_version_pair_wp_sheet",
        ),
        # CHECK constraint for migration_strategy
        sa.CheckConstraint(
            "migration_strategy IN ('auto_map', 'user_confirm', 'fresh_start')",
            name="ck_wsvm_migration_strategy",
        ),
    )


def downgrade() -> None:
    op.drop_table("workpaper_sheet_version_mapping")
