"""协作与质控相关表 ORM 模型（对应 Migration 010-015）

Tables:
  010: risk_assessments, risk_matrix_records
  011: audit_plans
  012: audit_procedures
  013: audit_findings
  014: management_letters
  015: notifications, confirmation_lists, confirmation_results,
        confirmation_attachments, going_concern_evaluations,
        going_concern_indicators, archive_checklists, archive_modifications
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Index,
    Integer, JSON, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AssertionLevel(str, enum.Enum):
    existence = "existence"
    completeness = "completeness"
    accuracy = "accuracy"
    cutoff = "cutoff"
    classification = "classification"
    occurrence = "occurrence"
    rights_obligations = "rights_obligations"
    valuation = "valuation"


class RiskLevel(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ReviewStatus(str, enum.Enum):
    draft = "draft"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        Index("ix_risk_assessments_project_account", "project_id", "account_or_cycle"),
        Index("ix_risk_assessments_significant", "project_id", "is_significant_risk"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    assertion_level: Mapped[AssertionLevel] = mapped_column(Enum(AssertionLevel, name="assertion_level"), nullable=False)
    account_or_cycle: Mapped[str] = mapped_column(String(100), nullable=False)
    inherent_risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="risk_level"), nullable=False)
    control_risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="risk_level"), nullable=False)
    combined_risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="risk_level"), nullable=False)
    is_significant_risk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_audit_procedures: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus, name="review_status_enum"), default=ReviewStatus.draft, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ConfirmationLetter(Base):
    """询证函模板/内容"""
    __tablename__ = "confirmation_letters"
    __table_args__ = (Index("ix_confirmation_letters_list", "confirmation_list_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    confirmation_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("confirmation_lists.id"), nullable=False
    )
    letter_format: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

class RiskMatrixRecord(Base):
    __tablename__ = "risk_matrix_records"
    __table_args__ = (Index("ix_risk_matrix_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    inherent_risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="risk_level"), nullable=False)
    control_risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="risk_level"), nullable=False)
    combined_risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="risk_level"), nullable=False)
    inherent_risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    control_risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    combined_risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    mitigation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


class AuditPlanStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    revised = "revised"


class AuditPlan(Base):
    __tablename__ = "audit_plans"
    __table_args__ = (Index("ix_audit_plans_project", "project_id"), Index("ix_audit_plans_status", "status"))

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, unique=True)
    plan_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    audit_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    key_focus_areas: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    team_assignment_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    materiality_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AuditPlanStatus] = mapped_column(Enum(AuditPlanStatus, name="audit_plan_status"), default=AuditPlanStatus.draft, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ProcedureType(str, enum.Enum):
    risk_assessment = "risk_assessment"
    control_test = "control_test"
    substantive = "substantive"


class ExecutionStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"
    not_applicable = "not_applicable"


class AuditProcedure(Base):
    __tablename__ = "audit_procedures"
    __table_args__ = (
        Index("ix_audit_procedures_project_type", "project_id", "procedure_type"),
        Index("ix_audit_procedures_project_cycle", "project_id", "audit_cycle"),
        Index("ix_audit_procedures_project_status", "project_id", "execution_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    procedure_code: Mapped[str] = mapped_column(String(50), nullable=False)
    procedure_name: Mapped[str] = mapped_column(String(200), nullable=False)
    procedure_type: Mapped[ProcedureType] = mapped_column(Enum(ProcedureType, name="procedure_type_enum"), nullable=False)
    audit_cycle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_status: Mapped[ExecutionStatus] = mapped_column(Enum(ExecutionStatus, name="execution_status_enum"), default=ExecutionStatus.not_started, nullable=False)
    executed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    executed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_wp_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_risk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


class SeverityLevel(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class FinalTreatment(str, enum.Enum):
    adjusted = "adjusted"
    unadjusted = "unadjusted"
    disclosed = "disclosed"
    no_action = "no_action"


class AuditFinding(Base):
    __tablename__ = "audit_findings"
    __table_args__ = (Index("ix_audit_findings_project", "project_id"), Index("ix_audit_findings_severity", "severity"))

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    finding_code: Mapped[str] = mapped_column(String(50), nullable=False)
    finding_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[SeverityLevel] = mapped_column(Enum(SeverityLevel, name="severity_level"), nullable=False)
    affected_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    finding_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    management_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_treatment: Mapped[FinalTreatment | None] = mapped_column(Enum(FinalTreatment, name="final_treatment_enum"), nullable=True)
    related_adjustment_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    related_wp_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class IssueType(str, enum.Enum):
    control_deficiency = "control_deficiency"
    process_improvement = "process_improvement"
    compliance = "compliance"
    other = "other"


class FollowUpStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    accepted_risk = "accepted_risk"


class ManagementLetter(Base):
    __tablename__ = "management_letters"
    __table_args__ = (
        Index("ix_management_letters_project", "project_id"),
        Index("ix_management_letters_status", "follow_up_status"),
        Index("ix_management_letters_prior", "prior_year_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    letter_code: Mapped[str] = mapped_column(String(50), nullable=False)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_type: Mapped[IssueType] = mapped_column(Enum(IssueType, name="issue_type_enum"), nullable=False)
    issue_title: Mapped[str] = mapped_column(String(200), nullable=False)
    issue_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    management_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    response_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    follow_up_status: Mapped[FollowUpStatus] = mapped_column(Enum(FollowUpStatus, name="follow_up_status_enum"), default=FollowUpStatus.open, nullable=False)
    prior_year_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_prior_year_carryforward: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


# ── Phase 015 ──
class ConfirmationType(str, enum.Enum):
    bank = "bank"
    customer = "customer"
    vendor = "vendor"
    lawyer = "lawyer"
    other = "other"


class ConfirmationListStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    sent = "sent"
    received = "received"
    reconciled = "reconciled"


class ConfirmationList(Base):
    __tablename__ = "confirmation_lists"
    __table_args__ = (
        Index("ix_confirmation_lists_project_type", "project_id", "confirmation_type"),
        Index("ix_confirmation_lists_project_status", "project_id", "list_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    confirmation_type: Mapped[ConfirmationType] = mapped_column(Enum(ConfirmationType, name="confirmation_type_enum"), nullable=False)
    confirmation_code: Mapped[str] = mapped_column(String(50), nullable=False)
    counterparty_name: Mapped[str] = mapped_column(String(200), nullable=False)
    counterparty_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    balance_or_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    list_status: Mapped[ConfirmationListStatus] = mapped_column(Enum(ConfirmationListStatus, name="confirmation_list_status"), default=ConfirmationListStatus.draft, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ConfirmationResultStatus(str, enum.Enum):
    confirmed = "confirmed"
    discrepancy = "discrepancy"
    no_response = "no_response"
    alternative_procedures = "alternative_procedures"


class ConfirmationResult(Base):
    __tablename__ = "confirmation_results"
    __table_args__ = (Index("ix_confirmation_results_list", "confirmation_list_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    confirmation_list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("confirmation_lists.id"), nullable=False)
    result_status: Mapped[ConfirmationResultStatus] = mapped_column(Enum(ConfirmationResultStatus, name="confirmation_result_status"), nullable=False)
    confirmed_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    discrepancy_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    discrepancy_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternative_procedures_performed: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


class ConfirmationAttachment(Base):
    __tablename__ = "confirmation_attachments"
    __table_args__ = (Index("ix_confirmation_attachments_list", "confirmation_list_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    confirmation_list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("confirmation_lists.id"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


class GoingConcernConclusion(str, enum.Enum):
    no_material_uncertainty = "no_material_uncertainty"
    material_uncertainty_disclosed = "material_uncertainty_disclosed"
    qualified = "qualified"
    adverse = "adverse"


class ConfirmationSummary(Base):
    """询证函汇总"""
    __tablename__ = "confirmation_summaries"
    __table_args__ = (Index("ix_confirmation_summaries_list", "confirmation_list_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    confirmation_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("confirmation_lists.id"), nullable=False
    )
    total_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_agreed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_discrepancies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )


class GoingConcernEvaluation(Base):
    __tablename__ = "going_concern_evaluations"
    __table_args__ = (Index("ix_going_concern_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    evaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    conclusion: Mapped[GoingConcernConclusion] = mapped_column(Enum(GoingConcernConclusion, name="going_concern_conclusion"), nullable=False)
    key_indicators: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    management_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    auditor_conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class GoingConcernIndicator(Base):
    __tablename__ = "going_concern_indicators"
    __table_args__ = (Index("ix_going_concern_indicators_eval", "evaluation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("going_concern_evaluations.id"), nullable=False)
    indicator_type: Mapped[str] = mapped_column(String(100), nullable=False)
    indicator_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    threshold: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    severity: Mapped[SeverityLevel] = mapped_column(Enum(SeverityLevel, name="severity_level"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


class CheckStatus(str, enum.Enum):
    pending = "pending"
    pass_ = "pass"
    fail = "fail"
    na = "na"


class ArchiveChecklist(Base):
    __tablename__ = "archive_checklists"
    __table_args__ = (Index("ix_archive_checklists_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    check_status: Mapped[CheckStatus] = mapped_column(Enum(CheckStatus, name="check_status_enum"), default=CheckStatus.pending, nullable=False)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


class ModificationType(str, enum.Enum):
    addition = "addition"
    deletion = "deletion"
    replacement = "replacement"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ArchiveModification(Base):
    __tablename__ = "archive_modifications"
    __table_args__ = (Index("ix_archive_modifications_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    modification_type: Mapped[ModificationType] = mapped_column(Enum(ModificationType, name="modification_type_enum"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    request_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus, name="approval_status_enum"), default=ApprovalStatus.pending, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
class WorkpaperReviewRecord(Base):
    """工作底稿复核记录"""
    __tablename__ = "workpaper_review_records"
    __table_args__ = (Index("ix_workpaper_review_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    workpaper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workpaper_type: Mapped[str] = mapped_column(String(100), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    review_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="review_status_enum"), nullable=False
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    issues_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )


# ── Phase 010b ── Subsequent Events & SE Checklist ──


class SubsequentEventType(str, enum.Enum):
    adjusting = "ADJUSTING"
    non_adjusting = "NON_ADJUSTING"


class SubsequentEvent(Base):
    __tablename__ = "subsequent_events"
    __table_args__ = (Index("ix_subsequent_events_project_date", "project_id", "event_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_type: Mapped[SubsequentEventType] = mapped_column(Enum(SubsequentEventType, name="subsequent_event_type"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    financial_impact: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    adjustment_posted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audit_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class SEChecklist(Base):
    __tablename__ = "se_checklist"
    __table_args__ = (Index("ix_se_checklist_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)



# ── Phase 3: Version Control & Sync ────────────────────────────────────────────
# ── 010c ── Sync Enums ──────────────────────────────────────────────────────────


class OpType(str, enum.Enum):
    """操作类型枚举"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    REVIEW = "review"
    APPROVE = "approve"
    COMMENT = "comment"


class SyncStatus(str, enum.Enum):
    """同步状态"""
    IDLE = "idle"
    SYNCING = "syncing"
    SYNCED = "synced"
    CONFLICT = "conflict"
    ERROR = "error"


class SyncType(str, enum.Enum):
    """同步操作类型"""
    UPLOAD = "upload"
    DOWNLOAD = "download"
    CONFLICT_RESOLUTION = "conflict_resolution"
    LOCK = "lock"
    UNLOCK = "unlock"
    EXPORT = "export"
    IMPORT = "import"


class MilestoneType(str, enum.Enum):
    """里程碑类型"""
    PLANNING = "planning"
    FIELDWORK = "fieldwork"
    REVIEW = "review"
    REPORT = "report"
    COMPLETION = "completion"


class PbcStatus(str, enum.Enum):
    """PBC 状态"""
    PENDING = "pending"
    RECEIVED = "received"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class ConfirmationStatusEnum(str, enum.Enum):
    """询证函状态枚举"""
    DRAFT = "draft"
    SENT = "sent"
    RECEIVED = "received"
    VERIFIED = "verified"
    REJECTED = "rejected"


class LetterFormat(str, enum.Enum):
    """询证函格式"""
    PDF = "pdf"
    WORD = "word"
    EMAIL = "email"
    PHYSICAL = "physical"


class ReplyStatus(str, enum.Enum):
    """回函状态"""
    PENDING = "pending"
    MATCHED = "matched"
    EXCEPTIONAL = "exceptional"
    NO_REPLY = "no_reply"


class GcRiskLevel(str, enum.Enum):
    """持续经营风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IndicatorSeverity(str, enum.Enum):
    """指标严重程度"""
    NORMAL = "normal"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"


class ApprovalStatus(str, enum.Enum):
    """审批状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ── 010d ── Sync Models ────────────────────────────────────────────────────────


class ProjectSync(Base):
    """项目同步状态"""
    __tablename__ = "project_sync"
    __table_args__ = (Index("ix_project_sync_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, unique=True)
    global_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sync_status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, name="sync_status_enum", create_constraint=True),
        default=SyncStatus.IDLE,
        nullable=False,
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


class SyncLog(Base):
    """同步日志"""
    __tablename__ = "sync_logs"
    __table_args__ = (
        Index("ix_sync_logs_project", "project_id"),
        Index("ix_sync_logs_time", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    sync_type: Mapped[SyncType] = mapped_column(
        Enum(SyncType, name="sync_type_enum", create_constraint=True),
        nullable=False,
    )
    version_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


class ProjectTimeline(Base):
    """项目时间线/里程碑"""
    __tablename__ = "project_timeline"
    __table_args__ = (Index("ix_project_timeline_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    milestone_type: Mapped[MilestoneType] = mapped_column(
        Enum(MilestoneType, name="milestone_type_enum", create_constraint=True),
        nullable=False,
    )
    milestone_name: Mapped[str] = mapped_column(String(200), nullable=False)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


class WorkHours(Base):
    """工时记录 — Phase 3 遗留表，已被 Phase 9 staff_models.WorkHour 替代"""
    __tablename__ = "work_hours_legacy"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


class BudgetHours(Base):
    """预算工时"""
    __tablename__ = "budget_hours"
    __table_args__ = (Index("ix_budget_hours_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    phase: Mapped[str] = mapped_column(String(100), nullable=False)
    planned_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    actual_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


class PBCChecklist(Base):
    """PBC 清单项"""
    __tablename__ = "pbc_checklist"
    __table_args__ = (Index("ix_pbc_checklist_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PbcStatus] = mapped_column(
        Enum(PbcStatus, name="pbc_status_enum", create_constraint=True),
        default=PbcStatus.PENDING,
        nullable=False,
    )
    requested_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    received_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
