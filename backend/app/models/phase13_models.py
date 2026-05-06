"""Phase 13: 审计报告·报表·附注生成与导出 — ORM 模型

新增表：
- word_export_task: Word导出主任务
- word_export_task_versions: 版本快照
- report_snapshot: 报表数据快照
- export_jobs_v2: 后台导出任务主表
- export_job_items_v2: 后台导出任务明细

新增枚举：
- WordExportDocType: 导出文档类型
- WordExportStatus: 导出状态
- ExportJobType: 后台任务类型
- ExportJobStatus: 后台任务状态
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

class WordExportDocType(str, enum.Enum):
    """Word导出文档类型"""
    audit_report = "audit_report"
    financial_report = "financial_report"
    disclosure_notes = "disclosure_notes"
    full_package = "full_package"


class WordExportStatus(str, enum.Enum):
    """Word导出状态机：draft→generating→generated→editing→confirmed→signed"""
    draft = "draft"
    generating = "generating"
    generated = "generated"
    editing = "editing"
    confirmed = "confirmed"
    signed = "signed"


# ---------------------------------------------------------------------------
# 状态机转换规则
# ---------------------------------------------------------------------------

VALID_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["generating"],
    "generating": ["generated"],
    "generated": ["editing"],
    "editing": ["confirmed"],
    "confirmed": ["signed", "editing"],  # confirmed 可 reopen 回 editing
    "signed": [],
}


# ---------------------------------------------------------------------------
# word_export_task — Word导出主任务
# ---------------------------------------------------------------------------

class WordExportTask(Base):
    """Word导出主任务"""

    __tablename__ = "word_export_task"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), server_default=text("'draft'"), nullable=False
    )
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Batch 3 Fix 2: 专用缓存键字段，不再复用 template_type
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="批量简报缓存键 MD5")

    __table_args__ = (
        Index("idx_word_export_task_project", "project_id", "doc_type"),
        Index("idx_word_export_task_status", "project_id", "status"),
        Index("idx_word_export_task_template_type", "template_type"),
        Index("idx_word_export_task_cache_key", "cache_key"),
    )


# ---------------------------------------------------------------------------
# word_export_task_versions — 版本快照
# ---------------------------------------------------------------------------

class WordExportTaskVersion(Base):
    """Word导出版本快照"""

    __tablename__ = "word_export_task_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    word_export_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("word_export_task.id"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_word_export_versions_task",
            "word_export_task_id", "version_no",
        ),
    )


# ---------------------------------------------------------------------------
# report_snapshot — 报表数据快照
# ---------------------------------------------------------------------------

class ReportSnapshot(Base):
    """报表数据快照（导出时从快照读取，不重复计算）"""

    __tablename__ = "report_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    report_type: Mapped[str] = mapped_column(String(10), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_trial_balance_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_report_snapshot_project_year_type",
            "project_id", "year", "report_type",
        ),
    )


# ---------------------------------------------------------------------------
# 枚举 — 后台导出任务
# ---------------------------------------------------------------------------

class ExportJobType(str, enum.Enum):
    """后台导出任务类型"""
    generate = "generate"
    full_package = "full_package"
    retry = "retry"


class ExportJobStatus(str, enum.Enum):
    """后台导出任务状态"""
    queued = "queued"
    running = "running"
    partial_failed = "partial_failed"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# export_jobs_v2 — 后台导出任务主表
# ---------------------------------------------------------------------------

class ExportJob(Base):
    """后台导出任务（全套导出/批量渲染/重试）"""

    __tablename__ = "export_jobs_v2"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), server_default=text("'queued'"), nullable=False
    )
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    progress_total: Mapped[int] = mapped_column(sa.Integer, server_default=text("0"))
    progress_done: Mapped[int] = mapped_column(sa.Integer, server_default=text("0"))
    failed_count: Mapped[int] = mapped_column(sa.Integer, server_default=text("0"))
    initiated_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_export_jobs_v2_project", "project_id", "status"),
    )


# ---------------------------------------------------------------------------
# export_job_items_v2 — 后台导出任务明细
# ---------------------------------------------------------------------------

class ExportJobItem(Base):
    """后台导出任务明细"""

    __tablename__ = "export_job_items_v2"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("export_jobs_v2.id"), nullable=False
    )
    word_export_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("word_export_task.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), server_default=text("'queued'"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_export_job_items_v2_job", "job_id", "status"),
    )
