"""公式推送引擎 ORM（对应迁移 V169）。

spec: .kiro/specs/chain-closure-phase2-formula-push-engine（需求 2.6 / 3.2）

* :class:`FormulaPushState` —— 每个推送目标一行，``(project_id, year, addr_id)`` 唯一。
  ``last_pushed_value`` 是可编辑目标三态判定的依据：当前值 ≠ 它 ⇒ 用户改过，不再覆盖。
* :class:`FormulaPushRun` —— 每次运行一行（触发来源 / 计数 / 逐项明细）。

``state`` / ``status`` 的取值集合与 ``app.services.formula_push.policy`` 同源，
由 ``tests/test_formula_push_schema_contract.py`` 钉死 DDL CHECK == ORM CHECK == policy 常量。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

#: 目标三态（+ pending_confirm）。改动须同步 V169 的 CHECK 与 policy.STATES。
PUSH_STATES: tuple[str, ...] = ("auto", "manual", "locked", "pending_confirm")
#: 运行状态。改动须同步 V169 的 CHECK。
RUN_STATUSES: tuple[str, ...] = ("running", "succeeded", "partial", "failed")
#: 目标域。
PUSH_DOMAINS: tuple[str, ...] = ("workpaper", "note")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class FormulaPushRun(Base):
    """公式推送运行记录（面板「最近推送」）。"""

    __tablename__ = "formula_push_run"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # TRIAL_BALANCE_UPDATED / WORKPAPER_SAVED / manual
    trigger_source: Mapped[str] = mapped_column(String(40), nullable=False)
    # 手动触发的用户；事件触发为 NULL
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running", server_default=sa.text("'running'")
    )
    written_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    unchanged_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    kept_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    skipped_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'")
    )
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", RUN_STATUSES), name="ck_formula_push_run_status"),
        Index("idx_formula_push_run_project_year", "project_id", "year", "started_at"),
    )


class FormulaPushState(Base):
    """公式推送目标级状态。"""

    __tablename__ = "formula_push_state"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # 底稿域 E1/E1-1/<item_id>[<row_id>].<field>；附注域 note://<section>/<table>/<row>.<end|prior>
    addr_id: Mapped[str] = mapped_column(String(512), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(20), nullable=False)
    wp_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("working_paper.id", ondelete="CASCADE"), nullable=True
    )
    note_section: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # NULL = 从未推送（三态判定的「首次」分支）。
    # ``none_as_null``：Python ``None`` 落 SQL NULL 而非 JSON ``null`` —— 否则
    # 「从未推送」（SQL NULL）与「推送过空值」在 SQL 里是两种形态，``IS NULL`` 查询会漏掉后者。
    last_pushed_value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    last_formula_value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    current_value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="auto", server_default=sa.text("'auto'")
    )
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("formula_push_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 最近一次采用 / 锁定的用户；引擎写入为 NULL
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "year", "addr_id", name="uq_formula_push_state_addr"),
        CheckConstraint(_in_list("state", PUSH_STATES), name="ck_formula_push_state_state"),
        CheckConstraint(_in_list("domain", PUSH_DOMAINS), name="ck_formula_push_state_domain"),
        Index("idx_formula_push_state_project_year_state", "project_id", "year", "state"),
    )
