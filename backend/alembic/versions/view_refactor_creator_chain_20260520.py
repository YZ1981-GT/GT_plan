"""F22 / Sprint 5.9: ImportJob 新增 creator_chain JSONB 字段。

背景（requirements F22 / design D8.3）：
导入接管机制需要记录接管链路——谁创建了 job、谁接管了、什么时间、什么原因。
原 `created_by UUID` 只记录原始创建者，无法表达接管历史。

新增字段：
- ``creator_chain JSONB DEFAULT '[]'``：接管链路数组
  格式: [{"user_id": "A", "action": "create", "at": "..."}, ...]

Revision ID: view_refactor_creator_chain_20260520
Revises: view_refactor_retention_class_20260526
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "view_refactor_creator_chain_20260520"
down_revision = "view_refactor_retention_class_20260526"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "import_jobs",
        sa.Column(
            "creator_chain",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("import_jobs", "creator_chain")
