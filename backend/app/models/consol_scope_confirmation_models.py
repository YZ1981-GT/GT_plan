"""合并范围用户确认快照（D5）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ConsolScopeConfirmation(Base):
    """合并范围确认版本；当前树变化后旧版本保留为 superseded。"""

    __tablename__ = "consol_scope_confirmations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    report_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    revision: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default=text("'active'")
    )
    confirmed_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("revision > 0", name="ck_consol_scope_confirmation_revision"),
        CheckConstraint("length(fingerprint) = 64", name="ck_consol_scope_confirmation_fingerprint"),
        CheckConstraint("status IN ('active', 'superseded')", name="ck_consol_scope_confirmation_status"),
        sa.UniqueConstraint(
            "project_id", "year", "report_scope", "revision",
            name="uq_consol_scope_confirmation_revision",
        ),
        Index(
            "ux_consol_scope_confirmation_active",
            "project_id", "year", "report_scope",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index("idx_consol_scope_confirmation_fingerprint", "project_id", "fingerprint"),
    )


class ConsolScopeConfirmationNode(Base):
    """某确认版本中的角色投影；不是 projects 或金额数据的副本。"""

    __tablename__ = "consol_scope_confirmation_nodes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    confirmation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("consol_scope_confirmations.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_key: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    company_code: Mapped[str] = mapped_column(String(100), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    host_project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    parent_node_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "confirmation_id", "node_key", name="uq_consol_scope_confirmation_node_key"
        ),
        sa.UniqueConstraint(
            "confirmation_id", "position", name="uq_consol_scope_confirmation_node_position"
        ),
        CheckConstraint("position >= 0", name="ck_consol_scope_confirmation_node_position"),
        Index("idx_consol_scope_confirmation_nodes_project", "project_id"),
    )
