"""集团合并相关 Pydantic Schema"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .consolidation_models import (
    CompetenceRating,
    ConsolMethod,
    EliminationEntryType,
    EvaluationStatusEnum,
    InclusionReason,
    InstructionStatus,
    OpinionTypeEnum,
    ReconciliationStatus,
    ReviewStatusEnum,
    ScopeChangeType,
    ScopeCompanyType,
    TradeType,
)


# ========== 1. 公司信息 ==========


class CompanyBase(BaseModel):
    company_code: str = Field(..., max_length=50)
    company_name: str = Field(..., max_length=255)
    parent_code: str | None = None
    shareholding: Decimal | None = Field(None, decimal_places=2, max_digits=5)
    consol_method: ConsolMethod | None = None
    acquisition_date: date | None = None
    disposal_date: date | None = None
    functional_currency: str = Field(default="CNY", max_length=3)
    is_active: bool = True


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    company_name: str | None = None
    parent_code: str | None = None
    shareholding: Decimal | None = None
    consol_method: ConsolMethod | None = None
    acquisition_date: date | None = None
    disposal_date: date | None = None
    functional_currency: str | None = None
    is_active: bool | None = None


class CompanyResponse(CompanyBase):
    id: UUID
    project_id: UUID
    ultimate_code: str
    consol_level: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanyTreeNode(CompanyResponse):
    children: list["CompanyTreeNode"] = Field(default_factory=list)


# ========== 2. 合并范围 ==========


class ConsolScopeBase(BaseModel):
    year: int
    company_code: str
    is_included: bool = True
    inclusion_reason: InclusionReason | None = None
    exclusion_reason: str | None = None
    scope_change_type: ScopeChangeType = ScopeChangeType.none
    scope_change_description: str | None = None


class ConsolScopeCreate(ConsolScopeBase):
    project_id: UUID
    company_name: str | None = None
    company_type: ScopeCompanyType | None = None
    ownership_ratio: Decimal | None = None


class ConsolScopeUpdate(BaseModel):
    is_included: bool | None = None
    inclusion_reason: InclusionReason | None = None
    exclusion_reason: str | None = None
    scope_change_type: ScopeChangeType | None = None
    scope_change_description: str | None = None


class ConsolScopeBatchUpdate(BaseModel):
    """批量更新合并范围"""
    scope_items: list[ConsolScopeCreate]


class ConsolScopeResponse(ConsolScopeBase):
    id: UUID
    project_id: UUID
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 3. 合并试算表 ==========


class ConsolTrialRow(BaseModel):
    standard_account_code: str
    account_name: str | None = None
    account_category: str | None = None
    individual_sum: Decimal = Field(default=Decimal("0"))
    consol_adjustment: Decimal = Field(default=Decimal("0"))
    consol_elimination: Decimal = Field(default=Decimal("0"))
    consol_amount: Decimal = Field(default=Decimal("0"))


class ConsolTrialUpdate(BaseModel):
    """Update schema for consolidation trial balance row"""
    account_name: str | None = None
    account_category: str | None = None
    individual_sum: Decimal | None = None
    consol_adjustment: Decimal | None = None
    consol_elimination: Decimal | None = None
    consol_amount: Decimal | None = None


class ConsolTrialResponse(ConsolTrialRow):
    id: UUID
    project_id: UUID
    year: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 4. 抵消分录 ==========


class EliminationEntryLine(BaseModel):
    """抵消分录行项"""
    account_code: str
    account_name: str | None = None
    debit_amount: Decimal = Field(default=Decimal("0"))
    credit_amount: Decimal = Field(default=Decimal("0"))


class EliminationEntryBase(BaseModel):
    year: int
    entry_type: EliminationEntryType
    description: str | None = None
    lines: list[EliminationEntryLine]


def _related_codes_as_list(value: Any) -> list[str] | None:
    """库里 ``related_company_codes`` 是 JSON：历史数据可能是 dict（取值）——统一成企业代码列表。"""
    if value is None:
        return None
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if isinstance(v, str) and v]
    return None


class EliminationEntryCreate(EliminationEntryBase):
    project_id: UUID
    related_company_codes: list[str] | None = None
    # 归属的差额节点（spec consol-tree-three-code-autobuild 需求 6.1）：空 = 本合并项目的「合并差额」；
    # 非空 = 该企业代码的「母分差额」（须由本合并项目承载，否则 400 并说明应到哪个合并项目录入）
    branch_entity_code: str | None = Field(default=None, max_length=50)


class EliminationEntryUpdate(BaseModel):
    entry_type: EliminationEntryType | None = None
    description: str | None = None
    lines: list[EliminationEntryLine] | None = None
    related_company_codes: list[str] | None = None
    # 显式传 null / 空串 = 改回「合并差额」；不传 = 不改
    branch_entity_code: str | None = Field(default=None, max_length=50)


class EliminationEntryResponse(EliminationEntryBase):
    id: UUID
    project_id: UUID
    entry_no: str
    entry_group_id: UUID
    debit_amount: Decimal = Field(default=Decimal("0"))
    credit_amount: Decimal = Field(default=Decimal("0"))
    related_company_codes: list[str] | None = None
    branch_entity_code: str | None = None
    # V172：来源（None=手工；ws_* 由合并工作底稿生成；legacy_sheet 旧版明细表转入）与来源键
    origin: str | None = None
    origin_key: str | None = None
    is_continuous: bool
    prior_year_entry_id: UUID | None = None
    review_status: ReviewStatusEnum
    reviewer_id: UUID | None = None
    reviewed_at: datetime | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("related_company_codes", mode="before")
    @classmethod
    def _normalize_related(cls, value: Any) -> list[str] | None:
        return _related_codes_as_list(value)

    @field_validator("lines", mode="before")
    @classmethod
    def _lines_or_empty(cls, value: Any) -> Any:
        # 旧数据只有表头（lines 为空）：响应给空列表而不是校验失败
        return value if isinstance(value, list) else []


class EliminationReviewAction(BaseModel):
    """抵消分录复核操作：submit 提交审批（草稿/已驳回 → 待审批）、approve 审批、reject 驳回、
    revoke 撤销审批（已审批 → 草稿；合并项目或其上层合并项目锁定时拒绝，spec consol-elimination-single-source-push 需求 8.2）。"""
    action: Literal["submit", "approve", "reject", "revoke"]
    rejection_reason: str | None = None


class EliminationSummary(BaseModel):
    """抵消分录汇总"""
    entry_type: EliminationEntryType
    count: int
    total_debit: Decimal
    total_credit: Decimal


# 合并工作底稿自动生成草稿分录（spec consol-elimination-single-source-push 需求 2，design §9.1）
WorksheetOrigin = Literal["ws_equity_sim", "ws_internal_arap", "ws_internal_trade"]


class WorksheetSourceLine(BaseModel):
    """来源分组的一行：科目名称 + 明细 + 借贷 + 金额（工作底稿按名称记录，编码由后端映射）。

    方向与金额不在这里拒收：认不出的方向 / 金额由生成接口逐组给原因（该组不生成），不让一行坏数据挡住整次请求。
    """
    subject: str = Field(default="", max_length=200)
    detail: str | None = Field(default=None, max_length=200)
    direction: str = Field(default="", max_length=10)   # 借 / 贷（也认 debit / credit）
    amount: Decimal | None = None


class WorksheetSourceGroup(BaseModel):
    """一个来源分组 ⇒ 一笔草稿分录；``origin_key`` 在来源内确定且稳定（重复生成按它更新同一笔草稿）。"""
    origin: WorksheetOrigin
    origin_key: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    # 不传 ⇒ 已有草稿沿用其类型（审计师可能改过），新建取来源默认类型
    entry_type: EliminationEntryType | None = None
    lines: list[WorksheetSourceLine] = Field(default_factory=list, max_length=500)
    related_company_codes: list[str] = Field(default_factory=list, max_length=200)


class GenerateFromWorksheetRequest(BaseModel):
    year: int
    # 本次请求负责的来源：这些来源里本次没有出现的来源键 ⇒ 其草稿软删。
    # 不传 = 分组里出现过的来源（某张表本次一组都没算出时，须显式列出它才会清理旧草稿）
    origins: list[WorksheetOrigin] | None = None
    groups: list[WorksheetSourceGroup] = Field(default_factory=list, max_length=2000)
    # 只预演：返回映射结果与将要发生的变化，不写库（明细表「待生成」预览用）
    dry_run: bool = False


class LegacySheetConvertRequest(BaseModel):
    """旧版明细表自定义行转为草稿分录（需求 1.6）。旧版行没有分录类型：不传按「其他调整」转入，审批前确认。"""
    year: int
    entry_type: EliminationEntryType | None = None


# 合并附注单元格公式（spec consol-elimination-single-source-push 需求 6.1 / 7.2）
class ConsolNoteFormulaCreate(BaseModel):
    template_type: Literal["soe", "listed"]
    section_id: str = Field(..., min_length=1, max_length=64)
    row_index: int = Field(..., ge=0, le=999)
    col_index: int = Field(..., ge=1, le=99)   # 第 0 列是项目名
    formula: str = Field(..., min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=500)


class ConsolNoteFormulaUpdate(BaseModel):
    formula: str | None = Field(default=None, min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=500)


# ========== 5. 内部交易 ==========


class InternalTradeCreate(BaseModel):
    year: int
    seller_company_code: str
    buyer_company_code: str
    trade_type: TradeType | None = None
    trade_amount: Decimal | None = None
    cost_amount: Decimal | None = None
    unrealized_profit: Decimal | None = None
    inventory_remaining_ratio: Decimal | None = None
    description: str | None = None


class InternalTradeUpdate(BaseModel):
    trade_type: TradeType | None = None
    trade_amount: Decimal | None = None
    cost_amount: Decimal | None = None
    unrealized_profit: Decimal | None = None
    inventory_remaining_ratio: Decimal | None = None
    description: str | None = None


class InternalTradeResponse(BaseModel):
    id: UUID
    project_id: UUID
    year: int
    seller_company_code: str
    buyer_company_code: str
    trade_type: TradeType | None = None
    trade_amount: Decimal | None = None
    cost_amount: Decimal | None = None
    unrealized_profit: Decimal | None = None
    inventory_remaining_ratio: Decimal | None = None
    description: str | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 6. 内部往来 ==========


class InternalArApCreate(BaseModel):
    year: int
    debtor_company_code: str
    creditor_company_code: str
    debtor_amount: Decimal | None = None
    creditor_amount: Decimal | None = None
    difference_amount: Decimal | None = None
    difference_reason: str | None = None
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.unmatched


class InternalArApUpdate(BaseModel):
    debtor_amount: Decimal | None = None
    creditor_amount: Decimal | None = None
    difference_amount: Decimal | None = None
    difference_reason: str | None = None
    reconciliation_status: ReconciliationStatus | None = None


class InternalArApResponse(BaseModel):
    id: UUID
    project_id: UUID
    year: int
    debtor_company_code: str
    creditor_company_code: str
    debtor_amount: Decimal | None = None
    creditor_amount: Decimal | None = None
    difference_amount: Decimal | None = None
    difference_reason: str | None = None
    reconciliation_status: ReconciliationStatus
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionMatrix(BaseModel):
    """交易矩阵"""
    company_codes: list[str]
    matrix: dict[str, dict[str, Decimal]]


# ========== 7. 商誉计算 ==========


class GoodwillInput(BaseModel):
    year: int
    subsidiary_company_code: str
    acquisition_date: date | None = None
    acquisition_cost: Decimal | None = None
    identifiable_net_assets_fv: Decimal | None = None
    parent_share_ratio: Decimal | None = None


class GoodwillCalcResponse(BaseModel):
    id: UUID
    project_id: UUID
    year: int
    subsidiary_company_code: str
    acquisition_date: date | None = None
    acquisition_cost: Decimal | None = None
    identifiable_net_assets_fv: Decimal | None = None
    parent_share_ratio: Decimal | None = None
    goodwill_amount: Decimal | None = None
    accumulated_impairment: Decimal
    current_year_impairment: Decimal
    carrying_amount: Decimal | None = None
    is_negative_goodwill: bool
    negative_goodwill_treatment: str | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 8. 少数股东权益 ==========


class MinorityInterestResult(BaseModel):
    year: int
    subsidiary_company_code: str
    subsidiary_net_assets: Decimal | None = None
    minority_share_ratio: Decimal | None = None
    minority_equity: Decimal | None = None
    subsidiary_net_profit: Decimal | None = None
    minority_profit: Decimal | None = None
    minority_equity_opening: Decimal | None = None
    minority_equity_movement: dict | None = None
    is_excess_loss: bool
    excess_loss_amount: Decimal


class MinorityInterestResponse(MinorityInterestResult):
    id: UUID
    project_id: UUID
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 9. 外币折算 ==========


class ForexRates(BaseModel):
    """汇率信息"""
    functional_currency: str
    bs_closing_rate: Decimal | None = None
    pl_average_rate: Decimal | None = None
    equity_historical_rate: Decimal | None = None


class TranslationWorksheet(BaseModel):
    """折算工作底稿"""
    year: int
    company_code: str
    functional_currency: str
    opening_retained_earnings_translated: Decimal | None = None
    translation_difference: Decimal | None = None
    translation_difference_oci: Decimal | None = None


class ForexTranslationResponse(BaseModel):
    id: UUID
    project_id: UUID
    year: int
    company_code: str
    functional_currency: str
    reporting_currency: str
    bs_closing_rate: Decimal | None = None
    pl_average_rate: Decimal | None = None
    equity_historical_rate: Decimal | None = None
    opening_retained_earnings_translated: Decimal | None = None
    translation_difference: Decimal | None = None
    translation_difference_oci: Decimal | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 10. 组成部分审计师 ==========


class ComponentAuditorCreate(BaseModel):
    company_code: str
    firm_name: str
    contact_person: str | None = None
    contact_info: str | None = None
    competence_rating: CompetenceRating
    rating_basis: str | None = None
    independence_confirmed: bool = False
    independence_date: date | None = None


class ComponentAuditorUpdate(BaseModel):
    firm_name: str | None = None
    contact_person: str | None = None
    contact_info: str | None = None
    competence_rating: CompetenceRating | None = None
    rating_basis: str | None = None
    independence_confirmed: bool | None = None
    independence_date: date | None = None


class ComponentAuditorResponse(BaseModel):
    id: UUID
    project_id: UUID
    company_code: str
    firm_name: str
    contact_person: str | None = None
    contact_info: str | None = None
    competence_rating: CompetenceRating | None = None
    rating_basis: str | None = None
    independence_confirmed: bool
    independence_date: date | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 11. 组成部分指令 ==========


class InstructionCreate(BaseModel):
    component_auditor_id: UUID
    instruction_date: date | None = None
    due_date: date | None = None
    materiality_level: Decimal | None = None
    audit_scope_description: str | None = None
    reporting_format: str | None = None
    special_attention_items: str | None = None
    instruction_file_path: str | None = None


class InstructionUpdate(BaseModel):
    instruction_date: date | None = None
    due_date: date | None = None
    materiality_level: Decimal | None = None
    audit_scope_description: str | None = None
    reporting_format: str | None = None
    special_attention_items: str | None = None
    instruction_file_path: str | None = None
    status: InstructionStatus | None = None


class InstructionResponse(BaseModel):
    id: UUID
    project_id: UUID
    component_auditor_id: UUID
    instruction_date: date | None = None
    due_date: date | None = None
    materiality_level: Decimal | None = None
    audit_scope_description: str | None = None
    reporting_format: str | None = None
    special_attention_items: str | None = None
    instruction_file_path: str | None = None
    status: InstructionStatus
    sent_at: datetime | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 12. 组成部分结果 ==========


class ResultCreate(BaseModel):
    component_auditor_id: UUID
    received_date: date | None = None
    opinion_type: OpinionTypeEnum | None = None
    identified_misstatements: dict | None = None
    significant_findings: str | None = None
    result_file_path: str | None = None
    group_team_evaluation: str | None = None
    needs_additional_procedures: bool = False


class ResultUpdate(BaseModel):
    received_date: date | None = None
    opinion_type: OpinionTypeEnum | None = None
    identified_misstatements: dict | None = None
    significant_findings: str | None = None
    result_file_path: str | None = None
    group_team_evaluation: str | None = None
    needs_additional_procedures: bool | None = None
    evaluation_status: EvaluationStatusEnum | None = None


class ResultResponse(BaseModel):
    id: UUID
    project_id: UUID
    component_auditor_id: UUID
    received_date: date | None = None
    opinion_type: OpinionTypeEnum | None = None
    identified_misstatements: dict | None = None
    significant_findings: str | None = None
    result_file_path: str | None = None
    group_team_evaluation: str | None = None
    needs_additional_procedures: bool
    evaluation_status: EvaluationStatusEnum
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 合并附注 ==========


class ConsolDisclosureRow(BaseModel):
    """合并附注行"""
    row_index: int | None = None
    col1: str | None = Field(None, alias="col_1")
    col2: str | None = Field(None, alias="col_2")
    col3: str | None = Field(None, alias="col_3")
    col4: str | None = Field(None, alias="col_4")
    col5: str | None = Field(None, alias="col_5")
    col6: str | None = Field(None, alias="col_6")

    model_config = ConfigDict(populate_by_name=True)


class ConsolDisclosureSection(BaseModel):
    """合并附注章节"""
    section_code: str
    section_title: str
    content: str | None = None
    rows: list[ConsolDisclosureRow] = Field(default_factory=list)
    is_editable: bool = True
    is_group_header: bool = False


# ========== 合并报表 ==========


class ConsolReportRow(BaseModel):
    """合并报表行"""
    row_code: str
    row_name: str
    row_index: int = 0
    indent_level: int = 0
    is_bold: bool = False
    is_total: bool = False
    is_total_row: bool = False
    current_period_amount: Decimal | str | None = Decimal("0")
    prior_period_amount: Decimal | str | None = Decimal("0")
    formula_used: str | None = None
    source_accounts: dict | list | None = None
    # V173：金额留空时的原因（公式取数超出合并口径 / 引用了留空行）；有值的行为 None
    blank_reason: str | None = None
    # 推送后下游数据（子企业试算表）已变化 ⇒ 该行待重新推送
    is_stale: bool = False


class ConsolWorkpaperResult(BaseModel):
    """合并底稿生成结果"""
    file_name: str
    file_data: bytes | None = None


class BalanceCheckResult(BaseModel):
    """资产负债表平衡校验结果"""
    is_balanced: bool
    total_assets: Decimal = Decimal("0")
    total_liabilities: Decimal = Decimal("0")
    total_equity: Decimal = Decimal("0")
    difference: Decimal = Decimal("0")
    minority_interest: Decimal | None = None
    goodwill: Decimal | None = None
    issues: list[str] = Field(default_factory=list)


class ConsolReportGenerateRequest(BaseModel):
    """合并报表生成请求。

    ``applicable_standard`` 可选：``soe_consolidated`` / ``listed_consolidated`` 照用；不传或其他值
    （含旧前端传的 ``CAS``）按项目模板类型解析，响应里给出实际口径（spec consol-elimination-single-source-push §4.4）。
    """
    project_id: UUID
    year: int
    applicable_standard: str | None = None


class ConsolNotesGenerateRequest(BaseModel):
    """合并附注生成请求"""
    project_id: UUID
    year: int
    include_subsidiaries: bool = True
    include_goodwill: bool = True
    include_mi: bool = True
    include_internal_trade: bool = True
    include_forex: bool = True


# ========== 看板与汇总 ==========


class ComponentDashboard(BaseModel):
    """组成部分审计师看板"""
    total_auditors: int
    pending_instructions: int
    pending_results: int
    received_results: int
    non_standard_opinions: int


class ConsolScopeSummary(BaseModel):
    """合并范围汇总"""
    total_companies: int
    included_companies: int
    excluded_companies: int
    scope_changes: int


# ========== 集团结构校验 ==========


class ConsistencyCheckResult(BaseModel):
    """一致性校验结果"""
    is_balanced: bool
    total_debit: Decimal
    total_credit: Decimal
    difference: Decimal
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StructureValidationResult(BaseModel):
    """集团结构校验结果"""
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# 修复前向引用
CompanyTreeNode.model_rebuild()

# Alias for existing code that uses EliminationCreate
EliminationCreate = EliminationEntryCreate
