"""WorkpaperTemplateVersion ORM 模型

对应 Alembic 迁移 wp_template_version_20260525.py。
管理致同底稿模板版本（v2024 → v2025 → v2026 年度修订），支持多版本共存。
"""

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkpaperTemplateVersion(Base):
    """底稿模板版本

    致同每年发布修订版（v2024 → v2025 → v2026），同一 wp_code 在不同版本里
    sheet 数量/字段/公式可能差异。项目立项后绑定一个版本。
    """

    __tablename__ = "workpaper_template_version"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True
    )
    release_date: Mapped[date] = mapped_column(
        sa.Date, nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'致同总所'")
    )
    is_current: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=text("false")
    )
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workpaper_template_version.id", ondelete="SET NULL"),
        nullable=True,
    )
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now()
    )
