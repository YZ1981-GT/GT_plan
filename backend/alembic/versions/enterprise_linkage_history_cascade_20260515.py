"""Enterprise Linkage Sprint 1: tb_change_history + event_cascade_log 表

背景（requirements 7.1, 7.2, 8.1, 8.2 / design D5, D6）：
- tb_change_history：记录试算平衡表行次变更历史（调整分录增删改、手动编辑、重分类）
- event_cascade_log：记录事件级联执行日志（触发→步骤→完成/降级/失败）

新增：
1. ``tb_change_history`` 表 — 试算表行次变更审计轨迹
   - 索引：(project_id, year, row_code, created_at DESC)
2. ``event_cascade_log`` 表 — 事件级联执行日志
   - 索引：(project_id, started_at DESC)
   - 部分索引：(status) WHERE status != 'completed'

Revision ID: enterprise_linkage_history_cascade_20260515
Revises: enterprise_linkage_locks_20260515
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "enterprise_linkage_history_cascade_20260515"
down_revision = "enterprise_linkage_locks_20260515"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _inspector():
    bind = op.get_bind()
    return sa.inspect(bind)


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    columns = {col["name"] for col in _inspector().get_columns(table_name)}
    return column_name in columns


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    indexes = {ix["name"] for ix in _inspector().get_indexes(table_name)}
    return index_name in indexes


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. 创建 tb_change_history 表
    # -----------------------------------------------------------------------
    if not _has_table("tb_change_history"):
        op.create_table(
            "tb_change_history",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column(
                "year",
                sa.Integer(),
                nullable=False,
            ),
            sa.Column(
                "row_code",
                sa.String(20),
                nullable=False,
            ),
            sa.Column(
                "operation_type",
                sa.String(30),
                nullable=False,
                comment="adjustment_created/modified/deleted/manual_edit/reclassification",
            ),
            sa.Column(
                "operator_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column(
                "operator_name",
                sa.String(100),
                nullable=True,
            ),
            sa.Column(
                "delta_amount",
                sa.Numeric(20, 2),
                nullable=True,
            ),
            sa.Column(
                "audited_after",
                sa.Numeric(20, 2),
                nullable=True,
            ),
            sa.Column(
                "source_adjustment_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # -----------------------------------------------------------------------
    # 2. 创建 tb_change_history 索引
    # -----------------------------------------------------------------------
    if _is_postgres():
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_tb_history_row "
            "ON tb_change_history (project_id, year, row_code, created_at DESC)"
        )
    else:
        if not _has_index("tb_change_history", "idx_tb_history_row"):
            op.create_index(
                "idx_tb_history_row",
                "tb_change_history",
                ["project_id", "year", "row_code", "created_at"],
            )

    # -----------------------------------------------------------------------
    # 3. 创建 event_cascade_log 表
    # -----------------------------------------------------------------------
    if not _has_table("event_cascade_log"):
        op.create_table(
            "event_cascade_log",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
            ),
            sa.Column(
                "year",
                sa.Integer(),
                nullable=True,
            ),
            sa.Column(
                "trigger_event",
                sa.String(50),
                nullable=False,
            ),
            sa.Column(
                "trigger_payload",
                postgresql.JSONB,
                nullable=True,
            ),
            sa.Column(
                "steps",
                postgresql.JSONB,
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.String(20),
                server_default=sa.text("'running'"),
                nullable=False,
                comment="running/completed/degraded/failed",
            ),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "completed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column(
                "total_duration_ms",
                sa.Integer(),
                nullable=True,
            ),
        )

    # -----------------------------------------------------------------------
    # 4. 创建 event_cascade_log 索引
    # -----------------------------------------------------------------------
    if _is_postgres():
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_cascade_log_project "
            "ON event_cascade_log (project_id, started_at DESC)"
        )
        # 部分索引：未完成的级联记录（用于监控/清理）
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_cascade_log_status "
            "ON event_cascade_log (status) WHERE status != 'completed'"
        )
    else:
        if not _has_index("event_cascade_log", "idx_cascade_log_project"):
            op.create_index(
                "idx_cascade_log_project",
                "event_cascade_log",
                ["project_id", "started_at"],
            )
        if not _has_index("event_cascade_log", "idx_cascade_log_status"):
            op.create_index(
                "idx_cascade_log_status",
                "event_cascade_log",
                ["status"],
            )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # 移除 event_cascade_log 表（级联删除索引）
    if _has_table("event_cascade_log"):
        op.drop_table("event_cascade_log")

    # 移除 tb_change_history 表（级联删除索引）
    if _has_table("tb_change_history"):
        op.drop_table("tb_change_history")
