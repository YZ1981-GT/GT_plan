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
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, func, text
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
    financial_report_unadjusted = "financial_report_unadjusted"
    disclosure_notes = "disclosure_notes"
    full_package = "full_package"


class WordExportStatus(str, enum.Enum):
    """Word导出状态机：draft→generating→generated→editing→confirmed→signed"""
    draft = "draft"
    generating = "generating"
    generated = "generated"
    editing = "editing"
    pending_approval = "pending_approval"
    confirmed = "confirmed"
    signed = "signed"
    archived = "archived"


# ---------------------------------------------------------------------------
# 状态机转换规则
# ---------------------------------------------------------------------------

VALID_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["generating"],
    "generating": ["generated"],
    "generated": ["editing"],
    "editing": ["pending_approval", "confirmed"],
    "pending_approval": ["confirmed", "editing"],
    "confirmed": ["signed", "editing", "archived"],
    "signed": ["archived"],
    "archived": ["confirmed"],  # 仅 admin 解除归档
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
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
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

    # deliverable-center V059
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_body_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    opinion_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    company_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    doc_subtype: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_pie: Mapped[bool | None] = mapped_column(
        server_default=text("false"), nullable=True
    )
    source_snapshot_refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    selected_sections: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    report_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    prior_period_info: Mapped[str | None] = mapped_column(String(40), nullable=True)
    approval_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    approval_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    signed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sign_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)

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

    # deliverable-center V059
    html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash_chain_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    source_snapshot_refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    selected_sections: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    created_via: Mapped[str | None] = mapped_column(
        String(20), server_default=text("'generate'"), nullable=True
    )
    # V142（deliverable-lineage-wiring-and-writeback-closure Wave 2 / 需求 7.2, 7.3）
    # 实际编辑人与编辑时间。NULL = 未知 —— **禁止回退 created_by 展示**：
    # created_by 在 OO 回调场景只是「回调处理占位」，把它当编辑人会让版本链上
    # 所有在线编辑版本作者都变成交付物创建人（历史缺陷）。
    edited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    edited_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # V143（deliverable-lineage-wiring-and-writeback-closure Wave 4 / 需求 10.2、10.8）
    # xlsx 手工改动差异检测**三态**：
    #   None                      = 未检测 / 未配 Cell_Mapping → 放行
    #   {"unavailable": "<原因>"}  = 映射存在但解析失败 → **拒绝 confirmed**（fail-closed）
    #   {"diffs": [...]}          = 已比对；非空即有手工改动 → 拒绝；空数组 → 放行
    # 🔴 判据不是「非空即拒绝」——`{"diffs": []}` 非空但表示已比对且一致。
    drift_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # V180（chain-closure-phase4-deliverable-center-trio Task 3 / 需求 3.2）
    # 显式 file_sha256 命名列（历史 file_hash 由 DeliverableHashService 旁路写；
    # phase4 新链路写 file_sha256，由最终落盘文件计算）+ snapshot_id 直绑三件套共享快照。
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
    is_stale: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)

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

    # V180（phase4 Task 3）：三件套共享快照 + 固定总数/成功计数 + readiness 摘要 + 时间点。
    # snapshot_id 是三件套应共享的不可变交付快照摘要（需求 1.5/2.4）；
    # trio_total 固定 3，trio_succeeded 只统计正式三件套（需求 2.6/4.4）。
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trio_total: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("3"), nullable=False
    )
    trio_succeeded: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    readiness: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

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

    # V180（phase4 Task 3）：稳定步骤键 + 固定顺序 + 共享快照 + 文件指纹投影 + attempt 投影。
    # 禁用显示名称作为稳定键（design §3.2）；中文名由前端映射，后端用这些固定英文键。
    step_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sequence: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    last_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    __table_args__ = (
        Index("idx_export_job_items_v2_job", "job_id", "status"),
    )


# ---------------------------------------------------------------------------
# export_job_attempts — append-only 尝试历史（phase4 Task 3）
# ---------------------------------------------------------------------------

class ExportJobAttempt(Base):
    """交付 job 的 append-only 尝试历史。

    设计 §3.3：失败 attempt 永不覆盖，重试只能新增 attempt 并更新 item 的当前投影；
    同一 item 的 ``attempt_no`` 单调递增且唯一（迁移 V180 唯一索引守护）。
    保留原始异常类型、中文用户消息、可诊断细节、时间点、快照 id 与文件指纹。
    """

    __tablename__ = "export_job_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("export_jobs_v2.id"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("export_job_items_v2.id"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), server_default=text("'running'"), nullable=False
    )
    #: 触发来源：initial（初次生成）/ retry（用户重试）/ recovery（中断恢复）
    trigger: Mapped[str | None] = mapped_column(String(30), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostic_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index(
            "uq_export_job_attempt_item_no",
            "item_id", "attempt_no", unique=True,
        ),
        Index("idx_export_job_attempts_job", "job_id", "item_id"),
    )
