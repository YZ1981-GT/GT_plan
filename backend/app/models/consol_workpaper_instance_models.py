"""合并薄底稿壳实例 ORM（consolidation-run-and-workpaper-lifecycle-closure 批 6 / ADR-CRW-006）。

`consol_workpaper_instance` 把合并项目/年度与其 A3-CONSOL 薄底稿壳（``WpIndex`` + ``WorkingPaper``）
关联，并记录最近一次正式 ``consol_operation`` 与不可变 ``consol_artifact`` 引用及壳版本号。
业务数据仍以 ``consol_worksheet_data`` / ``consol_trial`` / ``financial_report`` /
``consol_note_data`` 为权威，本表不复制业务 JSON，只做身份与最新产物指针。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_UUID = PG_UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)


class ConsolWorkpaperInstance(Base):
    """合并项目/年度与 A3-CONSOL 薄底稿壳的关联及最近正式产物指针。"""

    __tablename__ = "consol_workpaper_instance"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    working_paper_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper.id", ondelete="CASCADE"), nullable=False,
    )
    wp_index_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("wp_index.id", ondelete="CASCADE"), nullable=False,
    )
    latest_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("consol_operation.id", ondelete="SET NULL"), nullable=True,
    )
    latest_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("consol_artifact.id", ondelete="SET NULL"), nullable=True,
    )
    version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1"),
    )
    created_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(),
    )

    __table_args__ = (
        CheckConstraint("version > 0", name="ck_consol_workpaper_instance_version"),
        Index(
            "ux_consol_workpaper_instance_project_year",
            "project_id", "year", unique=True,
        ),
        Index(
            "ux_consol_workpaper_instance_working_paper",
            "working_paper_id", unique=True,
        ),
    )


__all__ = ["ConsolWorkpaperInstance"]
