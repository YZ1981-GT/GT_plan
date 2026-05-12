"""F25 / Sprint 5.18: extend activation_records with audit trail fields.

背景（requirements F25 / design D24）：
- `ActivationRecord` 原有字段 (action, dataset_id, previous_dataset_id, performed_by,
  performed_at, reason) 只能回答"谁在什么时间做了什么"，不能回答：
    - 操作发起的 IP / 终端来源
    - 操作耗时（衡量性能退化）
    - 激活/回滚前后四表行数（防静默数据损失）

本迁移新增 4 个可空字段：
- ip_address VARCHAR(64)    — 操作者 IP（支持 IPv6）
- duration_ms INTEGER        — 操作耗时毫秒
- before_row_counts JSONB    — 激活前四表行数快照
- after_row_counts JSONB     — 激活后四表行数快照

老记录保持 NULL，新记录在 DatasetService.activate/rollback 里填充。

Revision ID: view_refactor_activation_record_20260523
Revises: view_refactor_cleanup_old_deleted_20260517
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "view_refactor_activation_record_20260523"
down_revision = "view_refactor_cleanup_old_deleted_20260517"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    # PG 用 JSONB 走索引友好；SQLite/其他方言退化为通用 JSON
    json_type = JSONB() if dialect == "postgresql" else sa.JSON()

    op.add_column(
        "activation_records",
        sa.Column("ip_address", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "activation_records",
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "activation_records",
        sa.Column("before_row_counts", json_type, nullable=True),
    )
    op.add_column(
        "activation_records",
        sa.Column("after_row_counts", json_type, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("activation_records", "after_row_counts")
    op.drop_column("activation_records", "before_row_counts")
    op.drop_column("activation_records", "duration_ms")
    op.drop_column("activation_records", "ip_address")
