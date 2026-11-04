"""科目余额表 / 序时账人工修改日志（迁移 V260，spec citar-table-manual-edit R3~R5）。

修改直接写当前数据集的 ``tb_balance`` / ``tb_ledger`` 行（试算表、底稿取数、报表等读取方不用改）；
本表记每次修改前后的字段值，用于标出改过的行、显示原值、恢复导入原值。
重新导入账套会生成新数据集，旧数据集的修改不带过去（按 ``dataset_id`` 区分）。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

TABLE_BALANCE = "balance"
TABLE_LEDGER = "ledger"
ACTION_EDIT = "edit"
ACTION_RESTORE = "restore"
ACTION_CASCADE = "cascade"


class LedgerManualEdit(Base):
    __tablename__ = "ledger_manual_edits"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    table_name: Mapped[str] = mapped_column(String(20), nullable=False)
    row_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    before: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    after: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    edited_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_ledger_manual_edits_project_year_table", "project_id", "year", "table_name"),
        Index("idx_ledger_manual_edits_row", "row_id"),
    )
