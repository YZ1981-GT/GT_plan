"""交接记录模型 — Round 2 需求 10

HandoverRecord 记录人员离职/长假/轮岗时的工作交接，
包含交接范围、原因、实际迁移数量等信息，用于审计留痕。
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class HandoverScope(str, enum.Enum):
    """交接范围"""
    all = "all"
    by_project = "by_project"


class HandoverReasonCode(str, enum.Enum):
    """交接原因码"""
    resignation = "resignation"
    long_leave = "long_leave"
    rotation = "rotation"
    other = "other"


class HandoverRecord(Base, TimestampMixin):
    """人员交接记录

    记录从 from_staff 到 to_staff 的工作交接，
    包含底稿/工单/委派的迁移数量，以及原因和生效日期。
    """

    __tablename__ = "handover_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # 交接双方
    from_staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    to_staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    # 交接范围
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="交接范围: all / by_project"
    )
    project_ids: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="scope=by_project 时指定的项目 ID 列表"
    )

    # 原因
    reason_code: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="原因码: resignation / long_leave / rotation / other"
    )
    reason_detail: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="原因详情"
    )

    # 生效日期
    effective_date: Mapped[date] = mapped_column(nullable=False, comment="交接生效日期")

    # 迁移统计
    workpapers_moved: Mapped[int] = mapped_column(
        Integer, default=0, comment="迁移底稿数"
    )
    issues_moved: Mapped[int] = mapped_column(
        Integer, default=0, comment="迁移工单数"
    )
    assignments_moved: Mapped[int] = mapped_column(
        Integer, default=0, comment="迁移委派数"
    )

    # 执行信息
    executed_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, comment="执行交接的操作人"
    )
    executed_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="执行时间"
    )

    __table_args__ = (
        Index(
            "idx_handover_records_from_staff",
            "from_staff_id",
            text("executed_at DESC"),
        ),
        Index(
            "idx_handover_records_to_staff",
            "to_staff_id",
        ),
        Index(
            "idx_handover_records_effective_date",
            "effective_date",
        ),
    )
