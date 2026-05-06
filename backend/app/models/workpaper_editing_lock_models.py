"""底稿编辑软锁 ORM 模型

Refinement Round 4 — 需求 11：多人协作软锁，防止无意识并发编辑。

策略：查"有效锁"判断 ``released_at IS NULL AND heartbeat_at > now - 5min``。
过期锁由下一次 acquire 或查询时惰性清理（设 ``released_at=now``），不跑 worker。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WorkpaperEditingLock(Base, TimestampMixin):
    """底稿编辑软锁

    每次 acquire 创建一行，release 时设 released_at。
    wp_id 非唯一索引——允许历史锁共存，查时过滤 released_at IS NULL。
    heartbeat_at 索引用于惰性过期清理。
    """

    __tablename__ = "workpaper_editing_locks"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("working_paper.id"),
        nullable=False,
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    acquired_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now()
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now()
    )
    released_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )

    __table_args__ = (
        Index("idx_editing_locks_wp_id", "wp_id"),
        Index("idx_editing_locks_heartbeat_at", "heartbeat_at"),
    )
