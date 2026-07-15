"""ORM model for acnr_project_overlay table.

Requirements: Req-4 (Overlay 持久化与归属校验)
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AcnrProjectOverlay(Base):
    """ACNR L2 ProjectOverlay 持久化 — 项目级别名/CUST覆盖/binding。"""

    __tablename__ = "acnr_project_overlay"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    wp_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("working_paper.id"), nullable=True
    )
    parent_wp_code: Mapped[str] = mapped_column(String(20), nullable=False)
    sheet_code: Mapped[str] = mapped_column(String(40), nullable=False)
    overlay_type: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_overlay_project", "project_id"),
    )
