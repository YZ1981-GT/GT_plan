"""归档编排 ORM 模型

Refinement Round 1 — 归档向导 / 断点续传所需的作业状态表。

对应 Alembic 迁移脚本 ``round1_review_closure_signature_20260508.py``。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class ArchiveJob(Base, SoftDeleteMixin, TimestampMixin):
    """归档编排作业

    记录 ``ArchiveOrchestrator`` 每次执行的状态与断点，支持章节级重试。
    ``last_succeeded_section`` 使用 ``archive_section_registry`` 的章节前缀
    （如 ``"01"``、``"10"``），重试时从下一章节开始。

    Refinement Round 1 — 需求 5/6。
    """

    __tablename__ = "archive_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(
        String(20),
        server_default=text("'final'"),
        nullable=False,
    )  # 'final' | 'interim'
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=text("'queued'"),
        nullable=False,
    )  # 'queued' | 'running' | 'succeeded' | 'failed' | 'partial'
    push_to_cloud: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    purge_local: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    gate_eval_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    last_succeeded_section: Mapped[str | None] = mapped_column(String(16), nullable=True)
    failed_section: Mapped[str | None] = mapped_column(String(16), nullable=True)
    failed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    section_progress: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "idx_archive_jobs_project_status",
            "project_id",
            "status",
            postgresql_where=text("is_deleted = false"),
        ),
        Index("idx_archive_jobs_status", "status"),
        # TODO(Round2-Task-E): Add GIN index on section_progress for operational queries
        # Index("idx_archive_jobs_section_progress_gin", "section_progress", postgresql_using="gin"),
    )
