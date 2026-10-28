"""预审样本存续核对汇总（迁移 V212；spec voucher-identity-writeback-and-audit-phase 任务 8 建表、任务 17 写入）。

账套重导激活后，带预审行的底稿一键核对：每条预审分录在当前账套里是「未变 / 分录已改 / 凭证已删除 /
疑似重编号」（design §7）。逐行状态写在宿主行元数据 ``_gt.sv``；后端读不到各宿主的行结构，
只在这里落每底稿每账套版本一行的计数（upsert），项目级抽样概览读它报未确认数。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class InterimSurvivalCheck(Base):
    __tablename__ = "interim_survival_checks"
    __table_args__ = (
        sa.UniqueConstraint("working_paper_id", "dataset_id", name="uq_interim_survival_checks_wp_dataset"),
        sa.Index("idx_interim_survival_checks_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("projects.id"), nullable=False)
    working_paper_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    total: Mapped[int] = mapped_column(nullable=False)
    unchanged: Mapped[int] = mapped_column(nullable=False)
    changed: Mapped[int] = mapped_column(nullable=False)
    deleted: Mapped[int] = mapped_column(nullable=False)
    renumbered: Mapped[int] = mapped_column(nullable=False)
    # 非「未变」且尚未逐行确认的行数
    unacked: Mapped[int] = mapped_column(nullable=False)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
