"""H 循环 Sprint 1 Task 1.3a: projects 表新增 measurement_model

H-F2 计量模式控制：H3 投资性房地产 + H7 生产性生物资产支持
「成本模式」或「公允价值模式」，独立于 scenario 维度。

- measurement_model VARCHAR(20) NOT NULL DEFAULT 'cost'
  枚举: cost / fair_value
  驱动前端 useHFixedAssetSheetGroups sheet 显隐

Revision ID: h_cycle_measurement_model_20260519
Revises: wp_optimization_sprint1_20260520
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "h_cycle_measurement_model_20260519"
down_revision = "wp_optimization_sprint1_20260520"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "measurement_model",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'cost'"),
            comment="计量模式: cost(成本模式) / fair_value(公允价值模式)，驱动 H3/H7 sheet 显隐",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "measurement_model")
