"""Phase 3 性能优化：tb_balance 复合索引

为 tb_balance 表添加 (project_id, year, account_code) 复合索引，
加速试算表查询（6000 并发场景下的核心瓶颈）。

Revision ID: phase3_tb_balance_composite_index_20260527
Revises: view_refactor_retention_class_20260526
"""
from __future__ import annotations

from alembic import op


revision = "phase3_tb_balance_composite_index_20260527"
down_revision = "view_refactor_retention_class_20260526"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 复合索引：覆盖试算表主查询路径 (project_id, year, account_code)
    op.create_index(
        "idx_tb_balance_project_year_account",
        "tb_balance",
        ["project_id", "year", "account_code"],
    )
    # 补充索引：覆盖按 project_id + year 的全量查询（不含 account_code 过滤）
    op.create_index(
        "idx_tb_balance_project_year",
        "tb_balance",
        ["project_id", "year"],
    )


def downgrade() -> None:
    op.drop_index("idx_tb_balance_project_year", table_name="tb_balance")
    op.drop_index("idx_tb_balance_project_year_account", table_name="tb_balance")
