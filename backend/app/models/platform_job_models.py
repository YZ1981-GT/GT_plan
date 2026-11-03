"""平台通用耐久任务 ORM（V243）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlatformJob(Base):
    __tablename__ = "platform_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation: Mapped[str] = mapped_column(String(48), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_ref: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default=text("'queued'"))
    stage: Mapped[str | None] = mapped_column(String(64))
    progress_current: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    progress_total: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    progress_message: Mapped[str | None] = mapped_column(Text)
    reserved_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=0, server_default=text("0"))
    result_ref: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=3, server_default=text("3"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    version: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=1, server_default=text("1"))
    queued_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        sa.UniqueConstraint("actor_id", "project_id", "operation", "idempotency_key", name="uq_platform_jobs_idempotency"),
        Index("ix_platform_jobs_claim", "status", "next_attempt_at", "lease_expires_at", "queued_at"),
        Index("ix_platform_jobs_project_created", "project_id", "queued_at"),
    )


class PlatformJobAttempt(Base):
    __tablename__ = "platform_job_attempts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform_jobs.id", ondelete="CASCADE"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    lease_token: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", server_default=text("'running'"))
    started_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        sa.UniqueConstraint("job_id", "attempt_no", name="uq_platform_job_attempt_no"),
        sa.UniqueConstraint("lease_token", name="uq_platform_job_attempt_token"),
        Index("ix_platform_job_attempts_job", "job_id", "attempt_no"),
    )
