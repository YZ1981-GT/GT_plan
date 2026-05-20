"""E1 Sprint 1 Task 1.0: wp_template_metadata 新增 header_cells + llm_prompts

为 E1 货币资金底稿优化 (workpaper-e1-cash-optimization spec) 新增两个 JSONB
字段:
- header_cells: 表头自动填充配置（R3/R4 6 个 cell 坐标 → 项目元数据字段）
- llm_prompts: LLM 提示词模板配置（4 种场景: audit_conclusion / variance_analysis
  / check_conclusion / cutoff_conclusion）

锚定 requirements F4.2 (表头自动填充) + F6.3 (LLM 辅助审计说明)。

Revision ID: wp_e1_template_metadata_20260518
Revises: wp_optimization_sprint1_20260520
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "wp_e1_template_metadata_20260518"
down_revision = "wp_optimization_sprint1_20260520"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wp_template_metadata",
        sa.Column(
            "header_cells",
            JSONB,
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
            comment="表头自动填充配置: cell 坐标 → 字段映射",
        ),
    )
    op.add_column(
        "wp_template_metadata",
        sa.Column(
            "llm_prompts",
            JSONB,
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
            comment="LLM 提示词模板: 场景名 → prompt 模板",
        ),
    )


def downgrade() -> None:
    op.drop_column("wp_template_metadata", "llm_prompts")
    op.drop_column("wp_template_metadata", "header_cells")
