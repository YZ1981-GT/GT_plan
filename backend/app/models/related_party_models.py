"""关联方最小建模 ORM 模型

Refinement Round 5 — 需求 2.4 为 EQCR 关联方 Tab 提供最小 CRUD 承载。
R6+ 再做自动识别（如基于关键词扫描 / 导入外部关联方清单）。

对应 Alembic 迁移脚本 ``round5_eqcr_20260505.py``。
"""

import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


# ---------------------------------------------------------------------------
# 关联方注册表
# ---------------------------------------------------------------------------


class RelatedPartyRegistry(Base, SoftDeleteMixin, TimestampMixin):
    """关联方主数据（项目级）。

    ``relation_type`` 允许值（前后端约定）：
    ``parent`` / ``subsidiary`` / ``associate`` / ``joint_venture`` /
    ``key_management`` / ``family_member`` / ``other``。
    """

    __tablename__ = "related_party_registry"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_controlled_by_same_party: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_related_party_registry_project",
            "project_id",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "uq_related_party_registry_project_name",
            "project_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )


# ---------------------------------------------------------------------------
# 关联方交易
# ---------------------------------------------------------------------------


class RelatedPartyTransaction(Base, SoftDeleteMixin, TimestampMixin):
    """关联方交易明细。

    ``transaction_type`` 允许值（前后端约定）：
    ``sales`` / ``purchase`` / ``loan`` / ``guarantee`` / ``service`` /
    ``asset_transfer`` / ``other``。

    ``evidence_refs`` 记录审计证据关联（JSONB，如底稿 ID / 附件 ID）。
    """

    __tablename__ = "related_party_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    related_party_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("related_party_registry.id"),
        nullable=False,
    )
    amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2), nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_arms_length: Mapped[bool | None] = mapped_column(nullable=True)
    evidence_refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index(
            "idx_rp_transactions_project",
            "project_id",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "idx_rp_transactions_party",
            "related_party_id",
            postgresql_where=text("is_deleted = false"),
        ),
    )
