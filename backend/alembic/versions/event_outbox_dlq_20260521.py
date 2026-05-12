"""F45 / Sprint 7.17: event_outbox_dlq 死信队列表。

背景（requirements F45 / design D11.3 / tasks 7.17-7.18）：
- ``import_event_outbox`` 现有重试机制最多 N 次（config: ``LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS``）
  后停止重试，但"永久失败"的事件会一直留在 outbox 表 status=failed，没有运维入口。
- 本迁移新建 ``event_outbox_dlq`` 表，作为 outbox 的"死信队列"：
  重试 N 次仍失败的事件快照进入 DLQ（保留原始 payload + 失败原因 + attempt_count），
  原 outbox 行保留 status=failed 作审计（不删除）。
- DLQ 表与 outbox 表通过 ``original_event_id`` 字段松耦合（FK nullable），
  因为 outbox 行可能被定期清理而 DLQ 需长期保留。

**设计要点**：
- PG: ``original_event_id UUID NULL REFERENCES import_event_outbox(id) ON DELETE SET NULL``
  保证原 outbox 清理时 DLQ 行不受影响（只把 FK 清空）。
- ``resolved_at / resolved_by`` 为人工处理后的回执字段（``null`` 表未处理）。
- ``payload JSONB`` 做事件数据 snapshot，独立存储便于重投。
- 索引 ``(project_id, year, moved_to_dlq_at)`` 支持"查询某项目的最近死信"。
- 索引 ``(resolved_at)`` 支持"查找未处理的死信"（partial index，resolved_at IS NULL）。

**回滚策略**：downgrade 直接 drop_table；DLQ 行是运维辅助数据，删除安全。
production 环境若需要保留，upgrade 前手动 dump 表数据。

Revision ID: event_outbox_dlq_20260521
Revises: view_refactor_force_submit_20260524
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID


revision = "event_outbox_dlq_20260521"
down_revision = "view_refactor_force_submit_20260524"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_outbox_dlq",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "original_event_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("import_event_outbox.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "moved_to_dlq_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "resolved_by",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_event_outbox_dlq_project_year",
        "event_outbox_dlq",
        ["project_id", "year", "moved_to_dlq_at"],
    )
    # partial index 加速 "未处理的 DLQ 行" 查询
    op.create_index(
        "idx_event_outbox_dlq_unresolved",
        "event_outbox_dlq",
        ["moved_to_dlq_at"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )

    # F46 / Sprint 7.22: 下游对象 is_stale 字段
    # 底稿已有 working_paper.prefill_stale（phase 9 落地）—— 这里不动。
    # 审计报告 / 附注之前没有 stale 标记，本轮补齐，让 rollback 事件可以
    # 统一把三类下游都标 stale=True，提示用户刷新。
    op.add_column(
        "audit_report",
        sa.Column(
            "is_stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "disclosure_notes",
        sa.Column(
            "is_stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("disclosure_notes", "is_stale")
    op.drop_column("audit_report", "is_stale")
    op.drop_index("idx_event_outbox_dlq_unresolved", table_name="event_outbox_dlq")
    op.drop_index("idx_event_outbox_dlq_project_year", table_name="event_outbox_dlq")
    op.drop_table("event_outbox_dlq")
