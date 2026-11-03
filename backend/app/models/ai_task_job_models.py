"""耐久 AI 批任务 ORM（V238）。"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AiTaskJob(Base):
    __tablename__ = "ai_task_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    task_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", server_default=text("'queued'"))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    progress_total: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    progress_done: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    failed_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    cancelled_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    version: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        sa.UniqueConstraint("actor_id", "project_id", "task_kind", "idempotency_key", name="uq_ai_task_job_idempotency"),
        Index("ix_ai_task_jobs_project_created", "project_id", "created_at"),
    )


class AiTaskItem(Base):
    __tablename__ = "ai_task_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_task_jobs.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    target_key: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default=text("'queued'"))
    generation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_chat_message.id", ondelete="SET NULL"))
    baseline_version: Mapped[str | None] = mapped_column(String(80))
    before_hash: Mapped[str | None] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    result_summary: Mapped[dict | None] = mapped_column(JSONB)
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=3, server_default=text("3"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        sa.UniqueConstraint("job_id", "target_type", "target_id", "target_key", name="uq_ai_task_item_target"),
        sa.UniqueConstraint("job_id", "ordinal", name="uq_ai_task_item_ordinal"),
        sa.UniqueConstraint("generation_id", name="uq_ai_task_item_generation"),
        Index("ix_ai_task_items_job_status", "job_id", "status"),
        Index("ix_ai_task_items_claim", "status", "next_attempt_at", "lease_expires_at"),
    )
