"""WorkHourEntry ORM 模型 — Phase 7 F7: 工时填报粒度细化

三级粒度：循环/底稿/程序
"""

import enum
import uuid
from datetime import date as date_type, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class WorkHourEntryStatus(str, enum.Enum):
    """工时条目状态"""

    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class WorkHourEntry(Base):
    """工时填报条目（三级粒度）"""

    __tablename__ = "work_hour_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cycle: Mapped[str] = mapped_column(String(10), nullable=False)
    wp_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    procedure: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), server_default=text("'draft'"), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_whe_user_date", "user_id", "date"),
        Index("idx_whe_project_status", "project_id", "status"),
        Index("idx_whe_project_cycle", "project_id", "cycle"),
    )
