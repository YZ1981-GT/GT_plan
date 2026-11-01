"""持久化合并运行 ORM（consolidation-run-and-workpaper-lifecycle-closure）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

OPERATION_TYPES: tuple[str, ...] = ("refresh_all", "push")
OPERATION_STATUSES: tuple[str, ...] = (
    "queued", "running", "succeeded", "partial", "failed", "stale", "cancelled",
)
ACTIVE_OPERATION_STATUSES: tuple[str, ...] = ("queued", "running")
TERMINAL_OPERATION_STATUSES: tuple[str, ...] = (
    "succeeded", "partial", "failed", "stale", "cancelled",
)

_UUID = PG_UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_DIGEST = sa.CHAR(64)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class ConsolOperation(Base):
    """一次可恢复、可比较输入版本的合并运行。"""

    __tablename__ = "consol_operation"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    operation_type: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    idempotency_keys: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'"),
    )
    request_hash: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'"),
    )
    context_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'"),
    )
    version_vector: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'"),
    )
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default="queued", server_default=sa.text("'queued'"),
    )
    revision: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1"),
    )
    attempt: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0"),
    )
    lease_owner: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'"),
    )
    errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'"),
    )
    result_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'"),
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'"),
    )
    trigger_source: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    queued_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(),
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("consol_operation.id", ondelete="SET NULL"), nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            _in_list("operation_type", OPERATION_TYPES),
            name="ck_consol_operation_type",
        ),
        CheckConstraint(
            _in_list("status", OPERATION_STATUSES),
            name="ck_consol_operation_status",
        ),
        CheckConstraint("revision > 0 AND attempt >= 0", name="ck_consol_operation_revision"),
        CheckConstraint("length(request_hash) = 64", name="ck_consol_operation_hash"),
        CheckConstraint(
            "(status = 'running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status <> 'running' AND lease_owner IS NULL AND lease_expires_at IS NULL)",
            name="ck_consol_operation_lease",
        ),
        Index(
            "ux_consol_operation_idempotency",
            "project_id", "year", "idempotency_key", unique=True,
        ),
        Index(
            "ux_consol_operation_running",
            "project_id", "year", unique=True,
            postgresql_where=sa.text("status = 'running'"),
            sqlite_where=sa.text("status = 'running'"),
        ),
        Index(
            "ux_consol_operation_queued",
            "project_id", "year", unique=True,
            postgresql_where=sa.text("status = 'queued'"),
            sqlite_where=sa.text("status = 'queued'"),
        ),
        Index(
            "ix_consol_operation_project_year",
            "project_id", "year", "queued_at",
        ),
        Index(
            "ix_consol_operation_claim",
            "status", "lease_expires_at", "queued_at",
        ),
    )
