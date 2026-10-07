"""ConsolNoteData ORM 模型 — 合并附注用户数据存储

三层一致：V041 迁移（+ V172 is_stale + V182 cell_state）+ 本 ORM + routers/consol_note_sections.py service
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base

#: 合并附注单元格状态（与 formula_push 三态对等）
CONSOL_NOTE_CELL_STATES: tuple[str, ...] = ("auto", "manual", "locked")


class ConsolNoteData(Base):
    """合并附注用户数据存储 — 按项目+年度+章节存储用户编辑的附注数据"""

    __tablename__ = "consol_note_data"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    section_id: Mapped[str] = mapped_column(String(50), nullable=False)
    node_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # V172：合并推送后置真（合并数已变化，附注数据待更新）；「按公式填入」后清除
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # V182：持久化状态（与 formula_push 三态对等）
    cell_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="auto", server_default=text("'auto'")
    )
    # V182：被锁定的单元格坐标列表 [{row_index, col_index}]
    locked_cells: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    # V182：最近一次公式刷新的运行批次
    last_formula_run_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    # V182：最近一次公式刷新写入的值快照（用于对比 current vs formula）
    last_formula_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "cell_state IN ('auto', 'manual', 'locked')",
            name="ck_cnd_cell_state",
        ),
        # V177：旧项目级兼容行与节点级行分别做部分唯一约束；SQLite 测试库也保持同一语义。
        Index(
            "uq_cnd_legacy_project_year_section",
            "project_id", "year", "section_id",
            unique=True,
            postgresql_where=text("node_key IS NULL"),
            sqlite_where=text("node_key IS NULL"),
        ),
        Index(
            "uq_cnd_project_year_section_node",
            "project_id", "year", "section_id", "node_key",
            unique=True,
            postgresql_where=text("node_key IS NOT NULL"),
            sqlite_where=text("node_key IS NOT NULL"),
        ),
        Index("ix_cnd_proj_year", "project_id", "year"),
    )
