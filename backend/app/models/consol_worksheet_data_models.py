"""ConsolWorksheetData ORM 模型 — 合并工作底稿数据存储

三层一致：V041 迁移 + 本 ORM + routers/consol_worksheet_data.py service
"""

import uuid
from datetime import datetime

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ConsolWorksheetData(Base):
    """合并工作底稿数据存储 — 通用 JSON 存储，支持所有 16 张表"""

    __tablename__ = "consol_worksheet_data"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_key: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "year", "sheet_key"),
        Index("ix_cwd_project_year", "project_id", "year"),
    )
