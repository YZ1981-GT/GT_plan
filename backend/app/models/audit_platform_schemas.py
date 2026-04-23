"""第一阶段MVP核心：Pydantic Schema 定义

覆盖所有 API 请求/响应模型：
- 项目向导 (BasicInfoSchema, WizardState)
- 科目表 (AccountChartResponse, AccountTreeNode)
- 科目映射 (MappingInput, MappingSuggestion, MappingResult)
- 报表行次映射 (ReportLineMappingResponse, ReferenceCopyResult)
- 数据导入 (ImportProgress, ImportBatchResponse, DuplicateAction)
- 四表穿透 (BalanceFilter, LedgerFilter, BalanceRow, LedgerRow, AuxBalanceRow, AuxLedgerRow)
- 试算表 (TrialBalanceRow, ConsistencyReport)
- 调整分录 (AdjustmentCreate, AdjustmentUpdate, AdjustmentSummary)
- 重要性水平 (MaterialityInput, MaterialityResult, MaterialityOverride)
- 未更正错报 (MisstatementCreate, MisstatementSummary, ThresholdResult)
- 事件总线 (EventPayload)
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.audit_platform_models import (
    AccountCategory,
    AccountDirection,
    AccountSource,
    AdjustmentType,
    ImportStatus,
    MappingType,
    ReviewStatus,
)


# ===================================================================
# 通用 / 分页
# ===================================================================


class PageParams(BaseModel):
    """分页参数"""
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class PageResult(BaseModel):
    """分页结果包装"""
    items: list[Any] = []
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 0


class ValidationMessage(BaseModel):
    """校验消息"""
    field: str
    message: str
    severity: str = "error"  # error | warning


class ValidationResult(BaseModel):
    """校验结果"""
    valid: bool
    messages: list[ValidationMessage] = []


# ===================================================================
# 1. 项目向导 (ProjectWizard)
# ===================================================================


class WizardStep(str, enum.Enum):
    """向导步骤"""
    basic_info = "basic_info"
    account_import = "account_import"
    account_mapping = "account_mapping"
    materiality = "materiality"
    team_assignment = "team_assignment"
    template_set = "template_set"
    confirmation = "confirmation"


class BasicInfoSchema(BaseModel):
    """步骤1 - 基本信息"""
    client_name: str
    audit_year: int
    project_type: str  # annual / special / ipo / internal_control
    accounting_standard: str  # enterprise / small_enterprise / financial / government
    company_code: str | None = None  # 企业代码（统一社会信用代码）
    template_type: str | None = None  # 附注模板类型：soe（国企版）/ listed（上市版）
    report_scope: str | None = None  # 报表类型：standalone（单户）/ consolidated（合并）
    parent_company_name: str | None = None  # 上级企业名称（合并报表时填写）
    parent_company_code: str | None = None  # 上级企业代码
    ultimate_company_name: str | None = None  # 最终控制方名称
    ultimate_company_code: str | None = None  # 最终控制方代码
    signing_partner_id: UUID | None = None
    manager_id: UUID | None = None


class TeamMemberAssignment(BaseModel):
    """团队成员分工"""
    user_id: UUID
    role: str
    assigned_cycles: list[str] = []


class TeamAssignmentSchema(BaseModel):
    """步骤5 - 团队分工"""
    members: list[TeamMemberAssignment] = []


class TemplateSetSchema(BaseModel):
    """步骤6 - 底稿模板集"""
    template_set_id: UUID | None = None
    template_set_name: str | None = None


class WizardStepData(BaseModel):
    """单步骤数据"""
    step: WizardStep
    data: dict[str, Any] = {}
    completed: bool = False


class WizardState(BaseModel):
    """向导完整状态"""
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    current_step: WizardStep = WizardStep.basic_info
    steps: dict[str, WizardStepData] = {}
    completed: bool = False


class ProjectCreateResponse(BaseModel):
    """项目创建响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None = None
    client_name: str
    audit_year: int | None = None
    project_type: str | None = None
    status: str
    report_scope: str | None = None
    parent_project_id: UUID | None = None
    consol_level: int = 1
    created_at: datetime


# ===================================================================
# 2. 科目表 (AccountChart)
# ===================================================================


class AccountChartResponse(BaseModel):
    """科目表记录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    account_code: str
    account_name: str
    direction: AccountDirection
    level: int
    category: AccountCategory
    parent_code: str | None = None
    source: AccountSource
    created_at: datetime


class AccountTreeNode(BaseModel):
    """科目树节点（前端树形展示）"""
    account_code: str
    account_name: str
    direction: AccountDirection
    level: int
    category: AccountCategory
    parent_code: str | None = None
    children: list[AccountTreeNode] = []


class AccountImportResult(BaseModel):
    """科目导入结果"""
    total_imported: int
    by_category: dict[str, int] = {}
    errors: list[str] = []
    data_sheets_imported: dict[str, int] = {}  # {data_type: record_count}
    sheet_diagnostics: list[dict] = []  # [{sheet_name, guessed_type, matched_cols, missing_cols, row_count}]
    year: int | None = None


# ===================================================================
# 3. 科目映射 (AccountMapping)
# ===================================================================


class MappingInput(BaseModel):
    """保存/确认映射请求"""
    original_account_code: str
    original_account_name: str | None = None
    standard_account_code: str
    mapping_type: MappingType = MappingType.manual
    year: int | None = None


class MappingUpdateInput(BaseModel):
    standard_account_code: str
    year: int | None = None


class MappingYearInput(BaseModel):
    year: int | None = None


class MappingSuggestion(BaseModel):
    """自动映射建议"""
    original_account_code: str
    original_account_name: str | None = None
    suggested_standard_code: str
    suggested_standard_name: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    match_method: str  # prefix / exact_name / fuzzy_name


class MappingResponse(BaseModel):
    """映射记录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    original_account_code: str
    original_account_name: str | None = None
    standard_account_code: str
    mapping_type: MappingType
    created_at: datetime


class MappingResult(BaseModel):
    """批量确认映射结果"""
    confirmed_count: int
    total_count: int
    completion_rate: float


class AutoMatchResult(BaseModel):
    """自动匹配并保存的结果"""
    saved_count: int
    skipped_count: int
    unmatched_count: int
    total_client: int
    completion_rate: float
    details: list[MappingSuggestion] = []


class MappingCompletionRate(BaseModel):
    """映射完成率"""
    mapped_count: int
    total_count: int
    completion_rate: float
    unmapped_with_balance: list[dict[str, Any]] = []


# ===================================================================
# 3a. 报表行次映射 (ReportLineMapping)
# ===================================================================


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


class ReportLineMappingResponse(BaseModel):
    """报表行次映射响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    standard_account_code: str
    report_type: ReportType
    report_line_code: str
    report_line_name: str
    report_line_level: int
    parent_line_code: str | None = None
    mapping_type: ReportLineMappingType
    is_confirmed: bool
    confidence_score: float | None = None
    created_at: datetime


class ReportLineMappingConfirm(BaseModel):
    """确认报表行次映射"""
    mapping_ids: list[UUID]


class ReferenceCopyRequest(BaseModel):
    """集团参照复制请求"""
    source_company_code: str


class ReferenceCopyResult(BaseModel):
    """集团参照复制结果"""
    copied_count: int
    unmatched_accounts: list[str] = []


class ReportLine(BaseModel):
    """报表行次（供调整分录下拉）"""
    report_line_code: str
    report_line_name: str
    report_line_level: int
    report_type: ReportType


# ===================================================================
# 4. 数据导入 (Import)
# ===================================================================


class ImportStartRequest(BaseModel):
    """启动导入请求（表单字段，文件通过 UploadFile 传入）"""
    source_type: str = "generic"  # yonyou / kingdee / sap / generic
    data_type: str  # balance / ledger / aux_balance / aux_ledger
    year: int | None = None


class ImportProgress(BaseModel):
    """导入进度（SSE / 轮询）"""
    batch_id: UUID
    status: ImportStatus
    stage: str = "pending"  # parsing / validating / importing / completed / failed
    records_processed: int = 0
    total_records: int = 0
    progress_percent: float = 0.0
    elapsed_seconds: float = 0.0
    validation_warnings: list[str] = []
    error_message: str | None = None


class ImportBatchResponse(BaseModel):
    """导入批次响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    year: int
    source_type: str
    file_name: str
    data_type: str
    record_count: int
    status: ImportStatus
    validation_summary: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class DuplicateAction(BaseModel):
    """重复记录处理"""
    action: str  # skip / overwrite


class RuleResult(BaseModel):
    """单条校验规则结果"""
    rule_name: str
    severity: str  # reject / warning
    passed: bool
    message: str | None = None
    details: list[dict[str, Any]] = []


class ImportValidationResult(BaseModel):
    """导入校验汇总"""
    passed: bool
    rules: list[RuleResult] = []
    has_reject: bool = False
    has_warning: bool = False


# ===================================================================
# 5. 四表穿透 (Drilldown)
# ===================================================================


class BalanceFilter(BaseModel):
    """科目余额表筛选"""
    category: AccountCategory | None = None
    level: int | None = None
    keyword: str | None = None
    year: int | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class LedgerFilter(BaseModel):
    """序时账筛选"""
    date_from: date | None = None
    date_to: date | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    voucher_no: str | None = None
    summary_keyword: str | None = None
    counterpart_account: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class AuxFilter(BaseModel):
    """辅助余额/明细筛选"""
    aux_type: str | None = None
    aux_code: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class BalanceRow(BaseModel):
    """科目余额表行"""
    model_config = ConfigDict(from_attributes=True)

    account_code: str
    account_name: str | None = None
    opening_balance: Decimal | None = None
    debit_amount: Decimal | None = None
    credit_amount: Decimal | None = None
    closing_balance: Decimal | None = None
    has_aux: bool = False


class LedgerRow(BaseModel):
    """序时账行"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    voucher_date: date
    voucher_no: str
    account_code: str
    account_name: str | None = None
    debit_amount: Decimal | None = None
    credit_amount: Decimal | None = None
    counterpart_account: str | None = None
    summary: str | None = None
    preparer: str | None = None
    running_balance: Decimal | None = None


class AuxBalanceRow(BaseModel):
    """辅助余额表行"""
    model_config = ConfigDict(from_attributes=True)

    aux_type: str
    aux_code: str | None = None
    aux_name: str | None = None
    opening_balance: Decimal | None = None
    debit_amount: Decimal | None = None
    credit_amount: Decimal | None = None
    closing_balance: Decimal | None = None


class AuxLedgerRow(BaseModel):
    """辅助明细账行"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    voucher_date: date | None = None
    voucher_no: str | None = None
    account_code: str
    aux_type: str | None = None
    aux_code: str | None = None
    aux_name: str | None = None
    debit_amount: Decimal | None = None
    credit_amount: Decimal | None = None
    summary: str | None = None
    preparer: str | None = None


# ===================================================================
# 6. 试算表 (TrialBalance)
# ===================================================================


class TrialBalanceRow(BaseModel):
    """试算表行"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    standard_account_code: str
    account_name: str | None = None
    account_category: AccountCategory
    unadjusted_amount: Decimal | None = None
    rje_adjustment: Decimal = Decimal("0")
    aje_adjustment: Decimal = Decimal("0")
    audited_amount: Decimal | None = None
    opening_balance: Decimal | None = None


class TrialBalanceCategorySubtotal(BaseModel):
    """试算表分类小计"""
    category: AccountCategory
    unadjusted_total: Decimal = Decimal("0")
    rje_total: Decimal = Decimal("0")
    aje_total: Decimal = Decimal("0")
    audited_total: Decimal = Decimal("0")
    rows: list[TrialBalanceRow] = []


class TrialBalanceResponse(BaseModel):
    """试算表完整响应"""
    categories: list[TrialBalanceCategorySubtotal] = []
    grand_total_unadjusted: Decimal = Decimal("0")
    grand_total_rje: Decimal = Decimal("0")
    grand_total_aje: Decimal = Decimal("0")
    grand_total_audited: Decimal = Decimal("0")
    is_balanced: bool = True


class ConsistencyCheckItem(BaseModel):
    """一致性校验项"""
    check_name: str
    passed: bool
    expected_value: Decimal | None = None
    actual_value: Decimal | None = None
    difference: Decimal | None = None
    account_code: str | None = None


class ConsistencyReport(BaseModel):
    """数据一致性校验报告"""
    all_passed: bool
    checks: list[ConsistencyCheckItem] = []
    checked_at: datetime | None = None


# ===================================================================
# 7. 调整分录 (Adjustment)
# ===================================================================


class AdjustmentLineItem(BaseModel):
    """调整分录明细行"""
    standard_account_code: str
    account_name: str | None = None
    report_line_code: str | None = None
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")


class AdjustmentCreate(BaseModel):
    """创建调整分录"""
    adjustment_type: AdjustmentType
    year: int
    company_code: str = "default"
    description: str | None = None
    line_items: list[AdjustmentLineItem] = Field(min_length=1)


class AdjustmentUpdate(BaseModel):
    """修改调整分录"""
    description: str | None = None
    line_items: list[AdjustmentLineItem] | None = None


class AdjustmentEntryResponse(BaseModel):
    """调整分录明细行响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    line_no: int
    standard_account_code: str
    account_name: str | None = None
    report_line_code: str | None = None
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")


class AdjustmentGroupResponse(BaseModel):
    """调整分录组响应"""
    entry_group_id: UUID
    adjustment_no: str
    adjustment_type: AdjustmentType
    description: str | None = None
    review_status: ReviewStatus
    reviewer_id: UUID | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    total_debit: Decimal = Decimal("0")
    total_credit: Decimal = Decimal("0")
    line_items: list[AdjustmentEntryResponse] = []
    created_by: UUID | None = None
    created_at: datetime | None = None


class ReviewStatusChange(BaseModel):
    """变更复核状态"""
    status: ReviewStatus
    reason: str | None = None  # rejected 时必填


class AdjustmentSummary(BaseModel):
    """调整分录汇总统计"""
    aje_count: int = 0
    rje_count: int = 0
    aje_total_debit: Decimal = Decimal("0")
    aje_total_credit: Decimal = Decimal("0")
    rje_total_debit: Decimal = Decimal("0")
    rje_total_credit: Decimal = Decimal("0")
    status_counts: dict[str, int] = {}


class AdjustmentFilter(BaseModel):
    """调整分录筛选"""
    adjustment_type: AdjustmentType | None = None
    review_status: ReviewStatus | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class AccountOption(BaseModel):
    """科目下拉选项"""
    code: str
    name: str
    level: int = 1


class WPAdjustmentDetail(BaseModel):
    """底稿审定表中的单笔调整明细"""
    entry_group_id: UUID
    adjustment_no: str
    adjustment_type: AdjustmentType
    description: str | None = None
    amount: Decimal = Decimal("0")


class WPAdjustmentSummary(BaseModel):
    """底稿审定表数据"""
    wp_code: str
    accounts: list[str] = []
    unadjusted_amount: Decimal = Decimal("0")
    aje_details: list[WPAdjustmentDetail] = []
    rje_details: list[WPAdjustmentDetail] = []
    aje_total: Decimal = Decimal("0")
    rje_total: Decimal = Decimal("0")
    audited_amount: Decimal = Decimal("0")


# ===================================================================
# 8. 重要性水平 (Materiality)
# ===================================================================


class MaterialityInput(BaseModel):
    """重要性水平计算输入"""
    benchmark_type: str  # pre_tax_profit / revenue / total_assets / net_assets / custom
    benchmark_amount: Decimal
    overall_percentage: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    performance_ratio: Decimal = Field(
        default=Decimal("50"), ge=Decimal("0"), le=Decimal("100")
    )
    trivial_ratio: Decimal = Field(
        default=Decimal("5"), ge=Decimal("0"), le=Decimal("100")
    )
    notes: str | None = None


class MaterialityResult(BaseModel):
    """重要性水平计算结果"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    project_id: UUID | None = None
    year: int | None = None
    benchmark_type: str
    benchmark_amount: Decimal
    overall_percentage: Decimal
    overall_materiality: Decimal
    performance_ratio: Decimal
    performance_materiality: Decimal
    trivial_ratio: Decimal
    trivial_threshold: Decimal
    is_override: bool = False
    override_reason: str | None = None
    notes: str | None = None
    calculated_by: UUID | None = None
    calculated_at: datetime | None = None


class MaterialityOverride(BaseModel):
    """手动覆盖重要性水平"""
    overall_materiality: Decimal | None = None
    performance_materiality: Decimal | None = None
    trivial_threshold: Decimal | None = None
    override_reason: str


class MaterialityChange(BaseModel):
    """重要性水平变更历史"""
    changed_at: datetime
    changed_by: UUID | None = None
    field_name: str
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None


# ===================================================================
# 9. 事件总线 (EventBus)
# ===================================================================


class EventType(str, enum.Enum):
    """事件类型"""
    ADJUSTMENT_CREATED = "adjustment.created"
    ADJUSTMENT_UPDATED = "adjustment.updated"
    ADJUSTMENT_DELETED = "adjustment.deleted"
    MAPPING_CHANGED = "mapping.changed"
    DATA_IMPORTED = "data.imported"
    IMPORT_ROLLED_BACK = "import.rolled_back"
    IMPORT_PROGRESS = "import.progress"
    MATERIALITY_CHANGED = "materiality.changed"
    TRIAL_BALANCE_UPDATED = "trial_balance.updated"
    REPORTS_UPDATED = "reports.updated"
    WORKPAPER_SAVED = "workpaper.saved"
    NOTE_UPDATED = "note.updated"


class EventPayload(BaseModel):
    """事件载荷"""
    event_type: EventType
    project_id: UUID
    year: int | None = None
    account_codes: list[str] | None = None
    batch_id: UUID | None = None
    entry_group_id: UUID | None = None
    extra: dict[str, Any] = {}


# ===================================================================
# 10. 未更正错报 (UnadjustedMisstatement)
# ===================================================================


class MisstatementType(str, enum.Enum):
    """错报类型"""
    factual = "factual"
    judgmental = "judgmental"
    projected = "projected"


class MisstatementCreate(BaseModel):
    """创建未更正错报"""
    year: int
    source_adjustment_id: UUID | None = None
    misstatement_description: str
    affected_account_code: str | None = None
    affected_account_name: str | None = None
    misstatement_amount: Decimal
    misstatement_type: MisstatementType
    management_reason: str | None = None
    auditor_evaluation: str | None = None


class MisstatementUpdate(BaseModel):
    """更新未更正错报"""
    misstatement_description: str | None = None
    affected_account_code: str | None = None
    affected_account_name: str | None = None
    misstatement_amount: Decimal | None = None
    misstatement_type: MisstatementType | None = None
    management_reason: str | None = None
    auditor_evaluation: str | None = None


class MisstatementResponse(BaseModel):
    """未更正错报响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    year: int
    source_adjustment_id: UUID | None = None
    misstatement_description: str
    affected_account_code: str | None = None
    affected_account_name: str | None = None
    misstatement_amount: Decimal
    misstatement_type: MisstatementType
    management_reason: str | None = None
    auditor_evaluation: str | None = None
    is_carried_forward: bool = False
    prior_year_id: UUID | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None


class MisstatementCategorySummary(BaseModel):
    """按类型分组的错报小计"""
    misstatement_type: MisstatementType
    count: int = 0
    total_amount: Decimal = Decimal("0")


class MisstatementSummary(BaseModel):
    """未更正错报汇总"""
    by_type: list[MisstatementCategorySummary] = []
    cumulative_amount: Decimal = Decimal("0")
    overall_materiality: Decimal | None = None
    performance_materiality: Decimal | None = None
    trivial_threshold: Decimal | None = None
    exceeds_materiality: bool = False
    evaluation_complete: bool = False


class ThresholdResult(BaseModel):
    """重要性水平对比结果"""
    cumulative_amount: Decimal
    overall_materiality: Decimal
    exceeds: bool
    warning_message: str | None = None
