"""E1 Sprint 2 Task 2.21: review_records 表新增双向溯源字段

锚定 requirements F5.5/F5.7 + design D14:
- source_sheet: 复核记录 sheet 名（A21-1 等模板内）
- target_sheet: 被复核底稿 sheet 名（货币资金审定表E1-1 等）
- target_cell: 目标 cell 坐标（R41 等）
- review_layer: 复核层级 L1/L2/L3/L4/L5/committee/it/tax

支持复核模板↔E1 底稿双向跳转 + L1-L5 复核 badge 状态。

Revision ID: wp_e1_review_record_20260519
Revises: wp_e1_project_scenario_20260518
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "wp_e1_review_record_20260519"
down_revision = "wp_e1_project_scenario_20260518"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "review_records",
        sa.Column("source_sheet", sa.String(100), nullable=True, comment="源 sheet 名（复核模板）"),
    )
    op.add_column(
        "review_records",
        sa.Column("target_sheet", sa.String(100), nullable=True, comment="目标 sheet 名（被复核底稿）"),
    )
    op.add_column(
        "review_records",
        sa.Column("target_cell", sa.String(50), nullable=True, comment="目标 cell（如 R41）"),
    )
    op.add_column(
        "review_records",
        sa.Column(
            "review_layer",
            sa.String(20),
            nullable=True,
            comment="复核层级: L1/L2/L3/L4/L5/committee/it/tax",
        ),
    )
    # 索引：按 review_layer 查询
    op.create_index(
        "idx_review_records_layer",
        "review_records",
        ["review_layer"],
        postgresql_where=sa.text("is_deleted = false AND review_layer IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_review_records_layer", table_name="review_records")
    op.drop_column("review_records", "review_layer")
    op.drop_column("review_records", "target_cell")
    op.drop_column("review_records", "target_sheet")
    op.drop_column("review_records", "source_sheet")
