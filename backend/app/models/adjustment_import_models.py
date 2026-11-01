"""调整分录 Excel 导入的耐久批次和逐组结果。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdjustmentImportBatch(Base):
    __tablename__ = "adjustment_import_batches"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    mode: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="processing")
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    parent_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("adjustment_import_batches.id", ondelete="RESTRICT"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.CheckConstraint("mode IN ('append','overwrite')", name="ck_adjustment_import_batches_mode"),
        sa.CheckConstraint("status IN ('processing','completed','partial','failed')", name="ck_adjustment_import_batches_status"),
        sa.Index("ix_adjustment_import_batches_scope", "project_id", "year", "created_at"),
    )


class AdjustmentImportGroupResult(Base):
    __tablename__ = "adjustment_import_group_results"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("adjustment_import_batches.id", ondelete="CASCADE"), nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    group_key: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    source_rows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    action: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    entry_group_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())

    __table_args__ = (
        sa.CheckConstraint("status IN ('imported','skipped','failed')", name="ck_adjustment_import_group_results_status"),
        sa.Index("ix_adjustment_import_group_results_batch", "batch_id", "status", "created_at"),
        sa.Index("ix_adjustment_import_group_results_external", "project_id", "year", "external_reference"),
    )
