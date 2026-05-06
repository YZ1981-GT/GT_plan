"""QC 抽查 ORM 模型

Refinement Round 3 — 需求 4：质控抽查底稿工具。

三张表：
- qc_inspections: 抽查批次
- qc_inspection_items: 抽查子项（每张底稿一条）
- qc_inspection_records: 质控独立复核记录（不入 wp_review_records）
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class QcInspection(Base, SoftDeleteMixin, TimestampMixin):
    """质控抽查批次

    每次质控发起抽查生成一条记录，包含抽样策略和参数。
    状态流转：created → in_progress → completed / cancelled

    Refinement Round 3 — 需求 4。
    """

    __tablename__ = "qc_inspections"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # 'random' | 'risk_based' | 'full_cycle' | 'mixed'
    params: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # 策略参数，如 {ratio: 0.1, cycles: ['D']}
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )  # 质控复核人
    status: Mapped[str] = mapped_column(
        String(20), server_default=text("'created'"), nullable=False
    )  # 'created' | 'in_progress' | 'completed' | 'cancelled'
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    report_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    items: Mapped[list["QcInspectionItem"]] = relationship(
        "QcInspectionItem", back_populates="inspection", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_qc_inspections_project", "project_id"),
        Index("idx_qc_inspections_reviewer", "reviewer_id"),
        Index("idx_qc_inspections_status", "status"),
    )


class QcInspectionItem(Base, TimestampMixin):
    """质控抽查子项

    每条对应一张底稿的质控复核任务。
    状态流转：pending → in_review → completed

    Refinement Round 3 — 需求 4。
    """

    __tablename__ = "qc_inspection_items"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("qc_inspections.id"), nullable=False
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )  # 被抽查的底稿 ID
    status: Mapped[str] = mapped_column(
        String(20), server_default=text("'pending'"), nullable=False
    )  # 'pending' | 'in_review' | 'completed'
    findings: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # 发现的问题列表
    qc_verdict: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # 'pass' | 'fail' | 'conditional_pass'
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)

    # Relationships
    inspection: Mapped["QcInspection"] = relationship(
        "QcInspection", back_populates="items"
    )
    records: Mapped[list["QcInspectionRecord"]] = relationship(
        "QcInspectionRecord", back_populates="item", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_qc_inspection_items_inspection", "inspection_id"),
        Index("idx_qc_inspection_items_wp", "wp_id"),
        Index("idx_qc_inspection_items_status", "status"),
    )


class QcInspectionRecord(Base, TimestampMixin):
    """质控独立复核记录

    质控人在抽查过程中对底稿的具体批注/意见。
    独立于项目组的 wp_review_records，避免干扰项目组复核状态。

    Refinement Round 3 — 需求 4。
    """

    __tablename__ = "qc_inspection_records"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inspection_item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("qc_inspection_items.id"), nullable=False
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'blocking' | 'warning' | 'info'
    cell_ref: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # 单元格引用，如 'E5'
    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )

    # Relationships
    item: Mapped["QcInspectionItem"] = relationship(
        "QcInspectionItem", back_populates="records"
    )

    __table_args__ = (
        Index("idx_qc_inspection_records_item", "inspection_item_id"),
        Index("idx_qc_inspection_records_created_by", "created_by"),
    )
