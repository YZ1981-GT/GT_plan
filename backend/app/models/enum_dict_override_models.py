"""枚举字典覆盖 ORM 模型 — DT-3 方案 B

V015 迁移配套模型。仅允许覆盖 label/color，value 由代码锁定。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EnumDictOverride(Base):
    """枚举字典覆盖（label / color 可改，value 不可改）"""

    __tablename__ = "enum_dict_overrides"

    dict_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(64), primary_key=True)
    label_override: Mapped[str | None] = mapped_column(String(255), nullable=True)
    color_override: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
