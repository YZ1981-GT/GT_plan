"""ProjectWorkpaperSheetOverride ORM 模型

对应 Alembic 迁移 project_override_template_version_20260525.py DDL ④。
项目级底稿 sheet 归类覆盖：自定义底稿/特殊归类场景。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProjectWorkpaperSheetOverride(Base):
    """项目级底稿 sheet 归类覆盖

    当用户上传自定义底稿或需要项目级特殊归类时，
    通过此表覆盖模板级 workpaper_sheet_classification 的默认归类。
    """

    __tablename__ = "project_workpaper_sheet_override"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    wp_code: Mapped[str] = mapped_column(String(50), nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    class_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scope_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    schema_override: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "project_id", "wp_code", "sheet_name",
            name="uq_pwpso_project_wp_sheet",
        ),
        Index("idx_pwpso_project_wp", "project_id", "wp_code"),
    )
