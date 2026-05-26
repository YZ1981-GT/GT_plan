"""Add projects.template_version_id FK + project_workpaper_sheet_override table.

按 design §4.2 DDL ② ④：
- ② projects 表加列 template_version_id UUID FK → workpaper_template_version(id)
- ④ 新建 project_workpaper_sheet_override 表（项目级覆盖：自定义底稿/特殊归类）
  + UNIQUE (project_id, wp_code, sheet_name)
  + INDEX idx_pwpso_project_wp (project_id, wp_code)

Revision ID: project_override_template_version_20260525
Revises: wpsc_extend_fields_20260525
Create Date: 2026-05-25

Requirements: 3.0.3（项目实例层级 L5）+ 3.0.4（模板版本管理）
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

# revision identifiers
revision = "project_override_template_version_20260525"
down_revision = "wpsc_extend_fields_20260525"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── DDL ②: projects 表加列 template_version_id ───────────────────────
    op.add_column(
        "projects",
        sa.Column(
            "template_version_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("workpaper_template_version.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_projects_template_version_id",
        "projects",
        ["template_version_id"],
    )

    # ─── DDL ④: project_workpaper_sheet_override 表 ───────────────────────
    op.create_table(
        "project_workpaper_sheet_override",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("wp_code", sa.String(50), nullable=False),
        sa.Column("sheet_name", sa.String(255), nullable=False),
        sa.Column("class_override", sa.String(20), nullable=True),
        sa.Column("scope_override", sa.String(20), nullable=True),
        sa.Column("schema_override", JSONB, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "created_by",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # UNIQUE constraint
        sa.UniqueConstraint("project_id", "wp_code", "sheet_name", name="uq_pwpso_project_wp_sheet"),
    )

    # ─── INDEX: project_id + wp_code 组合查询 ─────────────────────────────
    op.create_index(
        "idx_pwpso_project_wp",
        "project_workpaper_sheet_override",
        ["project_id", "wp_code"],
    )


def downgrade() -> None:
    # ─── 删除 project_workpaper_sheet_override 表 ─────────────────────────
    op.drop_index("idx_pwpso_project_wp", table_name="project_workpaper_sheet_override")
    op.drop_table("project_workpaper_sheet_override")

    # ─── 删除 projects.template_version_id 列 ─────────────────────────────
    op.drop_index("idx_projects_template_version_id", table_name="projects")
    op.drop_column("projects", "template_version_id")
