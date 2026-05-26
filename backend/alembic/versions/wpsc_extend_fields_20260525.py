"""Extend workpaper_sheet_classification table with 9 new columns + 3 indexes.

按 design §4.2 DDL ③ 扩展 workpaper_sheet_classification 表：
- class: A-/B-/C-/D-/E-/F-/G-/H-/I- 子类
- is_real_workpaper: 是否真底稿
- exclude_from_archive: 不归档
- exclude_from_progress: 不计入完成率
- is_static_doc: 静态文档
- scope: standalone/consolidated/parent_only/both
- delegated_module: 委派模块
- template_version_id: FK → workpaper_template_version
- render_schema_path: YAML schema 路径

索引：
- idx_wpsc_class_scope (class, scope)
- idx_wpsc_template_version_real (template_version_id, is_real_workpaper) WHERE is_real_workpaper = TRUE
- idx_wpsc_wp_code_version (wp_code, template_version_id)

Revision ID: wpsc_extend_fields_20260525
Revises: wp_template_version_20260525
Create Date: 2026-05-25

Requirements: 3.0.2（真假底稿）+ 3.0.5（合并剔除 scope）
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers
revision = "wpsc_extend_fields_20260525"
down_revision = "wp_template_version_20260525"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── 确保基表存在（wp_code / sheet_name / class_code 三列） ──────────
    # 如果表已存在则跳过创建（幂等）
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_name = 'workpaper_sheet_classification'"
            ")"
        )
    )
    table_exists = result.scalar()

    if not table_exists:
        op.create_table(
            "workpaper_sheet_classification",
            sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("wp_code", sa.String(50), nullable=False),
            sa.Column("sheet_name", sa.String(255), nullable=False),
            sa.Column("class_code", sa.String(20), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_unique_constraint(
            "uq_wpsc_wp_code_sheet_name",
            "workpaper_sheet_classification",
            ["wp_code", "sheet_name"],
        )

    # ─── DDL ③: 添加 9 个新列 ────────────────────────────────────────────
    op.add_column(
        "workpaper_sheet_classification",
        sa.Column("class", sa.String(20), nullable=True),
    )
    op.add_column(
        "workpaper_sheet_classification",
        sa.Column("is_real_workpaper", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "workpaper_sheet_classification",
        sa.Column("exclude_from_archive", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "workpaper_sheet_classification",
        sa.Column("exclude_from_progress", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "workpaper_sheet_classification",
        sa.Column("is_static_doc", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "workpaper_sheet_classification",
        sa.Column(
            "scope",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'standalone'"),
        ),
    )
    op.add_column(
        "workpaper_sheet_classification",
        sa.Column("delegated_module", sa.String(50), nullable=True),
    )
    op.add_column(
        "workpaper_sheet_classification",
        sa.Column(
            "template_version_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("workpaper_template_version.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "workpaper_sheet_classification",
        sa.Column("render_schema_path", sa.String(255), nullable=True),
    )

    # ─── CHECK constraint: scope 枚举 ────────────────────────────────────
    op.create_check_constraint(
        "chk_wpsc_scope_values",
        "workpaper_sheet_classification",
        "scope IN ('standalone', 'consolidated', 'parent_only', 'both')",
    )

    # ─── 索引 ────────────────────────────────────────────────────────────
    op.create_index(
        "idx_wpsc_class_scope",
        "workpaper_sheet_classification",
        ["class", "scope"],
    )
    op.create_index(
        "idx_wpsc_template_version_real",
        "workpaper_sheet_classification",
        ["template_version_id", "is_real_workpaper"],
        postgresql_where=sa.text("is_real_workpaper = TRUE"),
    )
    op.create_index(
        "idx_wpsc_wp_code_version",
        "workpaper_sheet_classification",
        ["wp_code", "template_version_id"],
    )


def downgrade() -> None:
    # ─── 删除索引 ────────────────────────────────────────────────────────
    op.drop_index("idx_wpsc_wp_code_version", table_name="workpaper_sheet_classification")
    op.drop_index("idx_wpsc_template_version_real", table_name="workpaper_sheet_classification")
    op.drop_index("idx_wpsc_class_scope", table_name="workpaper_sheet_classification")

    # ─── 删除 CHECK constraint ────────────────────────────────────────────
    op.drop_constraint("chk_wpsc_scope_values", "workpaper_sheet_classification", type_="check")

    # ─── 删除新增列（逆序） ──────────────────────────────────────────────
    op.drop_column("workpaper_sheet_classification", "render_schema_path")
    op.drop_column("workpaper_sheet_classification", "template_version_id")
    op.drop_column("workpaper_sheet_classification", "delegated_module")
    op.drop_column("workpaper_sheet_classification", "scope")
    op.drop_column("workpaper_sheet_classification", "is_static_doc")
    op.drop_column("workpaper_sheet_classification", "exclude_from_progress")
    op.drop_column("workpaper_sheet_classification", "exclude_from_archive")
    op.drop_column("workpaper_sheet_classification", "is_real_workpaper")
    op.drop_column("workpaper_sheet_classification", "class")
