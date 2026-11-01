"""报表生成运行与合并不可变 artifact ORM。

`report_generation_run` 是 formula-provenance-envelope 约定的共享运行记录；本轮只落合并报表域
最小闭环。`rows_json` 保存一次运行的规范行快照，避免给 `financial_report` 叠加历史重复行，
后者继续作为全平台兼容的“当前槽位”，并用 run_id/provenance 指向生成它的运行。
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

from app.models.base import Base

REPORT_RUN_STATUSES = ("building", "succeeded", "failed", "stale")
ARTIFACT_STATUSES = ("generating", "ready", "failed")
ARTIFACT_KINDS = ("report_excel", "consol_workpaper")

_UUID = PG_UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_DIGEST = sa.CHAR(64)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class ReportGenerationRun(Base):
    """一次报表计算的不可变运行摘要与规范行快照。"""

    __tablename__ = "report_generation_run"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    trigger: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("consol_operation.id", ondelete="SET NULL"), nullable=True,
    )
    operation_revision: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    node_key: Mapped[str | None] = mapped_column(sa.String(160), nullable=True)
    applicable_standard: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default="building", server_default=sa.text("'building'"),
    )
    calc_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    changed_rows: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=sa.text("0"))
    recomputed_rows: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=sa.text("0"))
    failed_rows: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=sa.text("0"))
    row_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default=sa.text("0"))
    report_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'"),
    )
    input_digest: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    row_digest: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    rows_json: Mapped[dict[str, list[dict[str, Any]]]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'"),
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'"),
    )
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    finished_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(),
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", REPORT_RUN_STATUSES), name="ck_report_generation_run_status"),
        CheckConstraint(
            "operation_revision IS NULL OR operation_revision > 0",
            name="ck_report_generation_run_revision",
        ),
        CheckConstraint(
            "changed_rows >= 0 AND recomputed_rows >= 0 AND failed_rows >= 0 AND row_count >= 0",
            name="ck_report_generation_run_counts",
        ),
        CheckConstraint(
            "input_digest IS NULL OR length(input_digest) = 64",
            name="ck_report_generation_run_input_digest",
        ),
        CheckConstraint(
            "row_digest IS NULL OR length(row_digest) = 64",
            name="ck_report_generation_run_row_digest",
        ),
        Index(
            "ux_report_generation_run_operation_revision",
            "operation_id", "operation_revision", "project_id", "node_key",
            unique=True,
            postgresql_where=sa.text("operation_id IS NOT NULL"),
            sqlite_where=sa.text("operation_id IS NOT NULL"),
        ),
        Index(
            "ix_report_generation_run_project_year",
            "project_id", "year", "status", "finished_at",
        ),
    )


class ConsolArtifact(Base):
    """绑定已发布 report run 的不可变合并 Excel artifact。"""

    __tablename__ = "consol_artifact"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("consol_operation.id", ondelete="SET NULL"), nullable=True,
    )
    operation_revision: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("report_generation_run.id", ondelete="RESTRICT"), nullable=False,
    )
    node_key: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default="generating", server_default=sa.text("'generating'"),
    )
    file_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    content_type: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'"),
    )
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    ready_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(),
    )

    __table_args__ = (
        CheckConstraint(_in_list("kind", ARTIFACT_KINDS), name="ck_consol_artifact_kind"),
        CheckConstraint(_in_list("status", ARTIFACT_STATUSES), name="ck_consol_artifact_status"),
        CheckConstraint(
            "operation_revision IS NULL OR operation_revision > 0",
            name="ck_consol_artifact_revision",
        ),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_consol_artifact_size",
        ),
        CheckConstraint(
            "sha256 IS NULL OR length(sha256) = 64",
            name="ck_consol_artifact_sha256",
        ),
        CheckConstraint(
            "status <> 'ready' OR (storage_path IS NOT NULL AND size_bytes IS NOT NULL "
            "AND sha256 IS NOT NULL AND ready_at IS NOT NULL)",
            name="ck_consol_artifact_ready_fields",
        ),
        Index(
            "ux_consol_artifact_report_kind_node",
            "report_run_id", "kind", "node_key", unique=True,
        ),
        Index(
            "ix_consol_artifact_project_year",
            "project_id", "year", "created_at",
        ),
    )


__all__ = [
    "ARTIFACT_KINDS",
    "ARTIFACT_STATUSES",
    "REPORT_RUN_STATUSES",
    "ConsolArtifact",
    "ReportGenerationRun",
]
