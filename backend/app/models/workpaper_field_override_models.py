"""统一字段覆盖存储 ORM 模型

对应迁移 V076__workpaper_field_overrides.sql。
多个底稿模块共享的"系统自动值+用户可覆盖"存储。
scope 区分底稿域（如 'procedure_table:A1'、'review:A23'）。
"""

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WorkpaperFieldOverride(Base, TimestampMixin):
    """统一字段覆盖值

    - project_id + year + scope + item_key + field 联合唯一
    - value 为 JSONB，可存字符串/数字/布尔/对象
    """

    __tablename__ = "workpaper_field_overrides"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    item_key: Mapped[str] = mapped_column(String(100), nullable=False)
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_field_overrides_scope", "project_id", "year", "scope"),
    )
