"""调整分录组复核任务与财务处理历史模型。

分录行仍存于 ``adjustments`` / ``adjustment_entries``；本模块只保存组级工作流，
避免把指定复核人、职责分离和最终处理状态复制到每条借贷行。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class AdjustmentReviewTask(Base, SoftDeleteMixin, TimestampMixin):
    """一笔调整分录的一轮持久化复核任务。"""

    __tablename__ = "adjustment_review_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    entry_group_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default="pending", server_default=sa.text("'pending'"),
    )
    required_level: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="manager", server_default=sa.text("'manager'"),
    )
    revision: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1"),
    )
    group_content_revision: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1"),
    )
    assigned_reviewer_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'"),
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
    )
    submit_note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    self_review_override_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'withdrawn', 'stale')",
            name="ck_adjustment_review_tasks_status",
        ),
        sa.CheckConstraint(
            "required_level IN ('manager', 'partner')",
            name="ck_adjustment_review_tasks_required_level",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_adjustment_review_tasks_revision"),
        sa.CheckConstraint(
            "group_content_revision >= 1",
            name="ck_adjustment_review_tasks_group_revision",
        ),
        sa.Index(
            "ix_adjustment_review_tasks_project_status",
            "project_id", "year", "status", "submitted_at",
        ),
    )


class AdjustmentTreatmentEvent(Base):
    """调整财务处理的追加式事件，不覆盖历史。"""

    __tablename__ = "adjustment_treatment_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    entry_group_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    action: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("ledger_datasets.id", ondelete="RESTRICT"), nullable=True,
    )
    voucher_keys: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'"),
    )
    misstatement_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("unadjusted_misstatements.id", ondelete="RESTRICT"),
        nullable=True,
    )
    client_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("adjustment_client_bookings.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reverses_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("adjustment_treatment_events.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
    )

    __table_args__ = (
        sa.CheckConstraint(
            "action IN ('include_in_working_tb', 'client_booked', "
            "'unadjusted_misstatement', 'withdraw')",
            name="ck_adjustment_treatment_events_action",
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_adjustment_treatment_events_sequence"),
        sa.CheckConstraint(
            "(action = 'client_booked' AND client_booking_id IS NOT NULL AND misstatement_id IS NULL) "
            "OR (action = 'unadjusted_misstatement' AND misstatement_id IS NOT NULL AND client_booking_id IS NULL) "
            "OR (action IN ('include_in_working_tb', 'withdraw') AND misstatement_id IS NULL AND client_booking_id IS NULL)",
            name="ck_adjustment_treatment_events_payload",
        ),
        sa.Index(
            "uq_adjustment_treatment_events_group_sequence",
            "project_id", "entry_group_id", "sequence", unique=True,
        ),
        sa.Index(
            "ix_adjustment_treatment_events_group_time",
            "project_id", "year", "entry_group_id", "created_at",
        ),
    )


class AdjustmentClientBooking(Base):
    """客户已入账的追加式标记/撤销历史。"""

    __tablename__ = "adjustment_client_bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    entry_group_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    voucher_keys: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'"),
    )
    booked_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("ledger_datasets.id", ondelete="RESTRICT"), nullable=True,
    )
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
    )

    __table_args__ = (
        sa.CheckConstraint("action IN ('book', 'revoke')", name="ck_adjustment_client_bookings_action"),
        sa.CheckConstraint("sequence >= 1", name="ck_adjustment_client_bookings_sequence"),
        sa.Index(
            "uq_adjustment_client_bookings_group_sequence",
            "project_id", "entry_group_id", "sequence", unique=True,
        ),
        sa.Index(
            "ix_adjustment_client_bookings_group_time",
            "project_id", "year", "entry_group_id", "created_at", "id",
        ),
    )
