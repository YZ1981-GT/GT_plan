"""E1 Sprint 2 Task 2.1: projects 表新增 scenario + has_foreign_currency

锚定 requirements F1.1 + F1.6:
- scenario VARCHAR(20) NOT NULL DEFAULT 'normal'
  枚举: normal/ipo/listed/transfer/restructure/fraud_response
  驱动 chain_orchestrator 文件级裁剪 + 前端 sheet 显隐
- has_foreign_currency BOOLEAN NOT NULL DEFAULT false
  驱动 E1-1 双区显隐 + E1-3 双版本二选一 + E1-8 外币盘点显隐

Revision ID: wp_e1_project_scenario_20260518
Revises: wp_e1_template_metadata_20260518
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "wp_e1_project_scenario_20260518"
down_revision = "wp_e1_template_metadata_20260518"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "scenario",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'normal'"),
            comment="项目场景: normal/ipo/listed/transfer/restructure/fraud_response",
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "has_foreign_currency",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="是否有外币业务（驱动 E1-1 双区显隐）",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "has_foreign_currency")
    op.drop_column("projects", "scenario")
