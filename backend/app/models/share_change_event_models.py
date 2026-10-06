"""ShareChangeEvent ORM 模型 — 动态股比变动事件。

spec: consol-node-key-isolation-and-shared-context 任务 9.1
设计: §十三（ADR-CNSC-009~010）

每个事件代表一次股比变动（购买少数股权、不丧失控制权处置、增资、减持等），
稳定 ID 不因排序或插行变化。排序键 = (effective_date, sequence, id)。

三层一致：V180 迁移 + 本 ORM + routers/share_change_events.py (Phase C-2)
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ShareChangeEventStatus(str, enum.Enum):
    """事件复核状态（复用现有审批链语义）。"""
    draft = "draft"
    approved = "approved"
    revoked = "revoked"


class ShareChangeEvent(Base):
    """动态股比变动事件。

    设计 §十三.1：1~N 事件模型，稳定 ID、日期、序号、前后比例、来源、状态。
    """

    __tablename__ = "share_change_event"

    # ── 主键与归属 ─────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String(50), nullable=False)
    node_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── 排序与身份 ─────────────────────────────────────────────────────────
    effective_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    sequence: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )

    # ── 比例（百分数 0~100，精度 6 位小数） ────────────────────────────────
    before_ratio: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(12, 6), nullable=True
    )
    after_ratio: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(12, 6), nullable=True
    )
    ratio_delta: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(12, 6), nullable=True
    )

    # ── 业务分类 ───────────────────────────────────────────────────────────
    change_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 2), nullable=True)
    equity_adjustment: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(18, 2), nullable=True
    )

    # ── 来源溯源（G7 幂等 upsert 用） ──────────────────────────────────────
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_row_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_sheet_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── 状态与版本 ─────────────────────────────────────────────────────────
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default=sa.text("'draft'")
    )
    calculation_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )

    # ── 扩展数据（资本公积分拆等） ─────────────────────────────────────────
    detail: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    # ── 审计 ───────────────────────────────────────────────────────────────
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # 同一来源行只能产生一个事件（G7 幂等 upsert）
        UniqueConstraint(
            "project_id", "year", "company_code", "source_type", "source_row_id",
            name="uq_share_change_event_source",
        ),
        Index(
            "ix_sce_project_year_company",
            "project_id", "year", "company_code",
        ),
        Index(
            "ix_sce_sort",
            "project_id", "year", "company_code",
            "effective_date", "sequence", "id",
        ),
        CheckConstraint(
            "review_status IN ('draft', 'approved', 'revoked')",
            name="ck_sce_review_status",
        ),
    )
