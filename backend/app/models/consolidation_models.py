"""集团合并相关表 ORM 模型"""

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base, SoftDeleteMixin, TimestampMixin


# ---------------------------------------------------------------------------
# 枚举类型
# ---------------------------------------------------------------------------


class ConsolMethod(str, enum.Enum):
    """合并方法"""
    full = "full"
    equity = "equity"
    proportional = "proportional"


class ScopeCompanyType(str, enum.Enum):
    """公司类型"""
    parent = "parent"
    subsidiary = "subsidiary"
    associate = "associate"
    joint_venture = "joint_venture"


class InclusionReason(str, enum.Enum):
    """纳入合并范围原因"""
    subsidiary = "subsidiary"
    associate = "associate"
    joint_venture = "joint_venture"
    special_purpose = "special_purpose"


class ScopeChangeType(str, enum.Enum):
    """合并范围变更类型"""
    none = "none"
    new_inclusion = "new_inclusion"
    exclusion = "exclusion"
    method_change = "method_change"


class EliminationEntryType(str, enum.Enum):
    """抵消分录类型"""
    equity = "equity"
    internal_trade = "internal_trade"
    internal_ar_ap = "internal_ar_ap"
    unrealized_profit = "unrealized_profit"
    other = "other"


class TradeType(str, enum.Enum):
    """内部交易类型"""
    goods = "goods"
    services = "services"
    assets = "assets"
    other = "other"


class ReconciliationStatus(str, enum.Enum):
    """往来对账状态"""
    matched = "matched"
    unmatched = "unmatched"
    adjusted = "adjusted"


class CompetenceRating(str, enum.Enum):
    """组成部分审计师胜任能力评价"""
    reliable = "reliable"
    additional_procedures_needed = "additional_procedures_needed"
    unreliable = "unreliable"


class InstructionStatus(str, enum.Enum):
    """审计指令状态"""
    draft = "draft"
    sent = "sent"
    acknowledged = "acknowledged"


class OpinionTypeEnum(str, enum.Enum):
    """审计意见类型"""
    unqualified = "unqualified"
    qualified = "qualified"
    adverse = "adverse"
    disclaimer = "disclaimer"


class EvaluationStatusEnum(str, enum.Enum):
    """评价状态"""
    pending = "pending"
    accepted = "accepted"
    requires_followup = "requires_followup"


class ReviewStatusEnum(str, enum.Enum):
    """复核状态"""
    draft = "draft"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"


class AccountCategory(str, enum.Enum):
    """科目类别"""
    asset = "asset"
    liability = "liability"
    equity = "equity"
    revenue = "revenue"
    expense = "expense"


# ---------------------------------------------------------------------------
# ORM 模型
# ---------------------------------------------------------------------------


class Company(Base, SoftDeleteMixin, TimestampMixin):
    """公司信息表"""
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String, nullable=True)
    ultimate_code: Mapped[str] = mapped_column(String, nullable=False)
    consol_level: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    shareholding: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    consol_method: Mapped[ConsolMethod | None] = mapped_column(Enum(ConsolMethod), nullable=True)
    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    disposal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    functional_currency: Mapped[str] = mapped_column(String(3), server_default="CNY", nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)


class ConsolScope(Base, SoftDeleteMixin, TimestampMixin):
    """合并范围表"""
    __tablename__ = "consol_scope"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    company_type: Mapped[ScopeCompanyType | None] = mapped_column(Enum(ScopeCompanyType), nullable=True)
    ownership_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_included: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    inclusion_reason: Mapped[InclusionReason | None] = mapped_column(Enum(InclusionReason), nullable=True)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_change_type: Mapped[ScopeChangeType] = mapped_column(
        Enum(ScopeChangeType), server_default="none", nullable=False
    )
    scope_change_description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConsolTrial(Base, SoftDeleteMixin, TimestampMixin):
    """合并试算表"""
    __tablename__ = "consol_trial"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    standard_account_code: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    account_category: Mapped[AccountCategory | None] = mapped_column(Enum(AccountCategory), nullable=True)
    individual_sum: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0", nullable=False)
    consol_adjustment: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0", nullable=False)
    consol_elimination: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0", nullable=False)
    consol_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0", nullable=False)


class EliminationEntry(Base, SoftDeleteMixin, TimestampMixin, AuditMixin):
    """抵消分录表"""
    __tablename__ = "elimination_entries"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_no: Mapped[str] = mapped_column(String, nullable=False)
    entry_type: Mapped[EliminationEntryType] = mapped_column(Enum(EliminationEntryType), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_code: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0", nullable=False)
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0", nullable=False)
    lines: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    entry_group_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    related_company_codes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_continuous: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    prior_year_entry_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    review_status: Mapped[ReviewStatusEnum] = mapped_column(
        Enum(ReviewStatusEnum), server_default="draft", nullable=False
    )
    reviewer_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class InternalTrade(Base, SoftDeleteMixin, TimestampMixin):
    """内部交易表"""
    __tablename__ = "internal_trade"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    seller_company_code: Mapped[str] = mapped_column(String, nullable=False)
    buyer_company_code: Mapped[str] = mapped_column(String, nullable=False)
    trade_type: Mapped[TradeType | None] = mapped_column(Enum(TradeType), nullable=True)
    trade_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    unrealized_profit: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    inventory_remaining_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class InternalArAp(Base, SoftDeleteMixin, TimestampMixin):
    """内部往来表"""
    __tablename__ = "internal_ar_ap"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    debtor_company_code: Mapped[str] = mapped_column(String, nullable=False)
    creditor_company_code: Mapped[str] = mapped_column(String, nullable=False)
    debtor_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    creditor_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    difference_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    difference_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconciliation_status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus), server_default="unmatched", nullable=False
    )


class GoodwillCalc(Base, SoftDeleteMixin, TimestampMixin):
    """商誉计算表"""
    __tablename__ = "goodwill_calc"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    subsidiary_company_code: Mapped[str] = mapped_column(String, nullable=False)
    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    acquisition_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    identifiable_net_assets_fv: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    parent_share_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    goodwill_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    accumulated_impairment: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0", nullable=False)
    current_year_impairment: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0", nullable=False)
    carrying_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    is_negative_goodwill: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    negative_goodwill_treatment: Mapped[str | None] = mapped_column(Text, nullable=True)


class MinorityInterest(Base, SoftDeleteMixin, TimestampMixin):
    """少数股东权益表"""
    __tablename__ = "minority_interest"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    subsidiary_company_code: Mapped[str] = mapped_column(String, nullable=False)
    subsidiary_net_assets: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    minority_share_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    minority_equity: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    subsidiary_net_profit: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    minority_profit: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    minority_equity_opening: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    minority_equity_movement: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_excess_loss: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    excess_loss_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default="0", nullable=False)


class ForexTranslation(Base, SoftDeleteMixin, TimestampMixin):
    """外币折算表"""
    __tablename__ = "forex_translation"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    functional_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reporting_currency: Mapped[str] = mapped_column(String(3), server_default="CNY", nullable=True)
    bs_closing_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    pl_average_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    equity_historical_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    opening_retained_earnings_translated: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    translation_difference: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    translation_difference_oci: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)


class ComponentAuditor(Base, SoftDeleteMixin, TimestampMixin):
    """组成部分审计师表"""
    __tablename__ = "component_auditors"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    firm_name: Mapped[str] = mapped_column(String, nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_info: Mapped[str | None] = mapped_column(String, nullable=True)
    competence_rating: Mapped[CompetenceRating | None] = mapped_column(Enum(CompetenceRating), nullable=True)
    rating_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    independence_confirmed: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    independence_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class ComponentInstruction(Base, SoftDeleteMixin, TimestampMixin, AuditMixin):
    """组成部分审计指令表"""
    __tablename__ = "component_instructions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    component_auditor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("component_auditors.id"), nullable=False
    )
    instruction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    materiality_level: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    audit_scope_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporting_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_attention_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction_file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[InstructionStatus] = mapped_column(
        Enum(InstructionStatus), server_default="draft", nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ComponentResult(Base, SoftDeleteMixin, TimestampMixin):
    """组成部分审计结果表"""
    __tablename__ = "component_results"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    component_auditor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("component_auditors.id"), nullable=False
    )
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    opinion_type: Mapped[OpinionTypeEnum | None] = mapped_column(Enum(OpinionTypeEnum), nullable=True)
    identified_misstatements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    significant_findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    group_team_evaluation: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_additional_procedures: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    evaluation_status: Mapped[EvaluationStatusEnum] = mapped_column(
        Enum(EvaluationStatusEnum), server_default="pending", nullable=False
    )
