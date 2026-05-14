"""Enterprise Linkage ORM Models

Tables: adjustment_editing_locks, tb_change_history, event_cascade_log
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, Numeric, DateTime, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdjustmentEditingLock(Base):
    __tablename__ = "adjustment_editing_locks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    entry_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    locked_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    locked_by_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TbChangeHistory(Base):
    __tablename__ = "tb_change_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    row_code: Mapped[str] = mapped_column(String(20), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    operator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    operator_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delta_amount: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    audited_after: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    source_adjustment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


class EventCascadeLog(Base):
    __tablename__ = "event_cascade_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger_event: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    steps: Mapped[dict] = mapped_column(JSONB, server_default=text("'[]'"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'running'"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
