"""附注章节裁剪 ORM 模型

Phase 9 Task 9.27
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class NoteSectionInstance(Base, SoftDeleteMixin, TimestampMixin):
    """附注章节实例（裁剪后的章节）"""

    __tablename__ = "note_section_instances"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)  # soe / listed
    section_number: Mapped[str] = mapped_column(String(20), nullable=False)
    section_title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="retain")  # retain / skip / not_applicable
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        Index("idx_note_section_project", "project_id", "template_type",
              postgresql_where=text("is_deleted = false")),
    )


class NoteTrimScheme(Base, SoftDeleteMixin, TimestampMixin):
    """附注裁剪方案"""

    __tablename__ = "note_trim_schemes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scheme_name: Mapped[str] = mapped_column(String(200), nullable=False)
    trim_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
