"""创建 note_account_mappings 表 — 附注科目对照映射

Requirements: 23.1, 23.2, 23.3

Revision ID: note_account_mappings_20260516
Revises: note_validation_results_20260516
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "note_account_mappings_20260516"
down_revision = "note_validation_results_20260516"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note_account_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_type", sa.String(20), nullable=False),  # soe / listed
        sa.Column("report_row_code", sa.String(50), nullable=False),  # BS-002
        sa.Column("note_section_code", sa.String(100), nullable=False),  # 章节编码
        sa.Column("table_index", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("validation_role", sa.String(30), nullable=True),  # 余额/宽表/交叉/其中项/描述
        sa.Column("wp_code", sa.String(30), nullable=True),  # E1/D2/F2
        sa.Column("fetch_mode", sa.String(30), nullable=True),  # total/detail/category/change
    )
    op.create_index(
        "ix_note_account_mappings_template_row",
        "note_account_mappings",
        ["template_type", "report_row_code"],
    )
    op.create_index(
        "ix_note_account_mappings_template_section",
        "note_account_mappings",
        ["template_type", "note_section_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_note_account_mappings_template_section")
    op.drop_index("ix_note_account_mappings_template_row")
    op.drop_table("note_account_mappings")
