"""QC 案例库 ORM 模型

Refinement Round 3 — 需求 8：失败案例库。

质控将典型问题底稿脱敏后发布为案例，供新人学习。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class QcCaseLibrary(Base, SoftDeleteMixin, TimestampMixin):
    """QC 案例库条目

    存储脱敏后的典型问题案例，关联审计准则编号。
    对所有用户开放只读，新员工培训可用。

    脱敏规则：
    - 客户名替换为 [客户A] / [客户B]
    - 金额保留级次但加扰动 ±5%

    Refinement Round 3 — 需求 8。
    """

    __tablename__ = "qc_case_library"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 案例分类，如 '底稿完整性' / '数据准确性'
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'blocking' | 'warning' | 'info'
    description: Mapped[str] = mapped_column(Text, nullable=False)
    lessons_learned: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # 经验教训
    related_wp_refs: Mapped[list | None] = mapped_column(
        JSONB, nullable=True
    )  # 脱敏后的底稿引用 [{wp_code, cycle, snippet}]
    related_standards: Mapped[list | None] = mapped_column(
        JSONB, nullable=True
    )  # 关联准则 [{code: '1301', section: '6.2', name: '审计工作底稿'}]
    published_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    review_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )  # 阅读计数

    __table_args__ = (
        Index("idx_qc_case_library_category", "category"),
        Index("idx_qc_case_library_severity", "severity"),
        Index("idx_qc_case_library_published_at", "published_at"),
        Index(
            "idx_qc_case_library_active",
            "category",
            "severity",
            postgresql_where=text("is_deleted = false"),
        ),
    )
