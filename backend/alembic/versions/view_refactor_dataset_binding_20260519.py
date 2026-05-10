"""F50 / Sprint 8.16: 下游对象快照绑定（bound_dataset_id + dataset_bound_at）。

背景（requirements F50 / design D13.1）：
- 合规关键改造：底稿/审计报告/附注/未更正错报生成或定稿时，快照绑定当时的
  active dataset_id。绑定后 rollback 该 dataset 会被拒绝（409）保证签字后
  报表数字不可篡改，对齐《会计档案管理办法》合规要求。

涉及 4 张表：
  - working_paper（底稿，生成时绑定）
  - audit_report（审计报告，转 final 时锁定）
  - disclosure_notes（附注，生成时绑定）
  - unadjusted_misstatements（未更正错报，创建时绑定）

新增字段（每张表 2 列 + 1 FK）：
  - bound_dataset_id UUID NULL, FK → ledger_datasets(id) ON DELETE RESTRICT
  - dataset_bound_at TIMESTAMP WITH TIME ZONE NULL

FK 采用 ON DELETE RESTRICT：一旦绑定，被引用的 dataset 无法物理删除；
purge 任务 / rollback 流程都必须先检查 bound_dataset_id 关系。

Revision ID: view_refactor_dataset_binding_20260519
Revises: event_outbox_dlq_20260521
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision = "view_refactor_dataset_binding_20260519"
down_revision = "event_outbox_dlq_20260521"
branch_labels = None
depends_on = None


# 4 张下游表（注意：working_paper / audit_report 单数，disclosure_notes /
# unadjusted_misstatements 复数 —— 与 ORM __tablename__ 一致）
_TARGET_TABLES: tuple[str, ...] = (
    "working_paper",
    "audit_report",
    "disclosure_notes",
    "unadjusted_misstatements",
)


def _fk_name(table: str) -> str:
    return f"fk_{table}_bound_dataset"


def _idx_name(table: str) -> str:
    return f"idx_{table}_bound_dataset"


def upgrade() -> None:
    # PG: 扩展 activation_type 枚举，新增 'force_unbind' 成员（Sprint 8.27）
    # SQLite 不支持原生 enum，建表时已按字符串存储，直接跳过
    # 注意：PG ALTER TYPE ADD VALUE 不能在 transaction 内执行，用 autocommit_block
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE activation_type ADD VALUE IF NOT EXISTS 'force_unbind'"
            )

    for table in _TARGET_TABLES:
        op.add_column(
            table,
            sa.Column(
                "bound_dataset_id",
                PG_UUID(as_uuid=True),
                nullable=True,
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "dataset_bound_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        op.create_foreign_key(
            _fk_name(table),
            table,
            "ledger_datasets",
            ["bound_dataset_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        # partial index：只为绑定的行建索引，rollback 保护查询走索引
        op.create_index(
            _idx_name(table),
            table,
            ["bound_dataset_id"],
            postgresql_where=sa.text("bound_dataset_id IS NOT NULL"),
        )


def downgrade() -> None:
    # 先 drop index + FK，再 drop column
    for table in _TARGET_TABLES:
        op.drop_index(_idx_name(table), table_name=table)
        op.drop_constraint(_fk_name(table), table, type_="foreignkey")
        op.drop_column(table, "dataset_bound_at")
        op.drop_column(table, "bound_dataset_id")
