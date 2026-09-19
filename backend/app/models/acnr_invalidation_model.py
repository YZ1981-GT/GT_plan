"""ORM models for ACNR durable invalidation (epoch + outbox).

Spec: acnr-invalidation-overlay-hardening (Wave 1, R11)

- AcnrInvalidationEpoch: per-project 单调递增失效计数器（Redis 不可用仍在 DB 递增）。
- AcnrInvalidationOutbox: 业务变更同事务写入的失效信号，dispatcher 至少一次投递。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AcnrInvalidationEpoch(Base):
    """ACNR Durable_Epoch — per-project 失效计数器（DB 权威，Redis 仅 fan-out）。"""

    __tablename__ = "acnr_invalidation_epoch"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True
    )
    epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, server_default=sa.text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AcnrInvalidationOutbox(Base):
    """ACNR Invalidation_Outbox — 业务变更同事务写入，dispatcher 至少一次投递。"""

    __tablename__ = "acnr_invalidation_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    wp_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(nullable=True)
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))

    __table_args__ = (
        Index(
            "idx_inval_outbox_undispatched",
            "created_at",
            postgresql_where=sa.text("dispatched_at IS NULL"),
        ),
    )
