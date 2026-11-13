"""高级查询运行记录与查询证据模型（迁移 V267）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QueryRun(Base):
    """一次查询定义在一个来源版本上的不可变运行记录。"""

    __tablename__ = "query_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    entry: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'direct'")
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    definition: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    definition_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    definition_version: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=text("1")
    )
    scope: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    labels: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    version_vector: Mapped[dict] = mapped_column(JSONB, nullable=False)
    vector_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    vector_weak: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    captured_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    execution_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("1")
    )
    first_executed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_executed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_total: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    last_warnings: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    hidden_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "entry", "definition_hash", "vector_hash",
            name="uq_query_runs_identity",
        ),
        Index(
            "ix_query_runs_history", "user_id", "entry", sa.desc("last_executed_at"),
            postgresql_where=text("hidden_at IS NULL"),
        ),
        Index(
            "ix_query_runs_definition", "user_id", "definition_hash", sa.desc("last_executed_at")
        ),
        Index("ix_query_runs_project", "project_id"),
        sa.CheckConstraint("entry IN ('business', 'builder')", name="ck_query_runs_entry"),
        sa.CheckConstraint("origin IN ('direct', 'template')", name="ck_query_runs_origin"),
        sa.CheckConstraint(
            "definition_hash ~ '^[0-9a-f]{64}$' AND vector_hash ~ '^[0-9a-f]{64}$'",
            name="ck_query_runs_hashes",
        ).ddl_if(dialect="postgresql"),
        sa.CheckConstraint("execution_count >= 1", name="ck_query_runs_count"),
    )


class QueryArtifact(Base):
    """一次「导出全部」生成的不可变查询证据清单。"""

    __tablename__ = "query_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("query_runs.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    entry: Mapped[str] = mapped_column(String(16), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    definition_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    version_vector: Mapped[dict] = mapped_column(JSONB, nullable=False)
    vector_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    scope: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'ready'")
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    row_count: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    columns: Mapped[list] = mapped_column(JSONB, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    retention_until: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    purged_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_query_artifacts_storage"),
        Index("ix_query_artifacts_user", "user_id", sa.desc("created_at")),
        Index(
            "ix_query_artifacts_expiry", "retention_until",
            postgresql_where=text("status = 'ready'"),
        ),
        Index("ix_query_artifacts_run", "run_id"),
        Index("ix_query_artifacts_definition", "user_id", "definition_hash"),
        sa.CheckConstraint("entry IN ('business', 'builder')", name="ck_query_artifacts_entry"),
        sa.CheckConstraint("status IN ('ready', 'purged')", name="ck_query_artifacts_status"),
        sa.CheckConstraint(
            "(status = 'purged') = (purged_at IS NOT NULL)",
            name="ck_query_artifacts_purged",
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$' AND manifest_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_query_artifacts_hashes",
        ).ddl_if(dialect="postgresql"),
        sa.CheckConstraint("byte_size >= 0 AND row_count >= 0", name="ck_query_artifacts_sizes"),
    )


__all__ = ["QueryRun", "QueryArtifact"]
