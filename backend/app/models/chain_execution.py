"""ChainExecution ORM 模型 — 全链路执行记录

Requirements: 1.10, 9.1, 9.2
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChainExecution(Base):
    """全链路执行记录"""

    __tablename__ = "chain_executions"

    id: Mapped[_uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    project_id: Mapped[_uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    steps: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    triggered_by: Mapped[_uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    total_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
