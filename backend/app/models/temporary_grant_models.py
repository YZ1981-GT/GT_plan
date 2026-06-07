"""临时授权 ORM 模型

ADR-030: 独立表存储项目级临时授权记录。
字段：operation_code、grantee、approver、reason、expires_at。
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TemporaryGrant(TimestampMixin, Base):
    """临时授权记录

    项目经理/合伙人可为特定用户授予有限时间内的操作权限。
    过期后 is_active 自动置 False。
    """

    __tablename__ = "temporary_grants"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    operation_code: Mapped[str] = mapped_column(String(64), nullable=False)
    grantee: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    approver: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index(
            "idx_temporary_grants_active_lookup",
            "grantee", "project_id", "operation_code",
            postgresql_where="is_active = TRUE",
        ),
        Index(
            "idx_temporary_grants_expires_at",
            "expires_at",
            postgresql_where="is_active = TRUE",
        ),
        Index("idx_temporary_grants_project_id", "project_id"),
        Index("idx_temporary_grants_approver", "approver"),
    )

    @property
    def is_expired(self) -> bool:
        """检查授权是否已过期"""
        from datetime import timezone
        return datetime.now(timezone.utc) > self.expires_at
