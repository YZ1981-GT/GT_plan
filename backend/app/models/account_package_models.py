"""科目工作包程序状态 ORM 模型

对应迁移 V063__account_package_program_status.sql。
跟踪科目工作包中每个审计程序的执行状态、证据、复核结果和结论。

Requirements: 2.3, 5.1
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AccountPackageProgramStatus(TimestampMixin, Base):
    """科目工作包程序状态

    记录每个审计程序的适用性、执行状态、证据、复核和结论。
    以 (project_id, account_package_id, program_code) 为唯一键。
    """

    __tablename__ = "account_package_program_status"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    account_package_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="工作包 ID，如 D1_notes_receivable"
    )
    program_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="程序编号，如 D1A, D1-12"
    )

    # ─── 3.2: applicable/status/evidence/review/conclusion ────────────────
    applicable: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否适用"
    )
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False,
        comment="pending|in_progress|completed|reviewed",
    )
    evidence: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="审计证据描述"
    )
    review_result: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="pass|fail|conditional"
    )
    conclusion: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="程序结论"
    )

    # ─── 3.3: 留痕字段 ──────────────────────────────────────────────────────
    not_applicable_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="不适用理由（applicable=False 时必填）"
    )
    reviewer: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("staff_members.id"),
        nullable=True,
        comment="复核人",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="复核时间"
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("staff_members.id"),
        nullable=True,
        comment="最后更新人",
    )

    # ─── 约束和索引 ─────────────────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint(
            "project_id", "account_package_id", "program_code",
            name="uq_acct_pkg_program_status",
        ),
        Index(
            "idx_acct_pkg_program_project",
            "project_id", "account_package_id",
        ),
    )
