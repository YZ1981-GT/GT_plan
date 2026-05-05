"""独立性声明 ORM 模型

Refinement Round 1 — 需求 10：独立性声明结构化。

设计要点：
- 使用 TimestampMixin（有 created_at / updated_at）
- 不使用 SoftDeleteMixin（声明是永久记录，不可软删除）
- answers 为 JSONB 存储 20+ 问题答案
- signature_record_id FK 到 signature_records.id 留痕
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class IndependenceDeclaration(Base, TimestampMixin):
    """独立性声明

    项目组核心成员（signing_partner / manager / qc / eqcr）均需单独提交，
    缺一个都阻断 sign_off gate。

    状态流转：draft → submitted → pending_conflict_review → approved

    Refinement Round 1 — 需求 10。
    """

    __tablename__ = "independence_declarations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    declarant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    declaration_year: Mapped[int] = mapped_column(nullable=False)
    answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    attachments: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    signature_record_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("signature_records.id"),
        nullable=True,
    )
    reviewed_by_qc_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        server_default=text("'draft'"),
        nullable=False,
    )  # 'draft' | 'submitted' | 'pending_conflict_review' | 'approved'

    __table_args__ = (
        Index(
            "idx_independence_declarations_project",
            "project_id",
            "declaration_year",
        ),
        Index(
            "idx_independence_declarations_declarant",
            "declarant_id",
            "project_id",
        ),
        Index("idx_independence_declarations_status", "status"),
    )
