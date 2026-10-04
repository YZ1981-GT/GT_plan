"""合并推送与合并附注公式 ORM（对应迁移 V172）。

spec: .kiro/specs/consol-elimination-single-source-push（需求 6.1 / 8.1）

* :class:`ConsolPushRun` —— 每次合并推送一行（触发来源 / 状态 / 逐项目逐步骤结果 / 警告）。
* :class:`ConsolNoteFormula` —— 合并附注单元格取数公式（模板级，按 soe / listed 区分）。

取值集合（``PUSH_RUN_STATUSES`` / ``NOTE_FORMULA_SOURCES`` / ``NOTE_TEMPLATE_TYPES``）与 V172 的 CHECK 同源，
由 ``tests/test_consol_push_schema_contract.py`` 钉死 DDL == ORM。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

#: 推送运行状态。改动须同步 V172 的 CHECK。
PUSH_RUN_STATUSES: tuple[str, ...] = ("running", "succeeded", "partial", "failed")
#: 合并附注公式来源：seed = 自动种子；manual = 人工维护（种子不覆盖人工）。
NOTE_FORMULA_SOURCES: tuple[str, ...] = ("seed", "manual")
#: 合并附注模板类型。
NOTE_TEMPLATE_TYPES: tuple[str, ...] = ("soe", "listed")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class ConsolPushRun(Base):
    """合并推送运行记录（公式管理「合并推送」页）。"""

    __tablename__ = "consol_push_run"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # elimination_approved / elimination_revoked / formula_changed / manual
    trigger_source: Mapped[str] = mapped_column(String(40), nullable=False)
    # 手动触发的用户；事件触发为 NULL
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running", server_default=text("'running'")
    )
    # [{project_id, project_name, step, status, detail}]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    warnings: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(_in_list("status", PUSH_RUN_STATUSES), name="ck_consol_push_run_status"),
        Index("idx_consol_push_run_project_year", "project_id", "year", "started_at"),
    )


class ConsolNoteFormula(Base):
    """合并附注单元格取数公式（语法同报表公式：TB / SUM_TB / REPORT / ROW）。"""

    __tablename__ = "consol_note_formula"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    row_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    col_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    formula: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", server_default=text("'manual'")
    )
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(_in_list("source", NOTE_FORMULA_SOURCES), name="ck_consol_note_formula_source"),
        CheckConstraint(_in_list("template_type", NOTE_TEMPLATE_TYPES), name="ck_consol_note_formula_template"),
        Index(
            "ux_consol_note_formula_cell",
            "template_type", "section_id", "row_index", "col_index",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )
