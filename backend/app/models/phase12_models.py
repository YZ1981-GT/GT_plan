"""Phase 12: 底稿深度开发 — ORM 模型

新增表：
- wp_ai_generations: AI生成历史留痕
- background_jobs: 后台长任务主表
- background_job_items: 后台长任务明细项
- wp_recommendation_feedback: 底稿推荐反馈
- wp_edit_sessions: 编辑时间采集

新增枚举：
- AiGenerationStatus: AI生成状态
- ExplanationStatus: 审计说明同步状态
- WorkflowStatus: 底稿工作流状态
- ConsistencyStatus: 数据一致性状态
- BackgroundJobType: 后台任务类型
- BackgroundJobStatus: 后台任务状态
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------

class AiGenerationStatus(str, enum.Enum):
    drafted = "drafted"
    confirmed = "confirmed"
    rejected = "rejected"


class ExplanationStatus(str, enum.Enum):
    not_started = "not_started"
    ai_drafted = "ai_drafted"
    user_edited = "user_edited"
    confirmed = "confirmed"
    written_back = "written_back"
    synced = "synced"
    sync_failed = "sync_failed"


class WorkflowStatus(str, enum.Enum):
    draft = "draft"
    in_progress = "in_progress"
    self_checked = "self_checked"
    submitted_for_review = "submitted_for_review"
    review_passed = "review_passed"
    review_returned = "review_returned"
    partner_checked = "partner_checked"
    archived = "archived"


class ConsistencyStatus(str, enum.Enum):
    unknown = "unknown"
    consistent = "consistent"
    inconsistent = "inconsistent"
    checking = "checking"


class BackgroundJobType(str, enum.Enum):
    prefill = "prefill"
    generate_explanation = "generate_explanation"
    submit_review = "submit_review"
    download_pack = "download_pack"
    batch_assign = "batch_assign"


class BackgroundJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    partial_failed = "partial_failed"
    failed = "failed"
    cancelled = "cancelled"


class FeedbackAction(str, enum.Enum):
    accepted = "accepted"
    skipped = "skipped"
    manually_added = "manually_added"


# ---------------------------------------------------------------------------
# wp_ai_generations — AI生成历史留痕
# ---------------------------------------------------------------------------

class WpAiGeneration(Base):
    """AI生成历史记录，完整留痕每次生成的prompt/model/输出/确认信息。"""

    __tablename__ = "wp_ai_generations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("working_paper.id"), nullable=False
    )
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_structured: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), server_default=text("'drafted'"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_wp_ai_generations_wp", "wp_id", created_at.desc()),
    )


# ---------------------------------------------------------------------------
# background_jobs / background_job_items — 后台长任务编排
# ---------------------------------------------------------------------------

class BackgroundJob(Base):
    """后台长任务主表（批量刷新/生成/提交/下载等）。"""

    __tablename__ = "background_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), server_default=text("'queued'"), nullable=False
    )
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    progress_total: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    progress_done: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    failed_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_background_jobs_project", "project_id", created_at.desc()),
    )


class BackgroundJobItem(Base):
    """后台长任务明细项。"""

    __tablename__ = "background_job_items"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("background_jobs.id"), nullable=False
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("working_paper.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_background_job_items_job", "job_id", "status"),
    )


# ---------------------------------------------------------------------------
# wp_recommendation_feedback — 底稿推荐反馈
# ---------------------------------------------------------------------------

class WpRecommendationFeedback(Base):
    """底稿推荐反馈记录（采纳/跳过/手动添加）。"""

    __tablename__ = "wp_recommendation_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    wp_code: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    action_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    action_at: Mapped[datetime] = mapped_column(server_default=func.now())
    project_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index("idx_wp_feedback_project", "project_id"),
        Index("idx_wp_feedback_action", "action", "action_at"),
    )


# ---------------------------------------------------------------------------
# wp_edit_sessions — 编辑时间采集
# ---------------------------------------------------------------------------

class WpEditSession(Base):
    """底稿编辑时间采集（WOPI lock/unlock 自动记录）。"""

    __tablename__ = "wp_edit_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("working_paper.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    source: Mapped[str] = mapped_column(
        String(30), server_default=text("'wopi'"), nullable=False
    )
