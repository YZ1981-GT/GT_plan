"""底稿两阶段生成 operation/item ORM（对应迁移 V224，原 V216，2026-10-30 同步改号）。

operation 是客户端幂等身份与恢复真源；item 保存 Phase A 预留身份及文件 manifest。
状态迁移的单调性由后续 operation 服务以 CAS 保证，本模块和数据库先封闭合法取值。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

OPERATION_KINDS: tuple[str, ...] = ("template_set", "from_codes")
FAILURE_POLICIES: tuple[str, ...] = ("atomic", "per_item")
OPERATION_STATUSES: tuple[str, ...] = (
    "prepared",
    "materializing",
    "materialized",
    "finalizing",
    "succeeded",
    "partial_failed",
    "failed",
    "stale",
)
# item 跟随同一阶段词汇；partial_failed 只供聚合兼容，正常 item 终态为 succeeded/failed/stale。
ITEM_STATUSES: tuple[str, ...] = OPERATION_STATUSES
ACTIVE_OPERATION_STATUSES: tuple[str, ...] = (
    "prepared",
    "materializing",
    "materialized",
    "finalizing",
)

_UUID = PG_UUID(as_uuid=True)
_DIGEST = sa.CHAR(64)
_TS = sa.DateTime(timezone=True)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class WorkpaperGenerationOperation(Base, TimestampMixin):
    """一次可恢复的底稿生成操作。"""

    __tablename__ = "workpaper_generation_operations"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    template_set_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("wp_template_set.id", ondelete="SET NULL"), nullable=True
    )
    failure_policy: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'")
    )
    request_hash: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    scope_revision: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default="prepared",
        server_default=sa.text("'prepared'"),
    )
    lease_token: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    attempt: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    progress_total: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    progress_done: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )

    receipt: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    public_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)

    __table_args__ = (
        CheckConstraint(
            _in_list("kind", OPERATION_KINDS),
            name="ck_wp_generation_operations_kind",
        ),
        CheckConstraint(
            _in_list("failure_policy", FAILURE_POLICIES),
            name="ck_wp_generation_operations_failure_policy",
        ),
        CheckConstraint(
            _in_list("status", OPERATION_STATUSES),
            name="ck_wp_generation_operations_status",
        ),
        CheckConstraint(
            "(kind = 'template_set' AND failure_policy = 'atomic') OR "
            "(kind = 'from_codes' AND failure_policy = 'per_item')",
            name="ck_wp_generation_operations_kind_policy",
        ),
        CheckConstraint(
            "attempt >= 0 AND progress_total >= 0 AND progress_done >= 0 "
            "AND progress_done <= progress_total",
            name="ck_wp_generation_operations_progress",
        ),
        CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_wp_generation_operations_lease_pair",
        ),
        Index(
            "ix_wp_generation_operations_project_status",
            "project_id", "status", "created_at",
        ),
        Index(
            "ix_wp_generation_operations_lease",
            "status", "lease_expires_at",
            postgresql_where=sa.text(
                _in_list("status", ACTIVE_OPERATION_STATUSES)
            ),
        ),
    )


class WorkpaperGenerationItem(Base):
    """生成操作内的一份底稿及其可恢复文件 manifest。"""

    __tablename__ = "workpaper_generation_items"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, default=uuid.uuid4
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(
        _UUID,
        ForeignKey("workpaper_generation_operations.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    wp_code: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    wp_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    audit_cycle: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    # Phase A 预留正式身份；此时目标行尚不存在，因此不能提前声明目标表外键。
    wp_index_id: Mapped[uuid.UUID] = mapped_column(_UUID, nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, nullable=False)
    template_source: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    template_fingerprint: Mapped[str | None] = mapped_column(
        _DIGEST, nullable=True
    )
    staging_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    final_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    from_template: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.text("false")
    )
    header_prepared: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.text("false")
    )
    header_issue: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default="prepared",
        server_default=sa.text("'prepared'"),
    )
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            _in_list("status", ITEM_STATUSES),
            name="ck_wp_generation_items_status",
        ),
        CheckConstraint(
            "ordinal >= 0",
            name="ck_wp_generation_items_ordinal",
        ),
        Index(
            "uq_wp_generation_items_operation_code",
            "operation_id", "wp_code", unique=True,
        ),
        Index(
            "uq_wp_generation_items_operation_ordinal",
            "operation_id", "ordinal", unique=True,
        ),
        Index(
            "ix_wp_generation_items_operation_status",
            "operation_id", "status", "ordinal",
        ),
    )
