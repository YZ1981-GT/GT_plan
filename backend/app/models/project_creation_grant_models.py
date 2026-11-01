"""精确企业代码的经理建项授权（迁移 V233）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class ProjectCreationGrant(Base, SoftDeleteMixin, TimestampMixin):
    """admin 授予 manager 对一个精确 USCC 的项目创建权。"""

    __tablename__ = "project_creation_grants"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    grantee_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    company_code: Mapped[str] = mapped_column(sa.String(18), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    valid_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    source: Mapped[str] = mapped_column(
        sa.String(48), nullable=False, default="admin", server_default=sa.text("'admin'")
    )
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT")
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        sa.CheckConstraint("version >= 1", name="ck_project_creation_grants_version"),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_project_creation_grants_valid_window",
        ),
        sa.CheckConstraint(
            "length(company_code) = 18 AND company_code = upper(trim(company_code))",
            name="ck_project_creation_grants_code_shape",
        ),
        # V234 另有 PG 专用约束 ck_project_creation_grants_code_checksum：
        # 未撤销行须通过 gt_is_valid_uscc（与 uscc_validator 同算法）。依赖 PG 函数，
        # 不在 ORM 声明，避免 SQLite 测试库建表失败；应用层写入同样先过 validate_uscc。
        sa.Index(
            "uq_project_creation_grants_active",
            "grantee_user_id", "company_code", unique=True,
            postgresql_where=sa.text("is_deleted = false"),
            sqlite_where=sa.text("is_deleted = 0"),
        ),
        sa.Index(
            "ix_project_creation_grants_grantee_valid",
            "grantee_user_id", "valid_until",
            postgresql_where=sa.text("is_deleted = false"),
        ),
    )


__all__ = ["ProjectCreationGrant"]
