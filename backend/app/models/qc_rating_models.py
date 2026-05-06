"""QC 评级与复核人指标 ORM 模型

Refinement Round 3 — 需求 3, 6：项目质量评级 + 复核人深度指标。

两张表：
- project_quality_ratings: 项目 ABCD 评级快照
- reviewer_metrics_snapshots: 复核人深度指标每日快照
"""

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProjectQualityRating(Base, TimestampMixin):
    """项目质量评级

    每月 1 日凌晨定时任务计算上月快照。
    评级 A/B/C/D 由 5 维度加权得分决定（权重存 system_settings.qc_rating_weights）。
    支持人工 override（必须附说明），系统评级与人工评级并存。

    Refinement Round 3 — 需求 3。
    """

    __tablename__ = "project_quality_ratings"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    rating: Mapped[str] = mapped_column(
        String(1), nullable=False
    )  # 'A' | 'B' | 'C' | 'D'
    score: Mapped[int] = mapped_column(
        sa.Integer, nullable=False
    )  # 0-100 综合得分
    dimensions: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # 各维度得分明细 {qc_pass_rate: 85, review_depth: 72, ...}
    computed_at: Mapped[datetime] = mapped_column(
        sa.DateTime, server_default=sa.func.now(), nullable=False
    )
    computed_by_rule_version: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("1"), nullable=False
    )
    # 人工 override 字段
    override_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    override_rating: Mapped[str | None] = mapped_column(
        String(1), nullable=True
    )  # 人工覆盖评级
    override_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # 覆盖原因说明

    __table_args__ = (
        Index("idx_project_quality_ratings_project_year", "project_id", "year"),
        Index("idx_project_quality_ratings_year", "year"),
        Index("idx_project_quality_ratings_rating", "rating"),
    )


class ReviewerMetricsSnapshot(Base, TimestampMixin):
    """复核人深度指标快照

    每日凌晨定时任务计算，用于年度考评参考。
    5 个核心指标：
    - avg_review_time_min: 平均复核时长（分钟）
    - avg_comments_per_wp: 平均每张底稿意见条数
    - rejection_rate: 退回率
    - qc_rule_catch_rate: 复核人发现问题占所有问题的比例
    - sampled_rework_rate: 被质控抽查后发现漏审的比例

    Refinement Round 3 — 需求 6。
    """

    __tablename__ = "reviewer_metrics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    avg_review_time_min: Mapped[float | None] = mapped_column(
        sa.Float, nullable=True
    )
    avg_comments_per_wp: Mapped[float | None] = mapped_column(
        sa.Float, nullable=True
    )
    rejection_rate: Mapped[float | None] = mapped_column(
        sa.Float, nullable=True
    )  # 0.0 ~ 1.0
    qc_rule_catch_rate: Mapped[float | None] = mapped_column(
        sa.Float, nullable=True
    )  # 0.0 ~ 1.0
    sampled_rework_rate: Mapped[float | None] = mapped_column(
        sa.Float, nullable=True
    )  # 0.0 ~ 1.0

    __table_args__ = (
        Index(
            "idx_reviewer_metrics_snapshots_reviewer_year",
            "reviewer_id",
            "year",
        ),
        Index("idx_reviewer_metrics_snapshots_date", "snapshot_date"),
    )
