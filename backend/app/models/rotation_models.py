"""合伙人轮换 Override ORM 模型

Refinement Round 1 — 需求 11：关键合伙人轮换检查。

设计要点：
- 使用 TimestampMixin
- 需合规合伙人 + 首席风控合伙人双签才能 override
- override_expires_at 到期后自动失效
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PartnerRotationOverride(Base, TimestampMixin):
    """合伙人轮换 Override

    当签字合伙人/EQCR 连续审计同一客户超过轮换上限时，
    需合规合伙人 + 首席风控合伙人双签 override 才能继续委派。

    Refinement Round 1 — 需求 11。
    """

    __tablename__ = "partner_rotation_overrides"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_years: Mapped[int] = mapped_column(nullable=False)
    override_reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by_compliance_partner: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_by_chief_risk_partner: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    override_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index(
            "idx_rotation_overrides_staff_client",
            "staff_id",
            "client_name",
        ),
    )
