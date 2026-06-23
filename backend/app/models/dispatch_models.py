"""分发记录 ORM 模型 — D0-1 跨底稿分发持久化

Feature: cross-workpaper-dispatch-persistence
Migration: V093__create_dispatch_records.sql
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base, TimestampMixin


class DispatchRecord(Base, TimestampMixin):
    """分发记录 — 描述「哪条函证行被分发到了哪个下游底稿」"""

    __tablename__ = "dispatch_records"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    confirm_index: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[str] = mapped_column(String(10), nullable=False)
    entity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    dispatched_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "confirm_index", "target", name="uq_dispatch_dedup"
        ),
        Index("ix_dispatch_project_target", "project_id", "target"),
    )
