"""附注公式计算运行记录（S5 / V238）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NoteFormulaRun(Base):
    """一个章节一次附注公式执行的可查询运行记录。"""

    __tablename__ = "note_formula_run"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    note_section: Mapped[str] = mapped_column(String(100), nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False, default="manual", server_default=text("'manual'"))
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", server_default=text("'running'"))
    executed_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    updated_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    failed_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'partial', 'failed')",
            name="ck_note_formula_run_status",
        ),
        Index("idx_note_formula_run_project_year_section", "project_id", "year", "note_section", "started_at"),
    )
