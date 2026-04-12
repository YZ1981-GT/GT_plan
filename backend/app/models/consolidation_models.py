"""集团合并相关表 ORM 模型（对应 Migration 009）

12 张表：
1. companies           - 公司信息
2. consol_scope       - 合并范围
3. consol_trial       - 合并试算表
4. elimination_entries - 抵消分录
5. internal_trade     - 内部交易
6. internal_ar_ap     - 内部往来
7. goodwill_calc      - 商誉计算
8. minority_interest  - 少数股东权益
9. forex_translation  - 外币折算
10. component_auditors - 组成部分审计师
11. component_instructions - 审计指令
12. component_results  - 组成部分审计结果
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ---------------------------------------------------------------------------
# PostgreSQL 枚举类型（与 Migration 009 一致）
# ---------------------------------------------------------------------------


class ConsolMethod(str, enum.Enum):
    """合并方法"""
    full = "full"
    equity = "equity"
    proportional = "proportional"


class OwnershipType(str, enum.Enum):
    """股权性质"""
    direct = "direct"
    indirect = "indirect"
    joint = "joint"


class InclusionReason(str, enum.Enum):
    """纳入合并范围原因"""
    direct_control = "direct_control"
    indirect_control = "indirect_control"
    joint_control = "joint_control"
    significant_influence = "significant_influence"
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


class ReviewStatusEnum(str, enum.Enum):
    """复核状态"""
    draft = "draft"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"


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


class EvaluationStatus(str, enum.Enum):
    """评价状态"""
    pending = "pending"
    accepted = "accepted"
    requires_followup = "requires_followup"


class ResultStatus(str, enum.Enum):
    """审计结果状态"""
    received = "received"
    accepted = "accepted"
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


# ---------------------------------------------------------------------------
# 1. Company
# ---------------------------------------------------------------------------

class Company(Base):
    """公司信息表"""
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String, nullable=True)
    ultimate_code: Mapped[str] = mapped_column(String, nullable=False)
    consol_level: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    shareholding: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    consol_method: Mapped[ConsolMethod | None] = mapped_column(
        Enum(ConsolMethod, name="consol_method", create_type=False), nullable=True
    )
    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    disposal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    functional_currency: Mapped[str] = mapped_column(
        String(3), server_default=text("'CNY'"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_companies_project_code", "project_id", "company_code", unique=True),
        Index("idx_companies_parent", "parent_code"),
    )


# ---------------------------------------------------------------------------
# 2. ConsolScope
# ---------------------------------------------------------------------------

class ConsolScope(Base):
    """合并范围表"""
    __tablename__ = "consol_scope"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    is_included: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), nullable=False
    )
    inclusion_reason: Mapped[InclusionReason | None] = mapped_column(
        Enum(InclusionReason, name="inclusion_reason", create_type=False), nullable=True
    )
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_change_type: Mapped[ScopeChangeType] = mapped_column(
        Enum(ScopeChangeType, name="scope_change_type", create_type=False),
        server_default=text("'none'"),
        nullable=False,
    )
    scope_change_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "idx_consol_scope_unique",
            "project_id", "year", "company_code",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# 3. ConsolTrial
# ---------------------------------------------------------------------------

class ConsolTrial(Base):
    """合并试算表"""
    __tablename__ = "consol_trial"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    standard_account_code: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    account_category: Mapped[AccountCategory | None] = mapped_column(
        Enum(AccountCategory, name="account_category", create_type=False),
        nullable=True,
    )
    individual_sum: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), server_default=text("0"), nullable=False
    )
    consol_adjustment: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), server_default=text("0"), nullable=False
    )
    consol_elimination: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), server_default=text("0"), nullable=False
    )
    consol_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), server_default=text("0"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "idx_consol_trial_unique",
            "project_id", "year", "standard_account_code",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# 4. EliminationEntry
# ---------------------------------------------------------------------------

class EliminationEntry(Base):
    """抵消分录表"""
    __tablename__ = "elimination_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_no: Mapped[str] = mapped_column(String, nullable=False)
    entry_type: Mapped[EliminationEntryType] = mapped_column(
        Enum(EliminationEntryType, name="elimination_entry_type", create_type=False),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_code: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    debit_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), server_default=text("0"), nullable=False
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), server_default=text("0"), nullable=False
    )
    entry_group_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    related_company_codes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_continuous: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    prior_year_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    review_status: Mapped[ReviewStatusEnum] = mapped_column(
        Enum(ReviewStatusEnum, name="review_status_enum", create_type=False),
        server_default=text("'draft'"),
        nullable=False,
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index("idx_elimination_project_year_type", "project_id", "year", "entry_type"),
        Index("idx_elimination_entry_group", "entry_group_id"),
        Index("idx_elimination_entry_no", "entry_no"),
    )


# ---------------------------------------------------------------------------
# 5. InternalTrade
# ---------------------------------------------------------------------------

class InternalTrade(Base):
    """内部交易表"""
    __tablename__ = "internal_trade"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    seller_company_code: Mapped[str] = mapped_column(String, nullable=False)
    buyer_company_code: Mapped[str] = mapped_column(String, nullable=False)
    trade_type: Mapped[TradeType | None] = mapped_column(
        Enum(TradeType, name="trade_type", create_type=False), nullable=True
    )
    trade_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    unrealized_profit: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    inventory_remaining_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_internal_trade_project_year", "project_id", "year"),
    )


# ---------------------------------------------------------------------------
# 6. InternalArAp
# ---------------------------------------------------------------------------

class InternalArAp(Base):
    """内部往来表"""
    __tablename__ = "internal_ar_ap"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    debtor_company_code: Mapped[str] = mapped_column(String, nullable=False)
    creditor_company_code: Mapped[str] = mapped_column(String, nullable=False)
    debtor_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    creditor_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    difference_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    difference_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconciliation_status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, name="reconciliation_status", create_type=False),
        server_default=text("'unmatched'"),
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_internal_ar_ap_project_year", "project_id", "year"),
    )


# ---------------------------------------------------------------------------
# 7. GoodwillCalc
# ---------------------------------------------------------------------------

class GoodwillCalc(Base):
    """商誉计算表"""
    __tablename__ = "goodwill_calc"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    subsidiary_company_code: Mapped[str] = mapped_column(String, nullable=False)
    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    acquisition_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    identifiable_net_assets_fv: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    parent_share_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    goodwill_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    accumulated_impairment: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), server_default=text("0"), nullable=False
    )
    current_year_impairment: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), server_default=text("0"), nullable=False
    )
    carrying_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    is_negative_goodwill: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    negative_goodwill_treatment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "idx_goodwill_unique",
            "project_id", "year", "subsidiary_company_code",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# 8. MinorityInterest
# ---------------------------------------------------------------------------

class MinorityInterest(Base):
    """少数股东权益表"""
    __tablename__ = "minority_interest"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    subsidiary_company_code: Mapped[str] = mapped_column(String, nullable=False)
    subsidiary_net_assets: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    minority_share_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    minority_equity: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    subsidiary_net_profit: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    minority_profit: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    minority_equity_opening: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    minority_equity_movement: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_excess_loss: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    excess_loss_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), server_default=text("0"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "idx_minority_interest_unique",
            "project_id", "year", "subsidiary_company_code",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# 9. ForexTranslation
# ---------------------------------------------------------------------------

class ForexTranslation(Base):
    """外币折算表"""
    __tablename__ = "forex_translation"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    functional_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reporting_currency: Mapped[str] = mapped_column(
        String(3), server_default=text("'CNY'"), nullable=True
    )
    bs_closing_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    pl_average_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    equity_historical_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    opening_retained_earnings_translated: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    translation_difference: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    translation_difference_oci: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "idx_forex_translation_unique",
            "project_id", "year", "company_code",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# 10. ComponentAuditor
# ---------------------------------------------------------------------------

class ComponentAuditor(Base):
    """组成部分审计师表"""
    __tablename__ = "component_auditors"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    company_code: Mapped[str] = mapped_column(String, nullable=False)
    firm_name: Mapped[str] = mapped_column(String, nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_info: Mapped[str | None] = mapped_column(String, nullable=True)
    competence_rating: Mapped[CompetenceRating | None] = mapped_column(
        Enum(CompetenceRating, name="competence_rating", create_type=False),
        nullable=True,
    )
    rating_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    independence_confirmed: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    independence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "idx_component_auditors_unique",
            "project_id", "company_code",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# 11. ComponentInstruction
# ---------------------------------------------------------------------------

class ComponentInstruction(Base):
    """审计指令表"""
    __tablename__ = "component_instructions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    component_auditor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("component_auditors.id"), nullable=False
    )
    instruction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    materiality_level: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    audit_scope_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporting_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_attention_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction_file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[InstructionStatus] = mapped_column(
        Enum(InstructionStatus, name="instruction_status", create_type=False),
        server_default=text("'draft'"),
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "idx_component_instructions_project_auditor",
            "project_id", "component_auditor_id",
        ),
    )


# ---------------------------------------------------------------------------
# 12. ComponentResult
# ---------------------------------------------------------------------------

class ComponentResult(Base):
    """组成部分审计结果表"""
    __tablename__ = "component_results"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    component_auditor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("component_auditors.id"), nullable=False
    )
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    opinion_type: Mapped[OpinionTypeEnum | None] = mapped_column(
        Enum(OpinionTypeEnum, name="opinion_type_enum", create_type=False),
        nullable=True,
    )
    identified_misstatements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    significant_findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    group_team_evaluation: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_additional_procedures: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    evaluation_status: Mapped[EvaluationStatus] = mapped_column(
        Enum(EvaluationStatus, name="evaluation_status", create_type=False),
        server_default=text("'pending'"),
        nullable=False,
    )
    is_non_standard_opinion: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    opinion_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ResultStatus] = mapped_column(
        Enum(ResultStatus, name="result_status", create_type=False),
        server_default=text("'received'"),
        nullable=False,
    )
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "idx_component_results_project_auditor",
            "project_id", "component_auditor_id",
        ),
    )
