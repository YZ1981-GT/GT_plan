"""集团合并相关 Pydantic Schema（对应 Migration 009）

覆盖所有 12 张表的 API 请求/响应模型：
1. Company        - 公司信息
2. ConsolScope   - 合并范围
3. ConsolTrial   - 合并试算表
4. EliminationEntry - 抵消分录
5. InternalTrade - 内部交易
6. InternalArAp  - 内部往来
7. GoodwillCalc  - 商誉计算
8. MinorityInterest - 少数股东权益
9. ForexTranslation - 外币折算
10. ComponentAuditor - 组成部分审计师
11. ComponentInstruction - 审计指令
12. ComponentResult - 组成部分审计结果

使用 Pydantic v2 风格。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.consolidation_models import (
    AccountCategory,
    CompetenceRating,
    ConsolMethod,
    EliminationEntryType,
    EvaluationStatus,
    InclusionReason,
    InstructionStatus,
    OpinionTypeEnum,
    ReconciliationStatus,
    ReviewStatusEnum,
    ScopeChangeType,
    TradeType,
)


# ===================================================================
# 通用 / 分页
# ===================================================================


class PageParams(BaseModel):
    """分页参数"""
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


PaginationParams = PageParams  # alias for backward compatibility


class PageResult(BaseModel):
    """分页结果包装"""
    items: list[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 0


# ===================================================================
# 1. Company (公司信息)
# ===================================================================


class CompanyBase(BaseModel):
    """公司基础字段"""
    company_code: str = Field(..., max_length=50)
    company_name: str = Field(..., max_length=255)
    parent_code: str | None = Field(None, max_length=50)
    ultimate_code: str = Field(..., max_length=50)
    consol_level: int = Field(default=0, ge=0)
    shareholding: Decimal | None = Field(None, decimal_places=2, max_digits=5)
    consol_method: ConsolMethod | None = None
    acquisition_date: date | None = None
    disposal_date: date | None = None
    functional_currency: str = Field(default="CNY", max_length=3)
    is_active: bool = True


class CompanyCreate(CompanyBase):
    """创建公司"""
    project_id: UUID


class CompanyUpdate(BaseModel):
    """更新公司"""
    company_name: str | None = None
    parent_code: str | None = None
    ultimate_code: str | None = None
    consol_level: int | None = None
    shareholding: Decimal | None = None
    consol_method: ConsolMethod | None = None
    acquisition_date: date | None = None
    disposal_date: date | None = None
    functional_currency: str | None = None
    is_active: bool | None = None


class CompanyResponse(CompanyBase):
    """公司响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class CompanyTreeNode(CompanyResponse):
    """公司树节点（递归结构）"""
    children: list["CompanyTreeNode"] = Field(default_factory=list)


class CompanyTreeResponse(BaseModel):
    """公司树根节点"""
    nodes: list[CompanyTreeNode] = Field(default_factory=list)


class StructureValidationResult(BaseModel):
    """集团结构校验结果"""
    is_valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConsolidationPeriod(BaseModel):
    """合并期间信息"""
    include_pl: bool = True
    include_bs: bool = True
    period_months: int = 12
    note: str = ""


class OwnershipTypeEnum(str, enum.Enum):
    """股权性质"""
    direct = "direct"
    indirect = "indirect"
    joint = "joint"


# ===================================================================
# 2. ConsolScope (合并范围)
# ===================================================================


class ConsolScopeBase(BaseModel):
    """合并范围基础字段"""
    year: int
    company_code: str = Field(..., max_length=50)
    is_included: bool = True
    inclusion_reason: InclusionReason | None = None
    exclusion_reason: str | None = None
    scope_change_type: ScopeChangeType = ScopeChangeType.none
    scope_change_description: str | None = None


class ConsolScopeCreate(ConsolScopeBase):
    """创建合并范围"""
    project_id: UUID


class ConsolScopeUpdate(BaseModel):
    """更新合并范围"""
    is_included: bool | None = None
    inclusion_reason: InclusionReason | None = None
    exclusion_reason: str | None = None
    scope_change_type: ScopeChangeType | None = None
    scope_change_description: str | None = None


class ConsolScopeBatchCreate(BaseModel):
    """批量创建合并范围"""
    scope_items: list[ConsolScopeCreate]


class ConsolScopeResponse(ConsolScopeBase):
    """合并范围响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class ConsolScopeSummary(BaseModel):
    """合并范围汇总"""
    total_companies: int = 0
    included_companies: int = 0
    excluded_companies: int = 0
    scope_changes: int = 0


class ConsolScopeBatchUpdate(BaseModel):
    """批量更新合并范围"""
    scope_items: list[ConsolScopeCreate]


class ConsolTrialRow(BaseModel):
    """合并试算表行"""
    standard_account_code: str = Field(..., max_length=50)
    account_name: str | None = None
    account_category: AccountCategory | None = None
    individual_sum: Decimal = Field(default=Decimal("0"))
    consol_adjustment: Decimal = Field(default=Decimal("0"))
    consol_elimination: Decimal = Field(default=Decimal("0"))
    consol_amount: Decimal = Field(default=Decimal("0"))


class ConsolTrialCreate(BaseModel):
    """创建合并试算表行"""
    project_id: UUID
    year: int
    standard_account_code: str = Field(..., max_length=50)
    account_name: str | None = None
    account_category: AccountCategory | None = None
    individual_sum: Decimal = Field(default=Decimal("0"))
    consol_adjustment: Decimal = Field(default=Decimal("0"))
    consol_elimination: Decimal = Field(default=Decimal("0"))
    consol_amount: Decimal = Field(default=Decimal("0"))


class ConsolTrialUpdate(BaseModel):
    """更新合并试算表行"""
    standard_account_code: str | None = None
    account_name: str | None = None
    account_category: AccountCategory | None = None
    individual_sum: Decimal | None = None
    consol_adjustment: Decimal | None = None
    consol_elimination: Decimal | None = None
    consol_amount: Decimal | None = None


class ConsolTrialResponse(ConsolTrialRow):
    """合并试算表响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    year: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class ConsistencyCheckResult(BaseModel):
    """合并试算表一致性校验结果"""
    is_balanced: bool = True
    total_debit: Decimal = Field(default=Decimal("0"))
    total_credit: Decimal = Field(default=Decimal("0"))
    difference: Decimal = Field(default=Decimal("0"))
    row_count: int = 0
    issues: list[str] = Field(default_factory=list)


# ===================================================================
# 4. EliminationEntry (抵消分录)
# ===================================================================


class EliminationEntryLine(BaseModel):
    """抵消分录行项"""
    account_code: str = Field(..., max_length=50)
    account_name: str | None = None
    debit_amount: Decimal = Field(default=Decimal("0"))
    credit_amount: Decimal = Field(default=Decimal("0"))

    @field_validator("debit_amount", "credit_amount", mode="before")
    @classmethod
    def coerce_decimal(cls, v):
        if v is None:
            return Decimal("0")
        return Decimal(str(v))


class EliminationEntryBase(BaseModel):
    """抵消分录基础字段"""
    year: int
    entry_type: EliminationEntryType
    description: str | None = None


class EliminationEntryCreate(EliminationEntryBase):
    """创建抵消分录"""
    project_id: UUID
    entry_no: str = Field(..., max_length=50)
    account_code: str = Field(..., max_length=50)
    account_name: str | None = None
    debit_amount: Decimal = Field(default=Decimal("0"))
    credit_amount: Decimal = Field(default=Decimal("0"))
    entry_group_id: UUID
    related_company_codes: list[str] | None = None
    is_continuous: bool = False


# 别名，保持向后兼容
EliminationCreate = EliminationEntryCreate


class EliminationEntryBatchCreate(BaseModel):
    """批量创建抵消分录（包含多个行项）"""
    project_id: UUID
    year: int
    entry_type: EliminationEntryType
    description: str | None = None
    entry_group_id: UUID
    related_company_codes: list[str] | None = None
    is_continuous: bool = False
    lines: list[EliminationEntryLine] = Field(..., min_length=1)


class EliminationEntryUpdate(BaseModel):
    """更新抵消分录"""
    entry_type: EliminationEntryType | None = None
    description: str | None = None
    account_code: str | None = None
    account_name: str | None = None
    debit_amount: Decimal | None = None
    credit_amount: Decimal | None = None
    related_company_codes: list[str] | None = None
    is_continuous: bool | None = None


class EliminationEntryResponse(EliminationEntryBase):
    """抵消分录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    entry_no: str
    account_code: str
    account_name: str | None = None
    debit_amount: Decimal
    credit_amount: Decimal
    entry_group_id: UUID
    related_company_codes: dict | None = None
    is_continuous: bool
    prior_year_entry_id: UUID | None = None
    review_status: ReviewStatusEnum
    reviewer_id: UUID | None = None
    reviewed_at: datetime | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None


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


# ===================================================================
# 5. InternalTrade (内部交易)
# ===================================================================


class InternalTradeCreate(BaseModel):
    """创建内部交易"""
    year: int
    seller_company_code: str = Field(..., max_length=50)
    buyer_company_code: str = Field(..., max_length=50)
    trade_type: TradeType | None = None
    trade_amount: Decimal | None = None
    cost_amount: Decimal | None = None
    unrealized_profit: Decimal | None = None
    inventory_remaining_ratio: Decimal | None = Field(
        None, decimal_places=4, max_digits=5
    )
    description: str | None = None


class InternalTradeUpdate(BaseModel):
    """更新内部交易"""
    trade_type: TradeType | None = None
    trade_amount: Decimal | None = None
    cost_amount: Decimal | None = None
    unrealized_profit: Decimal | None = None
    inventory_remaining_ratio: Decimal | None = None
    description: str | None = None


class InternalTradeResponse(BaseModel):
    """内部交易响应"""
    model_config = ConfigDict(from_attributes=True)

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


# ===================================================================
# 6. InternalArAp (内部往来)
# ===================================================================


class InternalArApCreate(BaseModel):
    """创建内部往来"""
    year: int
    debtor_company_code: str = Field(..., max_length=50)
    creditor_company_code: str = Field(..., max_length=50)
    debtor_amount: Decimal | None = None
    creditor_amount: Decimal | None = None
    difference_amount: Decimal | None = None
    difference_reason: str | None = None
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.unmatched


class InternalArApUpdate(BaseModel):
    """更新内部往来"""
    debtor_amount: Decimal | None = None
    creditor_amount: Decimal | None = None
    difference_amount: Decimal | None = None
    difference_reason: str | None = None
    reconciliation_status: ReconciliationStatus | None = None


class InternalArApResponse(BaseModel):
    """内部往来响应"""
    model_config = ConfigDict(from_attributes=True)

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


class TransactionMatrix(BaseModel):
    """交易矩阵"""
    company_codes: list[str] = Field(default_factory=list)
    matrix: dict[str, dict[str, Decimal]] = Field(default_factory=dict)


# ===================================================================
# 7. GoodwillCalc (商誉计算)
# ===================================================================


class GoodwillInput(BaseModel):
    """商誉计算输入"""
    year: int
    subsidiary_company_code: str = Field(..., max_length=50)
    acquisition_date: date | None = None
    acquisition_cost: Decimal | None = None
    identifiable_net_assets_fv: Decimal | None = None
    parent_share_ratio: Decimal | None = Field(None, decimal_places=4, max_digits=5)


class GoodwillCreate(GoodwillInput):
    """创建商誉计算"""
    project_id: UUID


class GoodwillUpdate(BaseModel):
    """更新商誉计算"""
    acquisition_date: date | None = None
    acquisition_cost: Decimal | None = None
    identifiable_net_assets_fv: Decimal | None = None
    parent_share_ratio: Decimal | None = None
    goodwill_amount: Decimal | None = None
    accumulated_impairment: Decimal | None = None
    current_year_impairment: Decimal | None = None
    carrying_amount: Decimal | None = None
    is_negative_goodwill: bool | None = None
    negative_goodwill_treatment: str | None = None


class GoodwillResult(BaseModel):
    """商誉计算结果"""
    subsidiary_company_code: str
    acquisition_cost: Decimal | None = None
    identifiable_net_assets_fv: Decimal | None = None
    goodwill_amount: Decimal | None = None
    carrying_amount: Decimal | None = None
    accumulated_impairment: Decimal = Decimal("0")
    current_year_impairment: Decimal = Decimal("0")
    is_negative_goodwill: bool = False


class GoodwillCalcResponse(BaseModel):
    """商誉计算响应"""
    model_config = ConfigDict(from_attributes=True)

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


# ===================================================================
# 7b. Equity Elimination & Carry Forward
# ===================================================================


class EquityEliminationInput(BaseModel):
    """权益抵消分录输入"""
    subsidiary_company_code: str
    parent_share_ratio: Decimal | None = None
    minority_share_ratio: Decimal | None = None
    # 以下字段用于从合并试算表取值，若为 None 则从 goodwill_calc / minority_interest 表读取
    share_capital: Decimal = Decimal("0")          # 实收资本（子公司个别报表）
    capital_reserve: Decimal = Decimal("0")         # 资本公积
    surplus_reserve: Decimal = Decimal("0")         # 盈余公积
    undistributed_profit: Decimal = Decimal("0")     # 未分配利润
    long_term_equity_investment: Decimal = Decimal("0")  # 长期股权投资（母公司个别报表账面值）
    minority_equity_amount: Decimal = Decimal("0")  # 少数股东权益（来自 minority_interest 表）


class EquityEliminationResult(BaseModel):
    """权益抵消分录生成结果"""
    entry_group_id: UUID
    entry_no: str
    description: str
    lines: list[EliminationEntryLine]
    goodwill_amount: Decimal
    minority_equity_amount: Decimal
    total_debit: Decimal
    total_credit: Decimal


class CarryForwardResult(BaseModel):
    """商誉结转结果"""
    carried_records: int = 0
    new_records: int = 0
    updated_records: int = 0
    details: list[dict] = Field(default_factory=list)


# ===================================================================
# 8. MinorityInterest (少数股东权益)
# ===================================================================


class ImpairmentRecord(BaseModel):
    """减值记录"""
    year: int
    impairment_amount: Decimal


class MinorityInterestInput(BaseModel):
    """少数股东权益输入（用于创建/更新）"""
    company_code: str
    company_name: str | None = None
    opening_equity: Decimal | None = None
    current_net_profit: Decimal | None = None
    net_assets: Decimal | None = None
    minority_share_ratio: Decimal | None = None
    equity_movement: dict | None = None


class MinorityInterestResult(BaseModel):
    """少数股东权益计算结果"""
    year: int
    subsidiary_company_code: str
    subsidiary_net_assets: Decimal | None = None
    minority_share_ratio: Decimal | None = None
    minority_equity: Decimal | None = None
    subsidiary_net_profit: Decimal | None = None
    minority_profit: Decimal | None = None
    minority_equity_opening: Decimal | None = None
    minority_equity_movement: dict | None = None
    is_excess_loss: bool = False
    excess_loss_amount: Decimal = Decimal("0")


class MinorityInterestBatchResult(BaseModel):
    """批量少数股东权益结果"""
    results: list[MinorityInterestResult]
    total_minority_equity: Decimal = Decimal("0")
    total_minority_profit: Decimal = Decimal("0")


class MinorityInterestCreate(BaseModel):
    """创建少数股东权益"""
    project_id: UUID
    year: int
    subsidiary_company_code: str = Field(..., max_length=50)
    subsidiary_net_assets: Decimal | None = None
    minority_share_ratio: Decimal | None = Field(None, decimal_places=4, max_digits=5)
    minority_equity: Decimal | None = None
    subsidiary_net_profit: Decimal | None = None
    minority_profit: Decimal | None = None
    minority_equity_opening: Decimal | None = None
    minority_equity_movement: dict | None = None
    is_excess_loss: bool = False
    excess_loss_amount: Decimal = Decimal("0")


class MinorityInterestUpdate(BaseModel):
    """更新少数股东权益"""
    subsidiary_net_assets: Decimal | None = None
    minority_share_ratio: Decimal | None = None
    minority_equity: Decimal | None = None
    subsidiary_net_profit: Decimal | None = None
    minority_profit: Decimal | None = None
    minority_equity_opening: Decimal | None = None
    minority_equity_movement: dict | None = None
    is_excess_loss: bool | None = None
    excess_loss_amount: Decimal | None = None


class MinorityInterestResponse(MinorityInterestResult):
    """少数股东权益响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class MinorityInterestEliminationResponse(BaseModel):
    """少数股东权益/损益抵消分录生成结果"""
    entry_group_id: str
    entry_no: str
    description: str
    lines: list["EliminationEntryLine"]
    minority_profit: str
    minority_equity: str
    minority_equity_opening: str
    total_debit: str
    total_credit: str
    skipped: bool | None = None
    reason: str | None = None


# ===================================================================
# 9. ForexTranslation (外币折算)
# ===================================================================


class ForexRates(BaseModel):
    """汇率输入"""
    bs_closing_rate: Decimal | None = Field(None, decimal_places=6)
    pl_average_rate: Decimal | None = Field(None, decimal_places=6)
    equity_historical_rate: Decimal | None = Field(None, decimal_places=6)


class ForexTranslationResult(BaseModel):
    """外币折算结果"""
    company_code: str
    functional_currency: str
    bs_closing_rate: Decimal | None = None
    pl_average_rate: Decimal | None = None
    equity_historical_rate: Decimal | None = None
    translation_difference: Decimal | None = None


class TranslationWorksheetRow(BaseModel):
    """折算工作表行（单个科目）"""
    standard_account_code: str
    account_name: str
    account_category: str | None = None
    original_amount: Decimal = Decimal("0")
    functional_currency: str
    rate: Decimal | None = None
    translated_amount: Decimal = Decimal("0")
    reporting_currency: str = "CNY"
    translation_difference: Decimal | None = None
    rate_type: str | None = None  # bs/pl/equity/retained/oci


class TranslationWorksheetSummary(BaseModel):
    """折算工作表汇总"""
    total_original_assets: Decimal = Decimal("0")
    total_original_liabilities: Decimal = Decimal("0")
    total_original_equity: Decimal = Decimal("0")
    total_translated_assets: Decimal = Decimal("0")
    total_translated_liabilities: Decimal = Decimal("0")
    total_translated_equity: Decimal = Decimal("0")


class TranslationWorksheet(BaseModel):
    """折算工作表"""
    company_code: str
    functional_currency: str
    reporting_currency: str = "CNY"
    rates: ForexRates
    opening_retained_earnings_translated: Decimal | None = None
    translation_difference: Decimal | None = None
    translation_difference_oci: Decimal | None = None
    rows: list[TranslationWorksheetRow] = []
    summary: TranslationWorksheetSummary | None = None


class ForexTranslationCreate(BaseModel):
    """创建外币折算"""
    project_id: UUID
    year: int
    company_code: str = Field(..., max_length=50)
    functional_currency: str = Field(..., max_length=3)
    reporting_currency: str = Field(default="CNY", max_length=3)
    bs_closing_rate: Decimal | None = Field(None, decimal_places=6)
    pl_average_rate: Decimal | None = Field(None, decimal_places=6)
    equity_historical_rate: Decimal | None = Field(None, decimal_places=6)
    opening_retained_earnings_translated: Decimal | None = None
    translation_difference: Decimal | None = None
    translation_difference_oci: Decimal | None = None


class ForexTranslationUpdate(BaseModel):
    """更新外币折算"""
    functional_currency: str | None = None
    reporting_currency: str | None = None
    bs_closing_rate: Decimal | None = None
    pl_average_rate: Decimal | None = None
    equity_historical_rate: Decimal | None = None
    opening_retained_earnings_translated: Decimal | None = None
    translation_difference: Decimal | None = None
    translation_difference_oci: Decimal | None = None


class ForexTranslationResponse(BaseModel):
    """外币折算响应"""
    model_config = ConfigDict(from_attributes=True)

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


# ===================================================================
# 10. ComponentAuditor (组成部分审计师)
# ===================================================================


class ComponentAuditorCreate(BaseModel):
    """创建组成部分审计师"""
    project_id: UUID
    company_code: str = Field(..., max_length=50)
    firm_name: str = Field(..., max_length=255)
    contact_person: str | None = None
    contact_info: str | None = None
    competence_rating: CompetenceRating | None = None
    rating_basis: str | None = None
    independence_confirmed: bool = False
    independence_date: date | None = None


class ComponentAuditorUpdate(BaseModel):
    """更新组成部分审计师"""
    firm_name: str | None = None
    contact_person: str | None = None
    contact_info: str | None = None
    competence_rating: CompetenceRating | None = None
    rating_basis: str | None = None
    independence_confirmed: bool | None = None
    independence_date: date | None = None


class ComponentAuditorResponse(BaseModel):
    """组成部分审计师响应"""
    model_config = ConfigDict(from_attributes=True)

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


# ===================================================================
# 11. ComponentInstruction (审计指令)
# ===================================================================


class InstructionCreate(BaseModel):
    """创建审计指令"""
    project_id: UUID
    component_auditor_id: UUID
    instruction_date: date | None = None
    due_date: date | None = None
    materiality_level: Decimal | None = None
    audit_scope_description: str | None = None
    reporting_format: str | None = None
    special_attention_items: str | None = None
    instruction_file_path: str | None = None


class InstructionUpdate(BaseModel):
    """更新审计指令"""
    instruction_date: date | None = None
    due_date: date | None = None
    materiality_level: Decimal | None = None
    audit_scope_description: str | None = None
    reporting_format: str | None = None
    special_attention_items: str | None = None
    instruction_file_path: str | None = None
    status: InstructionStatus | None = None


class InstructionSend(BaseModel):
    """发送审计指令"""
    instruction_date: date
    instruction_file_path: str | None = None


class ComponentInstructionResponse(BaseModel):
    """审计指令响应"""
    model_config = ConfigDict(from_attributes=True)

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
    created_by: UUID | None = None


# ===================================================================
# 12. ComponentResult (组成部分审计结果)
# ===================================================================


class ComponentResultCreate(BaseModel):
    """创建组成部分审计结果"""
    project_id: UUID
    component_auditor_id: UUID
    instruction_id: UUID | None = None
    received_date: date | None = None
    opinion_type: OpinionTypeEnum | None = None
    identified_misstatements: dict | None = None
    significant_findings: str | None = None
    result_file_path: str | None = None
    group_team_evaluation: str | None = None
    needs_additional_procedures: bool = False
    evaluation_status: EvaluationStatus = EvaluationStatus.pending
    is_non_standard_opinion: bool = False
    opinion_explanation: str | None = None


class ComponentResultUpdate(BaseModel):
    """更新组成部分审计结果"""
    received_date: date | None = None
    opinion_type: OpinionTypeEnum | None = None
    identified_misstatements: dict | None = None
    significant_findings: str | None = None
    result_file_path: str | None = None
    group_team_evaluation: str | None = None
    needs_additional_procedures: bool | None = None
    evaluation_status: EvaluationStatus | None = None


class ComponentResultResponse(BaseModel):
    """组成部分审计结果响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    component_auditor_id: UUID
    instruction_id: UUID | None = None
    received_date: date | None = None
    opinion_type: OpinionTypeEnum | None = None
    identified_misstatements: dict | None = None
    significant_findings: str | None = None
    result_file_path: str | None = None
    group_team_evaluation: str | None = None
    needs_additional_procedures: bool
    evaluation_status: EvaluationStatus
    is_non_standard_opinion: bool
    opinion_explanation: str | None = None
    status: ResultStatus
    accepted_by: UUID | None = None
    accepted_at: datetime | None = None
    rejection_reason: str | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class ComponentDashboard(BaseModel):
    """组成部分仪表盘"""
    total_components: int
    pending_results: int
    accepted_results: int
    requires_followup: int
    results_by_opinion: dict[str, int] = Field(default_factory=dict)



# ===================================================================
# 合并报表服务 schemas (Task 14)
# ===================================================================


class BalanceCheckResult(BaseModel):
    """资产负债表平衡校验结果"""
    is_balanced: bool = True
    total_assets: Decimal = Field(default=Decimal("0"))
    total_liabilities: Decimal = Field(default=Decimal("0"))
    total_equity: Decimal = Field(default=Decimal("0"))
    minority_interest: Decimal = Field(default=Decimal("0"))
    goodwill: Decimal = Field(default=Decimal("0"))
    difference: Decimal = Field(default=Decimal("0"))
    issues: list[str] = Field(default_factory=list)


class ConsolReportRow(BaseModel):
    """合并报表行"""
    row_code: str
    row_name: str | None = None
    current_period_amount: Decimal = Field(default=Decimal("0"))
    prior_period_amount: Decimal = Field(default=Decimal("0"))
    formula_used: str | None = None
    source_accounts: list[str] = Field(default_factory=list)


class ConsolWorkpaperResult(BaseModel):
    """合并底稿生成结果"""
    file_data: bytes | None = None
    file_name: str = "合并底稿.xlsx"
    sheet_count: int = 0
    message: str = ""


class ConsolDisclosureSection(BaseModel):
    """合并附注章节"""
    section_code: str
    section_title: str
    content_type: str = "table"  # table, text, mixed
    rows: list[dict] = Field(default_factory=list)
    summary: str = ""


class ConsolNotesGenerateRequest(BaseModel):
    """生成合并附注请求"""
    project_id: UUID
    year: int


class ConsolReportGenerateRequest(BaseModel):
    """生成合并报表请求"""
    project_id: UUID
    year: int
    applicable_standard: str = "enterprise"
