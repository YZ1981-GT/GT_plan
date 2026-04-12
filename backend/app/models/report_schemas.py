"""第一阶段MVP报表：Pydantic Schema 定义

覆盖所有报表模块 API 请求/响应模型：
- 报表生成 (ReportGenerateRequest, ReportRow, ReportDrilldown)
- 现金流量表工作底稿 (CFSWorksheetData, CFSAdjustmentCreate, CFSReconciliation)
- 附注 (DisclosureNoteTree, DisclosureNoteDetail, NoteValidationFinding)
- 审计报告 (AuditReportGenerate, AuditReportParagraph)
- PDF导出 (ExportTaskCreate, ExportTaskStatus)
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.report_models import (
    CashFlowCategory,
    CompanyType,
    ContentType,
    ExportTaskStatus,
    ExportTaskType,
    FinancialReportType,
    NoteStatus,
    OpinionType,
    ReportStatus,
    SourceTemplate,
)


# ===================================================================
# 1. 报表生成 (Report)
# ===================================================================


class ReportGenerateRequest(BaseModel):
    """生成报表请求"""
    project_id: UUID
    year: int


class ReportRow(BaseModel):
    """报表行数据"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    row_code: str
    row_name: str | None = None
    current_period_amount: Decimal | None = None
    prior_period_amount: Decimal | None = None
    formula_used: str | None = None
    source_accounts: list[str] | None = None


class ReportResponse(BaseModel):
    """报表响应"""
    report_type: FinancialReportType
    year: int
    rows: list[ReportRow] = []
    is_balanced: bool = True
    balance_check_message: str | None = None


class ReportDrilldownAccount(BaseModel):
    """穿透查询 — 贡献科目"""
    account_code: str
    account_name: str | None = None
    amount: Decimal | None = None


class ReportDrilldown(BaseModel):
    """报表行穿透查询结果"""
    row_code: str
    row_name: str | None = None
    formula: str | None = None
    current_period_amount: Decimal | None = None
    contributing_accounts: list[ReportDrilldownAccount] = []


class ConsistencyCheckResult(BaseModel):
    """跨报表一致性校验结果"""
    check_name: str
    passed: bool
    expected_value: Decimal | None = None
    actual_value: Decimal | None = None
    difference: Decimal | None = None


class ReportConsistencyResponse(BaseModel):
    """跨报表一致性校验响应"""
    all_passed: bool
    checks: list[ConsistencyCheckResult] = []


# ===================================================================
# 2. 报表格式配置 (ReportConfig)
# ===================================================================


class ReportConfigRow(BaseModel):
    """报表配置行"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_type: FinancialReportType
    row_number: int
    row_code: str
    row_name: str
    indent_level: int = 0
    formula: str | None = None
    applicable_standard: str
    is_total_row: bool = False
    parent_row_code: str | None = None


class ReportConfigCloneRequest(BaseModel):
    """克隆报表配置请求"""
    project_id: UUID
    applicable_standard: str = "enterprise"


# ===================================================================
# 3. 现金流量表工作底稿 (CFS Worksheet)
# ===================================================================


class CFSWorksheetRow(BaseModel):
    """工作底稿行"""
    account_code: str
    account_name: str | None = None
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    period_change: Decimal | None = None
    allocated_amount: Decimal | None = None
    unallocated_amount: Decimal | None = None


class CFSWorksheetData(BaseModel):
    """工作底稿数据"""
    project_id: UUID
    year: int
    rows: list[CFSWorksheetRow] = []
    is_balanced: bool = False


class CFSAdjustmentCreate(BaseModel):
    """创建CFS调整分录"""
    year: int
    description: str | None = None
    debit_account: str
    credit_account: str
    amount: Decimal
    cash_flow_category: CashFlowCategory | None = None
    cash_flow_line_item: str | None = None


class CFSAdjustmentUpdate(BaseModel):
    """修改CFS调整分录"""
    description: str | None = None
    debit_account: str | None = None
    credit_account: str | None = None
    amount: Decimal | None = None
    cash_flow_category: CashFlowCategory | None = None
    cash_flow_line_item: str | None = None


class CFSAdjustmentResponse(BaseModel):
    """CFS调整分录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    year: int
    adjustment_no: str
    description: str | None = None
    debit_account: str
    credit_account: str
    amount: Decimal
    cash_flow_category: CashFlowCategory | None = None
    cash_flow_line_item: str | None = None
    is_auto_generated: bool = False
    created_at: datetime | None = None


class CFSReconciliationRow(BaseModel):
    """平衡状态行"""
    account_code: str
    account_name: str | None = None
    period_change: Decimal | None = None
    allocated_total: Decimal | None = None
    unallocated: Decimal | None = None


class CFSReconciliation(BaseModel):
    """工作底稿平衡状态"""
    rows: list[CFSReconciliationRow] = []
    all_balanced: bool = False


class CFSCashReconciliation(BaseModel):
    """现金勾稽校验"""
    net_increase: Decimal | None = None
    closing_cash: Decimal | None = None
    opening_cash: Decimal | None = None
    expected_increase: Decimal | None = None
    is_reconciled: bool = False
    difference: Decimal | None = None


# ===================================================================
# 4. 附注 (Disclosure Notes)
# ===================================================================


class DisclosureNoteTreeNode(BaseModel):
    """附注目录树节点"""
    note_section: str
    section_title: str
    account_name: str | None = None
    content_type: ContentType | None = None
    status: NoteStatus = NoteStatus.draft
    sort_order: int | None = None
    children: list[DisclosureNoteTreeNode] = []


class DisclosureNoteTree(BaseModel):
    """附注目录树"""
    project_id: UUID
    year: int
    nodes: list[DisclosureNoteTreeNode] = []


class DisclosureNoteDetail(BaseModel):
    """附注章节详情"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    year: int
    note_section: str
    section_title: str
    account_name: str | None = None
    content_type: ContentType | None = None
    table_data: dict | None = None
    text_content: str | None = None
    source_template: SourceTemplate | None = None
    status: NoteStatus = NoteStatus.draft
    sort_order: int | None = None
    updated_at: datetime | None = None


class DisclosureNoteUpdate(BaseModel):
    """更新附注章节"""
    table_data: dict | None = None
    text_content: str | None = None
    status: NoteStatus | None = None


class DisclosureNoteGenerateRequest(BaseModel):
    """生成附注请求"""
    project_id: UUID
    year: int
    template_type: SourceTemplate = SourceTemplate.soe


# ===================================================================
# 5. 附注校验 (Note Validation)
# ===================================================================


class NoteValidationFinding(BaseModel):
    """校验发现"""
    note_section: str
    table_name: str | None = None
    check_type: str
    severity: str  # error / warning / info
    message: str
    expected_value: Decimal | None = None
    actual_value: Decimal | None = None
    cell_reference: str | None = None


class NoteValidationResponse(BaseModel):
    """校验结果响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    year: int
    validation_timestamp: datetime
    findings: list[dict] = []
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0


class NoteValidationFindingConfirm(BaseModel):
    """确认校验发现"""
    reason: str


# ===================================================================
# 6. 审计报告 (Audit Report)
# ===================================================================


class AuditReportGenerateRequest(BaseModel):
    """生成审计报告请求"""
    project_id: UUID
    year: int
    opinion_type: OpinionType
    company_type: CompanyType = CompanyType.non_listed


class AuditReportParagraph(BaseModel):
    """审计报告段落"""
    section_name: str
    content: str


class AuditReportResponse(BaseModel):
    """审计报告响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    year: int
    opinion_type: OpinionType
    company_type: CompanyType
    report_date: date | None = None
    signing_partner: str | None = None
    paragraphs: dict | None = None
    financial_data: dict | None = None
    status: ReportStatus = ReportStatus.draft
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AuditReportStatusUpdate(BaseModel):
    """更新审计报告状态"""
    status: ReportStatus


class AuditReportTemplateResponse(BaseModel):
    """审计报告模板响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    opinion_type: OpinionType
    company_type: CompanyType
    section_name: str
    section_order: int
    template_text: str
    is_required: bool = True


# ===================================================================
# 7. PDF导出 (Export)
# ===================================================================


class ExportTaskCreate(BaseModel):
    """创建导出任务"""
    project_id: UUID
    task_type: ExportTaskType = ExportTaskType.full_archive
    document_type: str | None = None
    password: str | None = None


class ExportTaskStatusResponse(BaseModel):
    """导出任务状态响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    task_type: ExportTaskType
    document_type: str | None = None
    status: ExportTaskStatus
    progress_percentage: int = 0
    file_path: str | None = None
    file_size: int | None = None
    password_protected: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None


class ExportHistoryResponse(BaseModel):
    """导出历史响应"""
    tasks: list[ExportTaskStatusResponse] = []
