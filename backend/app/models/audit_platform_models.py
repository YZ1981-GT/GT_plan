"""第一阶段MVP核心：10张业务表 ORM 模型

对应 Alembic 迁移脚本 002_mvp_core_tables.py，包含：
- 7 个 PostgreSQL 枚举类型
- 10 个 SQLAlchemy ORM 模型
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ---------------------------------------------------------------------------
# PostgreSQL 枚举类型（与迁移 002 一致）
# ---------------------------------------------------------------------------


class AccountDirection(str, enum.Enum):
    """科目借贷方向"""
    debit = "debit"
    credit = "credit"


class AccountCategory(str, enum.Enum):
    """科目类别（资产/负债/权益/收入/费用）"""
    asset = "asset"
    liability = "liability"
    equity = "equity"
    revenue = "revenue"
    expense = "expense"


class AccountSource(str, enum.Enum):
    """科目来源"""
    standard = "standard"
    client = "client"


class MappingType(str, enum.Enum):
    """映射类型"""
    auto_exact = "auto_exact"
    auto_fuzzy = "auto_fuzzy"
    manual = "manual"


class AdjustmentType(str, enum.Enum):
    """调整分录类型"""
    aje = "aje"
    rje = "rje"


class ReviewStatus(str, enum.Enum):
    """复核状态"""
    draft = "draft"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"


class ImportStatus(str, enum.Enum):
    """导入批次状态"""
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    rolled_back = "rolled_back"


class MisstatementType(str, enum.Enum):
    """错报类型"""
    factual = "factual"
    judgmental = "judgmental"
    projected = "projected"


class ReportType(str, enum.Enum):
    """报表类型"""
    balance_sheet = "balance_sheet"
    income_statement = "income_statement"
    cash_flow = "cash_flow"


class ReportLineMappingType(str, enum.Enum):
    """报表行次映射类型"""
    ai_suggested = "ai_suggested"
    manual = "manual"
    reference_copied = "reference_copied"


# ---------------------------------------------------------------------------
# ImportBatch 模型（先于四表数据表，因为它们有 FK 引用）
# ---------------------------------------------------------------------------


class ImportBatch(Base):
    """导入批次"""

    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    data_type: Mapped[str] = mapped_column(String, nullable=False)
    record_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    status: Mapped[ImportStatus] = mapped_column(
        sa.Enum(ImportStatus, name="import_status", create_type=False),
        server_default=text("'pending'"),
        nullable=False,
    )
    validation_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_import_batches_project_year", "project_id", "year"),
    )


# ---------------------------------------------------------------------------
# AccountChart 模型
# ---------------------------------------------------------------------------


class AccountChart(Base):
    """科目表（标准科目 + 客户科目）"""

    __tablename__ = "account_chart"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    account_code: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[AccountDirection] = mapped_column(
        sa.Enum(AccountDirection, name="account_direction", create_type=False),
        nullable=False,
    )
    level: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    category: Mapped[AccountCategory] = mapped_column(
        sa.Enum(AccountCategory, name="account_category", create_type=False),
        nullable=False,
    )
    parent_code: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[AccountSource] = mapped_column(
        sa.Enum(AccountSource, name="account_source", create_type=False),
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "uq_account_chart_project_code_source",
            "project_id", "account_code", "source",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# AccountMapping 模型
# ---------------------------------------------------------------------------


class AccountMapping(Base):
    """科目映射关系"""

    __tablename__ = "account_mapping"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    original_account_code: Mapped[str] = mapped_column(String, nullable=False)
    original_account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    standard_account_code: Mapped[str] = mapped_column(String, nullable=False)
    mapping_type: Mapped[MappingType] = mapped_column(
        sa.Enum(MappingType, name="mapping_type", create_type=False),
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "uq_account_mapping_project_original_code",
            "project_id", "original_account_code",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# TbBalance 模型
# ---------------------------------------------------------------------------


class TbBalance(Base):
    """科目余额表"""

    __tablename__ = "tb_balance"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    account_code: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    opening_balance: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    debit_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    credit_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    closing_balance: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    currency_code: Mapped[str] = mapped_column(
        String(3), server_default=text("'CNY'"), nullable=False
    )
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_batches.id"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_tb_balance_project_year_account",
            "project_id", "year", "account_code",
        ),
    )


# ---------------------------------------------------------------------------
# TbLedger 模型
# ---------------------------------------------------------------------------


class TbLedger(Base):
    """序时账（总账明细）"""

    __tablename__ = "tb_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    voucher_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    voucher_no: Mapped[str] = mapped_column(String, nullable=False)
    account_code: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    debit_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    credit_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    counterpart_account: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    preparer: Mapped[str | None] = mapped_column(String, nullable=True)
    currency_code: Mapped[str] = mapped_column(
        String(3), server_default=text("'CNY'"), nullable=False
    )
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_batches.id"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_tb_ledger_project_year_date_no",
            "project_id", "year", "voucher_date", "voucher_no",
        ),
        Index(
            "idx_tb_ledger_project_year_account",
            "project_id", "year", "account_code",
        ),
    )


# ---------------------------------------------------------------------------
# TbAuxBalance 模型
# ---------------------------------------------------------------------------


class TbAuxBalance(Base):
    """辅助余额表"""

    __tablename__ = "tb_aux_balance"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    account_code: Mapped[str] = mapped_column(String, nullable=False)
    aux_type: Mapped[str] = mapped_column(String, nullable=False)
    aux_code: Mapped[str | None] = mapped_column(String, nullable=True)
    aux_name: Mapped[str | None] = mapped_column(String, nullable=True)
    opening_balance: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    debit_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    credit_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    closing_balance: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    currency_code: Mapped[str] = mapped_column(
        String(3), server_default=text("'CNY'"), nullable=False
    )
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_batches.id"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_tb_aux_balance_project_year_account_aux",
            "project_id", "year", "account_code", "aux_type",
        ),
    )


# ---------------------------------------------------------------------------
# TbAuxLedger 模型
# ---------------------------------------------------------------------------


class TbAuxLedger(Base):
    """辅助明细账"""

    __tablename__ = "tb_aux_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    voucher_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    voucher_no: Mapped[str | None] = mapped_column(String, nullable=True)
    account_code: Mapped[str] = mapped_column(String, nullable=False)
    aux_type: Mapped[str | None] = mapped_column(String, nullable=True)
    aux_code: Mapped[str | None] = mapped_column(String, nullable=True)
    aux_name: Mapped[str | None] = mapped_column(String, nullable=True)
    debit_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    credit_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    preparer: Mapped[str | None] = mapped_column(String, nullable=True)
    currency_code: Mapped[str] = mapped_column(
        String(3), server_default=text("'CNY'"), nullable=False
    )
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_batches.id"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_tb_aux_ledger_project_year_account_aux",
            "project_id", "year", "account_code", "aux_type",
        ),
    )


# ---------------------------------------------------------------------------
# Adjustment 模型
# ---------------------------------------------------------------------------


class Adjustment(Base):
    """审计调整分录（AJE / RJE）"""

    __tablename__ = "adjustments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    adjustment_no: Mapped[str] = mapped_column(String, nullable=False)
    adjustment_type: Mapped[AdjustmentType] = mapped_column(
        sa.Enum(AdjustmentType, name="adjustment_type", create_type=False),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_code: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    debit_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    credit_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    entry_group_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        sa.Enum(ReviewStatus, name="review_status", create_type=False),
        server_default=text("'draft'"),
        nullable=False,
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_adjustments_project_year_type",
            "project_id", "year", "adjustment_type",
        ),
        Index(
            "idx_adjustments_project_entry_group",
            "project_id", "entry_group_id",
        ),
    )


# ---------------------------------------------------------------------------
# TrialBalance 模型
# ---------------------------------------------------------------------------


class TrialBalance(Base):
    """试算表（四列结构）"""

    __tablename__ = "trial_balance"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    standard_account_code: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    account_category: Mapped[AccountCategory] = mapped_column(
        sa.Enum(AccountCategory, name="account_category", create_type=False),
        nullable=False,
    )
    unadjusted_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    rje_adjustment: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 2), server_default=text("0"), nullable=False
    )
    aje_adjustment: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 2), server_default=text("0"), nullable=False
    )
    audited_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    opening_balance: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "uq_trial_balance_project_year_company_account",
            "project_id", "year", "company_code", "standard_account_code",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# Materiality 模型
# ---------------------------------------------------------------------------


class Materiality(Base):
    """重要性水平"""

    __tablename__ = "materiality"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    benchmark_type: Mapped[str] = mapped_column(String, nullable=False)
    benchmark_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 2), nullable=False
    )
    overall_percentage: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False
    )
    overall_materiality: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 2), nullable=False
    )
    performance_ratio: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False
    )
    performance_materiality: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 2), nullable=False
    )
    trivial_ratio: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False
    )
    trivial_threshold: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 2), nullable=False
    )
    is_override: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    calculated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "uq_materiality_project_year",
            "project_id", "year",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# ReportLineMapping 模型
# ---------------------------------------------------------------------------


class ReportLineMapping(Base):
    """报表行次映射（标准科目→报表行次）"""

    __tablename__ = "report_line_mapping"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    standard_account_code: Mapped[str] = mapped_column(String, nullable=False)
    report_type: Mapped[ReportType] = mapped_column(
        sa.Enum(ReportType, name="report_type", create_type=False),
        nullable=False,
    )
    report_line_code: Mapped[str] = mapped_column(String, nullable=False)
    report_line_name: Mapped[str] = mapped_column(String, nullable=False)
    report_line_level: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    parent_line_code: Mapped[str | None] = mapped_column(String, nullable=True)
    mapping_type: Mapped[ReportLineMappingType] = mapped_column(
        sa.Enum(ReportLineMappingType, name="report_line_mapping_type", create_type=False),
        nullable=False,
    )
    is_confirmed: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_report_line_mapping_project_type_account",
            "project_id", "report_type", "standard_account_code",
        ),
    )


# ---------------------------------------------------------------------------
# AdjustmentEntry 模型（调整分录明细行）
# ---------------------------------------------------------------------------


class AdjustmentEntry(Base):
    """调整分录明细行（独立于 adjustments 头表）"""

    __tablename__ = "adjustment_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    adjustment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("adjustments.id"), nullable=False
    )
    entry_group_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    line_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    standard_account_code: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    report_line_code: Mapped[str | None] = mapped_column(String, nullable=True)
    debit_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 2), server_default=text("0"), nullable=False
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 2), server_default=text("0"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_adjustment_entries_adjustment_id", "adjustment_id"),
        Index("idx_adjustment_entries_entry_group_id", "entry_group_id"),
    )


# ---------------------------------------------------------------------------
# UnadjustedMisstatement 模型（未更正错报汇总）
# ---------------------------------------------------------------------------


class UnadjustedMisstatement(Base):
    """未更正错报汇总"""

    __tablename__ = "unadjusted_misstatements"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source_adjustment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("adjustments.id"), nullable=True
    )
    misstatement_description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_account_code: Mapped[str | None] = mapped_column(String, nullable=True)
    affected_account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    misstatement_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 2), nullable=False
    )
    misstatement_type: Mapped[MisstatementType] = mapped_column(
        sa.Enum(MisstatementType, name="misstatement_type", create_type=False),
        nullable=False,
    )
    management_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    auditor_evaluation: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_carried_forward: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    prior_year_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("unadjusted_misstatements.id"), nullable=True
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
            "idx_unadjusted_misstatements_project_year",
            "project_id", "year",
        ),
        Index(
            "idx_unadjusted_misstatements_source_adj",
            "source_adjustment_id",
        ),
    )
