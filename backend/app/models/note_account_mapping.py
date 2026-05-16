"""NoteAccountMapping ORM 模型 — 附注科目对照映射

Requirements: 23.1, 23.2, 23.3
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NoteAccountMapping(Base):
    """附注科目对照映射 — 报表行次 → 附注章节 → 表格的三级映射"""

    __tablename__ = "note_account_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)  # soe / listed
    report_row_code: Mapped[str] = mapped_column(String(50), nullable=False)  # BS-002
    note_section_code: Mapped[str] = mapped_column(String(100), nullable=False)
    table_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_role: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 余额/宽表/交叉/其中项/描述
    wp_code: Mapped[str | None] = mapped_column(String(30), nullable=True)  # E1/D2/F2
    fetch_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)  # total/detail/category/change
