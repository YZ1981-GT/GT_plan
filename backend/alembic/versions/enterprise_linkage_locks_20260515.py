"""Enterprise Linkage Sprint 1: adjustment_editing_locks 表 + adjustments.version 列

背景（requirements 5.1, 5.5 / design D3）：
调整分录编辑冲突守卫需要软锁表（防多人同时编辑同一笔分录）和乐观锁版本号。

新增：
1. ``adjustment_editing_locks`` 表 — 调整分录编辑软锁
   - 部分唯一索引 ``(entry_group_id) WHERE released_at IS NULL``（PG 专用）
   - 索引：heartbeat_at（过期清理扫描）、project_id（项目级查询）
2. ``adjustments.version`` 列 — 乐观锁版本号（INT NOT NULL DEFAULT 1）

Revision ID: enterprise_linkage_locks_20260515
Revises: view_refactor_interrupted_status_20260511
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "enterprise_linkage_locks_20260515"
down_revision = "view_refactor_interrupted_status_20260511"
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
    # 1. 创建 adjustment_editing_locks 表
    # -----------------------------------------------------------------------
    if not _has_table("adjustment_editing_locks"):
        op.create_table(
            "adjustment_editing_locks",
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
                "entry_group_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
            ),
            sa.Column(
                "locked_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column(
                "locked_by_name",
                sa.String(100),
                nullable=True,
            ),
            sa.Column(
                "acquired_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "heartbeat_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "released_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    # -----------------------------------------------------------------------
    # 2. 创建索引
    # -----------------------------------------------------------------------

    # 部分唯一索引：同一 entry_group_id 只允许一个活跃锁（released_at IS NULL）
    if _is_postgres():
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_adj_lock_active "
            "ON adjustment_editing_locks (entry_group_id) "
            "WHERE released_at IS NULL"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_adj_lock_heartbeat "
            "ON adjustment_editing_locks (heartbeat_at)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_adj_lock_project "
            "ON adjustment_editing_locks (project_id)"
        )
    else:
        # SQLite 不支持部分唯一索引，创建普通索引作为兼容
        if not _has_index("adjustment_editing_locks", "idx_adj_lock_heartbeat"):
            op.create_index(
                "idx_adj_lock_heartbeat",
                "adjustment_editing_locks",
                ["heartbeat_at"],
            )
        if not _has_index("adjustment_editing_locks", "idx_adj_lock_project"):
            op.create_index(
                "idx_adj_lock_project",
                "adjustment_editing_locks",
                ["project_id"],
            )

    # -----------------------------------------------------------------------
    # 3. adjustments 表新增 version 列（乐观锁）
    # -----------------------------------------------------------------------
    if not _has_column("adjustments", "version"):
        op.add_column(
            "adjustments",
            sa.Column(
                "version",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
            ),
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # 移除 version 列
    if _has_column("adjustments", "version"):
        op.drop_column("adjustments", "version")

    # 移除表（级联删除索引）
    if _has_table("adjustment_editing_locks"):
        op.drop_table("adjustment_editing_locks")
