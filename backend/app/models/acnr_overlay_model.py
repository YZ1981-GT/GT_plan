"""ORM model for acnr_project_overlay table.

Requirements: Req-4 (Overlay 持久化与归属校验)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, func
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
    # V122: overlay 治理字段（持久化，重启后 is_expired 生效）+ 乐观并发 revision
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    revision: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_overlay_project", "project_id"),
        # V122: 组合唯一约束（Overlay_Unique_Key）
        UniqueConstraint(
            "project_id", "parent_wp_code", "sheet_code", "overlay_type",
            name="uq_overlay_identity",
        ),
    )
