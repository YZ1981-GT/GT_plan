"""Refinement Round 4: workpaper editing soft lock table

Revision ID: round4_editing_lock_20260506
Revises: round5_eqcr_20260506

本迁移落地 Round 4 需求 11 的编辑软锁表：

1. ``workpaper_editing_locks`` — 底稿编辑软锁（防无意识并发）

策略：查"有效锁"判断 ``released_at IS NULL AND heartbeat_at > now - 5min``。
过期锁由下一次 acquire 或查询时惰性清理（设 ``released_at=now``），不跑 worker。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "round4_editing_lock_20260506"
down_revision = "round5_eqcr_20260506"
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
    if not _has_table("workpaper_editing_locks"):
        op.create_table(
            "workpaper_editing_locks",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "wp_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("working_paper.id"),
                nullable=False,
            ),
            sa.Column(
                "staff_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column(
                "acquired_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "heartbeat_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("released_at", sa.DateTime(), nullable=True),
            # TimestampMixin
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # 索引
    if _is_postgres():
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_editing_locks_wp_id "
            "ON workpaper_editing_locks (wp_id)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_editing_locks_heartbeat_at "
            "ON workpaper_editing_locks (heartbeat_at)"
        )
    else:
        if not _has_index("workpaper_editing_locks", "idx_editing_locks_wp_id"):
            op.create_index(
                "idx_editing_locks_wp_id",
                "workpaper_editing_locks",
                ["wp_id"],
            )
        if not _has_index("workpaper_editing_locks", "idx_editing_locks_heartbeat_at"):
            op.create_index(
                "idx_editing_locks_heartbeat_at",
                "workpaper_editing_locks",
                ["heartbeat_at"],
            )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    op.drop_table("workpaper_editing_locks")
