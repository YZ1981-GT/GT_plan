"""批量建项两阶段预校验计划 ORM（迁移 V220）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

PLAN_MODES: tuple[str, ...] = ("project", "consolidation")
PLAN_STATUSES: tuple[str, ...] = (
    "invalid", "validated", "applying", "applied", "failed", "expired",
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class ProjectBatchImportPlan(Base, TimestampMixin):
    """一次上传产生的规范化计划、预览与可重放最终回执。"""

    __tablename__ = "project_batch_import_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    mode: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(24), nullable=False, default="validated", server_default=sa.text("'validated'")
    )
    file_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    template_version: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    request_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    tree_preview: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    receipt: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    public_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.CheckConstraint(_in_list("mode", PLAN_MODES), name="ck_project_batch_plans_mode"),
        sa.CheckConstraint(_in_list("status", PLAN_STATUSES), name="ck_project_batch_plans_status"),
        sa.Index(
            "uq_project_batch_plans_actor_key",
            "actor_user_id", "idempotency_key", unique=True,
        ),
        sa.Index(
            "ix_project_batch_plans_actor_status",
            "actor_user_id", "status", "created_at",
        ),
        sa.Index("ix_project_batch_plans_expiry", "status", "expires_at"),
    )


__all__ = ["PLAN_MODES", "PLAN_STATUSES", "ProjectBatchImportPlan"]
