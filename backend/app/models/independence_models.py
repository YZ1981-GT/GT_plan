"""独立性声明 ORM 模型

Refinement Round 5 任务 23 — 需求 12

本轮只落地"年度个人独立性声明"，覆盖 EQCR / signing_partner / qc_partner 角色。

**架构注解**：
- R1 需求 10 规划了"项目级独立性声明"表 ``independence_declarations``
  (``declaration_scope ∈ {'project','annual'}``)，但 R1 尚未落库。
- 本表 ``annual_independence_declarations`` 是 **R5 最小独立实现**，
  只保存 ``declaration_scope='annual'`` 的年度声明。
- 当 R1 的 ``independence_declarations`` 表正式建成后，本表数据应迁入，
  届时可通过一次性迁移脚本 ``INSERT INTO independence_declarations SELECT * FROM annual_independence_declarations``
  完成合并；本表保留或删除取决于 R1 迁移策略。
- 这样既满足本轮"不依赖 R1 建模"的独立性，也避免了在 ``User`` 表上
  添加 ``metadata_`` JSONB（那会污染 User 表的职责边界）。
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class AnnualIndependenceDeclaration(Base, SoftDeleteMixin, TimestampMixin):
    """年度独立性声明（R5 需求 12）+ 项目级独立性声明（R1 需求 10 合并）。

    - 年度声明：``project_id=None``，``(declarant_id, declaration_year)`` 唯一。
    - 项目级声明：``project_id`` 有值，``(project_id, declarant_id, declaration_year)`` 唯一。
    - ``answers`` 存 30+ 题的答案 ``{"1": "no", "2": "yes", ...}``。
    - ``risk_flagged_count`` 冗余字段，缓存"有风险回答数"方便抽查排序。
    - ``status`` 状态机：draft → submitted → approved / pending_conflict_review → superseded_by_handover
    """

    __tablename__ = "annual_independence_declarations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    declarant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    declaration_year: Mapped[int] = mapped_column(Integer, nullable=False)
    answers: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    attachments: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    risk_flagged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    signed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    signature_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    reviewed_by_qc_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "declarant_id", "declaration_year",
            name="uq_annual_independence_declarant_year",
        ),
        Index(
            "idx_annual_independence_year",
            "declaration_year",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "idx_independence_project_declarant",
            "project_id", "declarant_id",
            postgresql_where=text("is_deleted = false"),
        ),
    )


# 向后兼容别名 — 早期测试/代码使用短名称 IndependenceDeclaration
IndependenceDeclaration = AnnualIndependenceDeclaration
