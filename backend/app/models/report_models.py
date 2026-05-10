"""第一阶段MVP报表：8张报表相关表 ORM 模型

对应 Alembic 迁移脚本 006_report_tables.py，包含：
- 10 个 PostgreSQL 枚举类型
- 8 个 SQLAlchemy ORM 模型
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ---------------------------------------------------------------------------
# PostgreSQL 枚举类型（与迁移 006 一致）
# ---------------------------------------------------------------------------


class FinancialReportType(str, enum.Enum):
    """财务报表类型"""
    balance_sheet = "balance_sheet"
    income_statement = "income_statement"
    cash_flow_statement = "cash_flow_statement"
    equity_statement = "equity_statement"
    cash_flow_supplement = "cash_flow_supplement"
    impairment_provision = "impairment_provision"


class CashFlowCategory(str, enum.Enum):
    """现金流量类别"""
    operating = "operating"
    investing = "investing"
    financing = "financing"
    supplementary = "supplementary"


class ContentType(str, enum.Enum):
    """附注内容类型"""
    table = "table"
    text = "text"
    mixed = "mixed"


class SourceTemplate(str, enum.Enum):
    """附注模版来源"""
    soe = "soe"
    listed = "listed"


class NoteStatus(str, enum.Enum):
    """附注状态"""
    draft = "draft"
    confirmed = "confirmed"


class OpinionType(str, enum.Enum):
    """审计意见类型"""
    unqualified = "unqualified"
    qualified = "qualified"
    adverse = "adverse"
    disclaimer = "disclaimer"


class CompanyType(str, enum.Enum):
    """公司类型"""
    listed = "listed"
    non_listed = "non_listed"


class ReportStatus(str, enum.Enum):
    """审计报告状态

    Round 5 新增 ``eqcr_approved``：项目组完成 ``sign_off`` gate 后，
    EQCR 审批通过时切入此态；``opinion_type`` 与段落锁定。
    归档签字完成后切至 ``final``。
    """
    draft = "draft"
    review = "review"
    eqcr_approved = "eqcr_approved"
    final = "final"


class ExportTaskType(str, enum.Enum):
    """导出任务类型"""
    single_document = "single_document"
    full_archive = "full_archive"


class ExportTaskStatus(str, enum.Enum):
    """导出任务状态"""
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


# ---------------------------------------------------------------------------
# ReportConfig 模型（报表格式配置）
# ---------------------------------------------------------------------------


class ReportConfig(Base):
    """报表格式配置（行次定义+取数公式）"""

    __tablename__ = "report_config"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_type: Mapped[FinancialReportType] = mapped_column(
        sa.Enum(FinancialReportType, name="financial_report_type", create_type=False),
        nullable=False,
    )
    row_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    row_code: Mapped[str] = mapped_column(String, nullable=False)
    row_name: Mapped[str] = mapped_column(String, nullable=False)
    indent_level: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    formula_category: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # auto_calc(自动运算) / logic_check(逻辑审核) / reasonability(提示合理性)
    formula_description: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )  # 公式简短说明
    formula_source: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # 公式来源标注（如"试算表审定数"/"报表行次引用"/"手工填列"）
    applicable_standard: Mapped[str] = mapped_column(String, nullable=False)
    is_total_row: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    parent_row_code: Mapped[str | None] = mapped_column(String, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "uq_report_config_type_code_standard",
            "report_type", "row_code", "applicable_standard",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# FinancialReport 模型（生成的报表数据）
# ---------------------------------------------------------------------------


class FinancialReport(Base):
    """生成的财务报表数据"""

    __tablename__ = "financial_report"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    report_type: Mapped[FinancialReportType] = mapped_column(
        sa.Enum(FinancialReportType, name="financial_report_type", create_type=False),
        nullable=False,
    )
    row_code: Mapped[str] = mapped_column(String, nullable=False)
    row_name: Mapped[str | None] = mapped_column(String, nullable=True)
    current_period_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    prior_period_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    formula_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_accounts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    indent_level: Mapped[int] = mapped_column(sa.Integer, server_default=text("0"), nullable=False)
    is_total_row: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "uq_financial_report_project_year_type_code",
            "project_id", "year", "report_type", "row_code",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# CfsAdjustment 模型（现金流量表调整分录）
# ---------------------------------------------------------------------------


class CfsAdjustment(Base):
    """现金流量表调整分录"""

    __tablename__ = "cfs_adjustments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    adjustment_no: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    debit_account: Mapped[str] = mapped_column(String, nullable=False)
    credit_account: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(20, 2), nullable=False)
    cash_flow_category: Mapped[CashFlowCategory | None] = mapped_column(
        sa.Enum(CashFlowCategory, name="cash_flow_category", create_type=False),
        nullable=True,
    )
    cash_flow_line_item: Mapped[str | None] = mapped_column(String, nullable=True)
    entry_group_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    is_auto_generated: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "idx_cfs_adjustments_project_year_category",
            "project_id", "year", "cash_flow_category",
        ),
    )


# ---------------------------------------------------------------------------
# DisclosureNote 模型（附注）
# ---------------------------------------------------------------------------


class DisclosureNote(Base):
    """财务报表附注"""

    __tablename__ = "disclosure_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    note_section: Mapped[str] = mapped_column(String, nullable=False)
    section_title: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[ContentType | None] = mapped_column(
        sa.Enum(ContentType, name="content_type", create_type=False),
        nullable=True,
    )
    table_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_template: Mapped[SourceTemplate | None] = mapped_column(
        sa.Enum(SourceTemplate, name="source_template", create_type=False),
        nullable=True,
    )
    status: Mapped[NoteStatus] = mapped_column(
        sa.Enum(NoteStatus, name="note_status", create_type=False),
        server_default=text("'draft'"),
        nullable=False,
    )
    sort_order: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    # F46 / Sprint 7.22: 账套 rollback 后由 event_handlers 标 True，提示刷新
    is_stale: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    # F50 / Sprint 8.16: 下游快照绑定（创建时绑定当前 active dataset）
    bound_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ledger_datasets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dataset_bound_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "uq_disclosure_notes_active",
            "project_id", "year", "note_section",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )


# ---------------------------------------------------------------------------
# AuditReport 模型（审计报告）
# ---------------------------------------------------------------------------


class AuditReport(Base):
    """审计报告"""

    __tablename__ = "audit_report"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    opinion_type: Mapped[OpinionType] = mapped_column(
        sa.Enum(OpinionType, name="opinion_type", create_type=False),
        nullable=False,
    )
    company_type: Mapped[CompanyType] = mapped_column(
        sa.Enum(CompanyType, name="company_type", create_type=False),
        server_default=text("'non_listed'"),
        nullable=False,
    )
    report_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    signing_partner: Mapped[str | None] = mapped_column(String, nullable=True)
    paragraphs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    financial_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        sa.Enum(ReportStatus, name="report_status", create_type=False),
        server_default=text("'draft'"),
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    # F46 / Sprint 7.22: 账套 rollback 后由 event_handlers 标 True，提示刷新
    is_stale: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    # F50 / Sprint 8.16: 下游快照绑定
    # AuditReport 绑定时机特殊：不是创建时，而是 status 转 final 时锁定（签字级合规）
    bound_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ledger_datasets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dataset_bound_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "uq_audit_report_project_year",
            "project_id", "year",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# AuditReportTemplate 模型（审计报告模板）
# ---------------------------------------------------------------------------


class AuditReportTemplate(Base):
    """审计报告段落模板"""

    __tablename__ = "audit_report_template"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    opinion_type: Mapped[OpinionType] = mapped_column(
        sa.Enum(OpinionType, name="opinion_type", create_type=False),
        nullable=False,
    )
    company_type: Mapped[CompanyType] = mapped_column(
        sa.Enum(CompanyType, name="company_type", create_type=False),
        nullable=False,
    )
    section_name: Mapped[str] = mapped_column(String, nullable=False)
    section_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_required: Mapped[bool] = mapped_column(
        server_default=text("true"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "uq_audit_report_template_opinion_company_section",
            "opinion_type", "company_type", "section_name",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# ExportTask 模型（导出任务）
# ---------------------------------------------------------------------------


class ExportTask(Base):
    """PDF导出任务"""

    __tablename__ = "export_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    task_type: Mapped[ExportTaskType] = mapped_column(
        sa.Enum(ExportTaskType, name="export_task_type", create_type=False),
        nullable=False,
    )
    document_type: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[ExportTaskStatus] = mapped_column(
        sa.Enum(ExportTaskStatus, name="export_task_status", create_type=False),
        server_default=text("'queued'"),
        nullable=False,
    )
    progress_percentage: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    file_size: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    password_protected: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_export_tasks_project_status",
            "project_id", "status",
        ),
    )


# ---------------------------------------------------------------------------
# NoteValidationResult 模型（附注校验结果）
# ---------------------------------------------------------------------------


class NoteValidationResult(Base):
    """附注校验结果"""

    __tablename__ = "note_validation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    validation_timestamp: Mapped[datetime] = mapped_column(nullable=False)
    findings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    error_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    warning_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    info_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    validated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_note_validation_results_project_year",
            "project_id", "year",
        ),
    )
