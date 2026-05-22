"""ReviewTemplate ORM 模型 — Phase 7 F4: 复核意见模板库"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ReviewTemplate(Base):
    """复核意见模板"""

    __tablename__ = "review_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    applicable_cycles: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    priority_tag: Mapped[str] = mapped_column(
        String(20), server_default=text("'suggest'")
    )
    use_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_review_templates_priority",
            "priority_tag",
            postgresql_where=text("is_deleted = false"),
        ),
    )
