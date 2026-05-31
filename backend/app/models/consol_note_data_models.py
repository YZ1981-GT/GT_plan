"""ConsolNoteData ORM 模型 — 合并附注用户数据存储

三层一致：V041 迁移 + 本 ORM + routers/consol_note_sections.py service
"""

import uuid
from datetime import datetime

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ConsolNoteData(Base):
    """合并附注用户数据存储 — 按项目+年度+章节存储用户编辑的附注数据"""

    __tablename__ = "consol_note_data"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    section_id: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "year", "section_id"),
        Index("ix_cnd_proj_year", "project_id", "year"),
    )
