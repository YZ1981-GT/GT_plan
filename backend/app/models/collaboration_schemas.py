"""Phase 3 协作与质控 Pydantic Schema 定义

Validates: Requirements 10.1-10.21
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class UserBase(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    office_code: Optional[str] = None


class UserCreate(UserBase):
    password: str
    role: str = "auditor"


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    office_code: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: Optional[str] = None
    role: str
    office_code: Optional[str] = None
    email: Optional[str] = None
    is_active: bool = True


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Project User schemas
# ---------------------------------------------------------------------------

class ProjectUserCreate(BaseModel):
    user_id: str
    project_role: str
    assigned_cycles: Optional[list[str]] = None
    assigned_account_ranges: Optional[list[str]] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class ProjectUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    user_id: str
    project_role: str
    assigned_cycles: Optional[list[str]] = None
    assigned_account_ranges: Optional[list[str]] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class ProjectUserBulkAssign(BaseModel):
    user_ids: list[str]
    project_role: str


# ---------------------------------------------------------------------------
# Review schemas
# ---------------------------------------------------------------------------

class ReviewCreate(BaseModel):
    workpaper_id: str
    project_id: str
    review_level: int = Field(ge=1, le=3)
    comments: Optional[str] = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workpaper_id: str
    project_id: str
    reviewer_id: Optional[str] = None
    review_level: int
    review_status: str
    comments: Optional[str] = None
    reply_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ReviewActionRequest(BaseModel):
    comments: Optional[str] = None
    reply_text: Optional[str] = None


# ---------------------------------------------------------------------------
# Subsequent Event schemas
# ---------------------------------------------------------------------------

class SubsequentEventCreate(BaseModel):
    event_date: date
    event_type: str
    description: str
    financial_impact: Optional[Decimal] = None
    adjustment_id: Optional[str] = None
    disclosed_in_note_id: Optional[str] = None


class SubsequentEventUpdate(BaseModel):
    event_date: Optional[date] = None
    event_type: Optional[str] = None
    description: Optional[str] = None
    financial_impact: Optional[Decimal] = None
    adjustment_id: Optional[str] = None
    disclosed_in_note_id: Optional[str] = None
    is_disclosed: Optional[bool] = None


class SubsequentEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    event_date: date
    event_type: str
    description: str
    financial_impact: Optional[Decimal] = None
    is_disclosed: bool
    adjustment_id: Optional[str] = None
    disclosed_in_note_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SEChecklistUpdate(BaseModel):
    is_completed: Optional[bool] = None
    notes: Optional[str] = None


class SEChecklistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    item_code: Optional[str] = None
    description: str
    is_completed: bool
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Sync schemas
# ---------------------------------------------------------------------------

class SyncStatus(BaseModel):
    project_id: str
    global_version: int
    last_synced_at: Optional[datetime] = None
    sync_status: str
    is_locked: bool
    locked_by: Optional[str] = None


class SyncResult(BaseModel):
    project_id: str
    version: int
    sync_type: str
    timestamp: datetime


class SyncConflict(BaseModel):
    conflict_id: str
    object_type: str
    object_id: str
    local_value: dict
    server_value: dict
    conflict_field: str


class ExportScope(BaseModel):
    project_id: str
    include_trial_balance: bool = True
    include_adjustments: bool = True
    include_workpapers: bool = True
    include_report: bool = True


class ImportResult(BaseModel):
    project_id: str
    imported_records: int
    skipped_records: int
    errors: list[str] = []


# ---------------------------------------------------------------------------
# Dashboard schemas
# ---------------------------------------------------------------------------

class ProjectOverview(BaseModel):
    project_id: str
    project_name: str
    status: str
    workpaper_completion_rate: float
    review_completion_rate: float
    days_until_deadline: int
    team_size: int
    pbc_pending_count: int
    overdue_count: int


class RiskAlert(BaseModel):
    alert_id: str
    alert_type: str
    severity: str
    message: str
    related_object_type: Optional[str] = None
    related_object_id: Optional[str] = None
    created_at: datetime


class WorkloadSummary(BaseModel):
    project_id: str
    phase: str
    budget_hours: Decimal
    actual_hours: Decimal
    utilization_rate: float


# ---------------------------------------------------------------------------
# Workhour schemas
# ---------------------------------------------------------------------------

class WorkhourCreate(BaseModel):
    work_date: date
    hours: Decimal = Field(gt=0)
    work_description: Optional[str] = None
    user_id: Optional[str] = None


class WorkhourResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    user_id: Optional[str] = None
    work_date: date
    hours: Decimal
    work_description: Optional[str] = None


class BudgetHourUpdate(BaseModel):
    phase: str
    budget_hours: Decimal


# ---------------------------------------------------------------------------
# PBC schemas
# ---------------------------------------------------------------------------

class PBCItemCreate(BaseModel):
    item_name: str
    category: Optional[str] = None
    requested_date: Optional[date] = None
    notes: Optional[str] = None


class PBCItemUpdate(BaseModel):
    item_name: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    received_date: Optional[date] = None
    notes: Optional[str] = None


class PBCItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    item_name: str
    category: Optional[str] = None
    requested_date: Optional[date] = None
    received_date: Optional[date] = None
    status: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Notification schemas
# ---------------------------------------------------------------------------

class NotificationFilter(BaseModel):
    unread_only: bool = False
    notification_type: Optional[str] = None
    related_object_type: Optional[str] = None


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    notification_type: str
    title: str
    content: Optional[str] = None
    related_object_type: Optional[str] = None
    related_object_id: Optional[str] = None
    is_read: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Confirmation schemas
# ---------------------------------------------------------------------------

class ConfirmationCreate(BaseModel):
    confirmation_type: str
    description: str
    counterparty_name: str
    account_info: Optional[str] = None
    balance: Optional[Decimal] = None
    balance_date: Optional[date] = None


class ConfirmationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    confirmation_type: str
    description: str
    counterparty_name: str
    account_info: Optional[str] = None
    balance: Optional[Decimal] = None
    balance_date: Optional[date] = None
    status: str


class ConfirmationResultCreate(BaseModel):
    reply_date: Optional[date] = None
    reply_status: str
    confirmed_amount: Optional[Decimal] = None
    difference_amount: Optional[Decimal] = None
    difference_reason: Optional[str] = None
    needs_adjustment: bool = False
    alternative_procedure: Optional[str] = None
    alternative_conclusion: Optional[str] = None


class ConfirmationResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    confirmation_list_id: str
    reply_date: Optional[date] = None
    reply_status: str
    confirmed_amount: Optional[Decimal] = None
    difference_amount: Optional[Decimal] = None
    difference_reason: Optional[str] = None
    needs_adjustment: bool


class ConfirmationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    summary_date: date
    total_count: int
    sent_count: int
    replied_count: int
    matched_count: int
    mismatched_count: int
    not_replied_count: int
    returned_count: int


class ConfirmationAttachment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    confirmation_list_id: str
    file_name: str
    file_path: str


# ---------------------------------------------------------------------------
# Going Concern schemas
# ---------------------------------------------------------------------------

class GoingConcernCreate(BaseModel):
    assessment_date: Optional[date] = None
    has_gc_indicator: bool = False
    risk_level: str = "low"
    assessment_basis: str = ""


class GoingConcernUpdate(BaseModel):
    has_gc_indicator: Optional[bool] = None
    risk_level: Optional[str] = None
    assessment_basis: Optional[str] = None
    management_plans: Optional[str] = None
    auditor_conclusion: Optional[str] = None


class GoingConcernIndicatorUpdate(BaseModel):
    is_identified: bool
    evidence: Optional[str] = None


class GoingConcernResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    assessment_date: date
    has_gc_indicator: bool
    risk_level: str
    assessment_basis: str
    management_plans: Optional[str] = None
    auditor_conclusion: Optional[str] = None


class GoingConcernIndicatorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    going_concern_id: str
    indicator_type: str
    description: Optional[str] = None
    severity: str
    is_identified: bool
    evidence: Optional[str] = None


# ---------------------------------------------------------------------------
# Archive schemas
# ---------------------------------------------------------------------------

class ArchiveChecklistUpdate(BaseModel):
    is_completed: Optional[bool] = None
    notes: Optional[str] = None


class ArchiveChecklistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    item_code: Optional[str] = None
    item_name: str
    category: Optional[str] = None
    is_completed: bool
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    notes: Optional[str] = None


class ArchiveProjectRequest(BaseModel):
    password: Optional[str] = None


class ArchiveProjectResponse(BaseModel):
    project_id: str
    archived_at: datetime
    retention_expiry_date: date


class ArchiveModificationRequest(BaseModel):
    modification_type: str
    description: str


class ArchiveModificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    modification_type: str
    description: str
    approval_status: str
    requested_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Timeline schemas
# ---------------------------------------------------------------------------

class TimelineCreate(BaseModel):
    milestone_type: str
    due_date: date
    notes: Optional[str] = None


class TimelineUpdate(BaseModel):
    due_date: Optional[date] = None
    completed_date: Optional[date] = None
    is_completed: Optional[bool] = None
    notes: Optional[str] = None


class TimelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    milestone_type: str
    due_date: date
    completed_date: Optional[date] = None
    is_completed: bool
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Audit Program schemas
# ---------------------------------------------------------------------------

class RiskAssessmentCreate(BaseModel):
    account_or_cycle: str
    assertion_level: str
    inherent_risk: str
    control_risk: str
    is_significant_risk: bool = False
    risk_description: Optional[str] = None
    response_strategy: Optional[str] = None


class RiskAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    account_or_cycle: str
    assertion_level: str
    inherent_risk: str
    control_risk: str
    combined_risk: Optional[str] = None
    is_significant_risk: bool
    risk_description: Optional[str] = None
    response_strategy: Optional[str] = None


class AuditPlanCreate(BaseModel):
    audit_strategy: Optional[str] = None
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    key_focus_areas: Optional[list[str]] = None
    team_assignment_summary: Optional[dict] = None
    materiality_reference: Optional[str] = None


class AuditPlanUpdate(BaseModel):
    audit_strategy: Optional[str] = None
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    key_focus_areas: Optional[list[str]] = None
    team_assignment_summary: Optional[dict] = None
    materiality_reference: Optional[str] = None
    status: Optional[str] = None


class AuditPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    plan_version: int
    audit_strategy: Optional[str] = None
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    key_focus_areas: Optional[list] = None
    team_assignment_summary: Optional[dict] = None
    materiality_reference: Optional[str] = None
    status: str
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class AuditProcedureCreate(BaseModel):
    procedure_code: str
    procedure_name: str
    procedure_type: str
    audit_cycle: Optional[str] = None
    account_code: Optional[str] = None
    description: Optional[str] = None
    related_risk_id: Optional[str] = None
    related_wp_code: Optional[str] = None


class AuditProcedureUpdate(BaseModel):
    procedure_name: Optional[str] = None
    description: Optional[str] = None
    execution_status: Optional[str] = None
    executed_by: Optional[str] = None
    executed_at: Optional[date] = None
    conclusion: Optional[str] = None


class AuditProcedureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    procedure_code: str
    procedure_name: str
    procedure_type: str
    audit_cycle: Optional[str] = None
    account_code: Optional[str] = None
    description: Optional[str] = None
    execution_status: str
    executed_by: Optional[str] = None
    executed_at: Optional[date] = None
    conclusion: Optional[str] = None
    related_wp_code: Optional[str] = None
    related_risk_id: Optional[str] = None


class AuditFindingCreate(BaseModel):
    finding_code: str
    finding_description: str
    severity: str
    affected_account: Optional[str] = None
    finding_amount: Optional[Decimal] = None
    management_response: Optional[str] = None
    related_adjustment_id: Optional[str] = None
    related_wp_code: Optional[str] = None


class AuditFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    finding_code: str
    finding_description: str
    severity: str
    affected_account: Optional[str] = None
    finding_amount: Optional[Decimal] = None
    management_response: Optional[str] = None
    final_treatment: Optional[str] = None
    related_adjustment_id: Optional[str] = None
    related_wp_code: Optional[str] = None
    identified_by: Optional[str] = None


class ManagementLetterCreate(BaseModel):
    item_code: str
    deficiency_type: str
    deficiency_description: str
    potential_impact: Optional[str] = None
    recommendation: Optional[str] = None
    management_response: Optional[str] = None
    response_deadline: Optional[date] = None


class ManagementLetterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    item_code: str
    deficiency_type: str
    deficiency_description: str
    potential_impact: Optional[str] = None
    recommendation: Optional[str] = None
    management_response: Optional[str] = None
    response_deadline: Optional[date] = None
    follow_up_status: str
    prior_year_item_id: Optional[str] = None
    identified_by: Optional[str] = None
