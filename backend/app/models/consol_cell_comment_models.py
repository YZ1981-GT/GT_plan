"""ConsolCellComment ORM 模型 — 单元格批注与复核标记

三层一致：V040 迁移 + 本 ORM + routers/consol_cell_comments.py service
Bug 条件: C5 | 属性: H4
"""

import uuid
from datetime import datetime

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ConsolCellComment(Base):
    """单元格批注与复核标记 — 支持所有模块的单元格级批注和复核状态持久化"""

    __tablename__ = "consol_cell_comments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    sheet_key: Mapped[str] = mapped_column(String(100), nullable=False)
    row_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    col_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    comment_type: Mapped[str] = mapped_column(String(20), nullable=False, default="comment")
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    row_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    col_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "project_id", "year", "module", "sheet_key",
            "row_idx", "col_idx", "comment_type"
        ),
        Index("ix_cc_proj_year_mod", "project_id", "year", "module"),
    )
