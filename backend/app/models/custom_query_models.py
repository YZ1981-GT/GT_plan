"""自定义查询模板模型 [template-library-coordination Sprint 6 Task 6.6]

支持用户保存自定义查询配置（数据源/筛选条件/字段选择），并按"私有/全局共享"控制可见性。

Validates: Requirements 22.7, 22.8 (template-library-coordination)
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CustomQueryTemplate(Base):
    """自定义查询模板。

    - scope='private'：仅创建者可见
    - scope='global'：全员共享
    - config 含 filters / fields / limit / source 等完整查询参数
    """

    __tablename__ = "custom_query_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    data_source: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sa.text("'private'")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index("idx_custom_query_templates_scope", "scope", "updated_at"),
        sa.Index("idx_custom_query_templates_creator", "created_by", "updated_at"),
    )
