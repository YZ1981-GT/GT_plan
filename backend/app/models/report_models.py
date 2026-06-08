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
from sqlalchemy import Boolean, ForeignKey, Index, Integer, SmallInteger, String, Text, func, text
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
    # D spec report-config-baseline / V040: 主模板更新→克隆项目标脏
    is_stale: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index(
            "uq_report_config_type_code_standard",
            "report_type", "row_code", "applicable_standard",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# ReportConfigBaseline 模型（报表配置主模板回填候选）
# ---------------------------------------------------------------------------


class ReportConfigBaseline(Base):
    """报表配置主模板回填候选（项目优化→主模板评审通道）

    仿附注 GroupNoteTemplateBaseline 范式：项目级配置可"提交为主模板候选"，
    admin 审核通过后合并回 standard 级（带版本号 + 审计留痕）。
    对应迁移 V044__report_config_baseline.sql（原 V040，因同号冲突重编号）。
    """

    __tablename__ = "report_config_baseline"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    standard: Mapped[str] = mapped_column(String(40), nullable=False)
    report_type: Mapped[str] = mapped_column(String(20), nullable=False)
    row_code: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), server_default=text("'pending'"), nullable=False
    )
    version: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), nullable=False
    )
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


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
    is_stale: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
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
    # D13 章节序号重构（A.0.1 / V019）：稳定 section_id + 树形层级 + 自动/锁定编号
    # A.0.5 backfill 完成后会把 section_id / level / parent_section_id 收紧为 NOT NULL
    section_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    parent_section_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    sort_index: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    auto_numbering: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    lock_number: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    locked_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
    # Sprint A.1 / V020：动态模型字段（D1-D7 基础设施）
    is_empty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    template_lineage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_local_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    text_template_vars: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Phase 3 附注级穿透 provenance（consol-phase3-frontend-drilldown / T6 / V039）
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    consolidation_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # workpaper-html-renderer Task 10.3: 附注双源单向同步标记
    # design §12.1 推荐选项 A — 仅记录"最近一次"由底稿 push 同步的来源
    last_sync_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_sync_wp_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("working_paper.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_sync_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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
# GroupNoteTemplateBaseline 模型（D6 集团附注模板基线）
# ---------------------------------------------------------------------------


class GroupNoteTemplateBaseline(Base):
    """集团附注模板基线（D6）

    集团总部维护的附注模板基线，子公司项目可 apply 并 local_override。
    支持多层级继承（parent_baseline_id 链）和版本管理。
    """

    __tablename__ = "group_note_template_baseline"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'v1.0'")
    )
    parent_baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("group_note_template_baseline.id"),
        nullable=True,
    )
    template_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'soe'")
    )
    sections_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_group_baseline_parent_project", "parent_project_id"),
        Index("ix_group_baseline_parent_baseline", "parent_baseline_id"),
    )


# ---------------------------------------------------------------------------
# NoteSectionVersionTree 模型（D11 章节版本树）
# ---------------------------------------------------------------------------


class NoteSectionVersionTree(Base):
    """章节版本树（D11）

    记录章节的版本历史，支持 fork/merge/diff 操作。
    每个节点是一个快照，parent_node_id 形成 DAG 结构。
    """

    __tablename__ = "note_section_version_tree"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    note_section_id: Mapped[str] = mapped_column(String(100), nullable=False)
    branch: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'main'")
    )
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("note_section_version_tree.id"),
        nullable=True,
    )
    snapshot_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    __table_args__ = (
        Index("ix_version_tree_project_section", "project_id", "note_section_id"),
        Index("ix_version_tree_parent_node", "parent_node_id"),
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
    # deliverable-center V059
    report_body_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_pie: Mapped[bool | None] = mapped_column(
        server_default=text("false"), nullable=True
    )
    prior_period_info: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # audit-report-template-integration V066: 企业子类型 + 模板详简版 + manifest 模板版本
    company_subtype: Mapped[str | None] = mapped_column(String(10), nullable=True)
    template_variant: Mapped[str | None] = mapped_column(
        String(10), server_default=text("'simple'"), nullable=True
    )
    template_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        Index(
            "uq_audit_report_project_year",
            "project_id", "year",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# FillPreviewSession 模型（报告正文两阶段生成 preview 会话）
# ---------------------------------------------------------------------------


class FillPreviewSession(Base):
    """报告正文模板填充 preview 会话（audit-report-template-integration V066）

    两阶段 API 的 preview 步骤产物：copy 模板 → 替换占位符 → 扫描 OPT 后，
    将工作副本路径 + 可选段落清单 + 待补充字段缓存至此表，confirm 阶段按
    preview_session_id 取回。TTL 24h（expires_at），confirm 后或定时清理删除。

    三层一致：DDL `V066__template_fill_columns.sql` + 本 ORM + TemplateFillService。
    created_at/updated_at 对应 DDL `TIMESTAMPTZ NOT NULL DEFAULT now()`。
    """

    __tablename__ = "fill_preview_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    opinion_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    company_subtype: Mapped[str | None] = mapped_column(String(10), nullable=True)
    template_variant: Mapped[str | None] = mapped_column(String(10), nullable=True)
    template_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    working_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    optional_sections_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    missing_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_fill_preview_sessions_project_year",
            "project_id", "year",
        ),
        Index(
            "idx_fill_preview_sessions_expires_at",
            "expires_at",
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
