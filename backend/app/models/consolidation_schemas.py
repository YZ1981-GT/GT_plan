"""集团合并相关 Pydantic Schema"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


# ========== 3. 合并试算表 ==========


class ConsolTrialRow(BaseModel):
    standard_account_code: str
    account_name: str | None = None
    account_category: str | None = None
    individual_sum: Decimal = Field(default=Decimal("0"))
    consol_adjustment: Decimal = Field(default=Decimal("0"))
    consol_elimination: Decimal = Field(default=Decimal("0"))
    consol_amount: Decimal = Field(default=Decimal("0"))


class ConsolTrialResponse(ConsolTrialRow):
    id: UUID
    project_id: UUID
    year: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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


class EliminationEntryCreate(EliminationEntryBase):
    project_id: UUID
    related_company_codes: list[str] | None = None


class EliminationEntryUpdate(BaseModel):
    entry_type: EliminationEntryType | None = None
    description: str | None = None
    lines: list[EliminationEntryLine] | None = None
    related_company_codes: list[str] | None = None


class EliminationEntryResponse(EliminationEntryBase):
    id: UUID
    project_id: UUID
    entry_no: str
    entry_group_id: UUID
    is_continuous: bool
    prior_year_entry_id: UUID | None = None
    review_status: ReviewStatusEnum
    reviewer_id: UUID | None = None
    reviewed_at: datetime | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EliminationReviewAction(BaseModel):
    """抵消分录复核操作"""
    action: Literal["approve", "reject"]
    rejection_reason: str | None = None


class EliminationSummary(BaseModel):
    """抵消分录汇总"""
    entry_type: EliminationEntryType
    count: int
    total_debit: Decimal
    total_credit: Decimal


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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


class StructureValidationResult(BaseModel):
    """集团结构校验结果"""
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# 修复前向引用
CompanyTreeNode.model_rebuild()
