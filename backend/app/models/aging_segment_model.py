"""账龄段枚举配置 ORM 模型

对应迁移 V091__aging_segments.sql。
每个底稿（wp_index_id）最多一条账龄段配置记录，
存储预设方案名 + 有序段名 JSONB 列表。

Requirements: 4.11
"""

import uuid

from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AgingSegment(Base, TimestampMixin):
    """账龄段枚举配置（每个底稿一条，关联 wp_index_id）"""

    __tablename__ = "aging_segments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wp_index_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("wp_index.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    preset: Mapped[str] = mapped_column(
        String(20), nullable=False, default="CUSTOM"
    )
    segments: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
