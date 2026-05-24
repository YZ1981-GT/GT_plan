"""自定义查询模板模型 [advanced-query-enhancements-p1p2 Task 8]

支持用户保存自定义查询配置（数据源/筛选条件/字段选择/选区/分页/排序），
并按"私有/团队/公开"控制可见性。

config JSONB 完整 schema（Req 15 AC3）：
  {project_id, year, source, sheet_name, cell_range, filter_text,
   conditions[], selected_columns[], available_columns[],
   page_size, sort_field, sort_order}

Validates: Requirements 15.1-15.5 (advanced-query-enhancements-p1p2)
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CustomQueryTemplate(Base):
    """自定义查询模板。

    - scope='private'：仅创建者可见
    - scope='team'：团队可见
    - scope='public'：全员共享
    - scope='global'：全员共享（legacy alias）
    - config 含完整查询参数（含 cell_range / sheet_name / page_size / sort）
    """

    __tablename__ = "custom_query_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    scope: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=sa.text("'private'")
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")
    )
    use_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    # creator_id is the canonical FK; created_by kept for backward compat
    creator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
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

    @property
    def owner_id(self) -> uuid.UUID:
        """Canonical owner: prefer creator_id, fallback to created_by."""
        return self.creator_id or self.created_by

    __table_args__ = (
        sa.Index("idx_custom_query_templates_scope", "scope", "updated_at"),
        sa.Index("idx_custom_query_templates_creator", "created_by", "updated_at"),
        sa.Index("idx_cqt_scope_updated", "scope", sa.desc("updated_at")),
        sa.Index("idx_cqt_creator_updated", "creator_id", sa.desc("updated_at")),
        sa.Index("idx_cqt_tags", "tags", postgresql_using="gin"),
    )
