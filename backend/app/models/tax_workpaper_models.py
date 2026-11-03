"""税审底稿手工填写值（迁移 V230）。

一行 = 一个项目、一个年度、一张底稿（索引编号）的全部手工值；表头参数存 ``sheet_code='__params__'``。
``inputs`` = {样表 sheet 名: {单元格地址: 值}}，值为数字 / 文字 / null（null = 手工清空）。
``version`` 每次保存加 1，保存时带上读到的版本，不一致返回冲突（不静默覆盖他人修改）。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

PARAMS_SHEET_CODE = "__params__"
# 鉴证报告自己的填写项（报告日期等，spec citar-assurance-report-menus），不进底稿计算
ASSURANCE_SHEET_CODE = "__assurance__"
RESERVED_SHEET_CODES = frozenset({PARAMS_SHEET_CODE, ASSURANCE_SHEET_CODE})


class TaxWorkpaperInput(Base):
    __tablename__ = "tax_workpaper_inputs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_code: Mapped[str] = mapped_column(String(64), nullable=False)
    # server_default 用纯字符串：PG 隐式转 jsonb、SQLite 测试库也能建表（V230 本身写的是 '{}'::jsonb）
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("uq_tax_workpaper_inputs_project_year_code", "project_id", "year", "sheet_code", unique=True),
    )
