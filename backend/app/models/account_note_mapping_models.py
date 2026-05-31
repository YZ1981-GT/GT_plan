"""AccountNoteMapping ORM 模型 — 科目→附注行映射

三层一致：V040 迁移 + 本 ORM + routers/account_note_mapping.py service
Bug 条件: C5 | 属性: H4
"""

import uuid
from datetime import datetime

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class AccountNoteMapping(Base):
    """科目→附注行映射 — 维护科目名称到附注表格行的映射关系"""

    __tablename__ = "account_note_mapping"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    section_id: Mapped[str] = mapped_column(String(50), nullable=False)
    row_name: Mapped[str] = mapped_column(String(200), nullable=False)
    col_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mapping_type: Mapped[str] = mapped_column(String(20), nullable=False, default="exact")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "account_name", "section_id", "row_name"),
        Index("ix_anm_proj", "project_id"),
    )
