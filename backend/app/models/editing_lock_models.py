"""通用编辑锁 ORM 模型

能力域 C — global-refinement-v5-closure：
以 (resource_type, resource_id) 为锁维度，支持 disclosure_note / audit_report / 任意资源类型。

策略：查"有效锁"判断 ``released_at IS NULL AND heartbeat_at > now - 5min``。
过期锁由下一次 acquire 时惰性清理（设 ``released_at=now``），不跑 worker。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class EditingLock(Base, TimestampMixin):
    """通用编辑锁

    每次 acquire 创建一行，release 时设 released_at。
    部分唯一索引 uq_editing_locks_active 保证同资源活跃锁 ≤ 1。
    heartbeat_at 索引用于惰性过期清理。
    """

    __tablename__ = "editing_locks"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    holder_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    holder_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    acquired_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    released_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("idx_editing_locks_resource", "resource_type", "resource_id"),
        Index("idx_editing_locks_heartbeat", "heartbeat_at"),
    )
