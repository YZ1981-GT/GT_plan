"""人员库 + 团队委派 + 工时管理 Pydantic Schemas

Phase 9 Task 1.1
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# StaffMember Schemas
# ---------------------------------------------------------------------------


class StaffCreate(BaseModel):
    name: str
    employee_no: str | None = None
    department: str | None = None
    title: str | None = None
    partner_name: str | None = None
    specialty: str | None = None
    phone: str | None = None
    email: str | None = None
    join_date: date | None = None


class StaffUpdate(BaseModel):
    name: str | None = None
    department: str | None = None
    title: str | None = None
    partner_name: str | None = None
    specialty: str | None = None
    phone: str | None = None
    email: str | None = None
    join_date: date | None = None


class StaffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None = None
    name: str
    employee_no: str | None = None
    department: str | None = None
    title: str | None = None
    partner_name: str | None = None
    partner_id: UUID | None = None
    specialty: str | None = None
    phone: str | None = None
    email: str | None = None
    join_date: date | None = None
    resume_data: dict | None = None
    created_at: datetime | None = None


class StaffListResponse(BaseModel):
    items: list[StaffResponse]
    total: int


# ---------------------------------------------------------------------------
# ProjectAssignment Schemas
# ---------------------------------------------------------------------------


class AssignmentCreate(BaseModel):
    staff_id: UUID
    role: str  # signing_partner / manager / auditor / qc
    assigned_cycles: list[str] | None = None  # ["B", "C", "D"]


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    staff_id: UUID
    role: str
    assigned_cycles: list[str] | None = None
    assigned_at: datetime | None = None
    assigned_by: UUID | None = None
    # 关联字段（API 返回时填充）
    staff_name: str | None = None
    staff_title: str | None = None


class AssignmentBatchRequest(BaseModel):
    assignments: list[AssignmentCreate]


# ---------------------------------------------------------------------------
# WorkHour Schemas
# ---------------------------------------------------------------------------


class WorkHourCreate(BaseModel):
    project_id: UUID
    work_date: date
    hours: Decimal = Field(ge=0, le=24)
    start_time: time | None = None
    end_time: time | None = None
    description: str | None = None


class WorkHourUpdate(BaseModel):
    hours: Decimal | None = Field(default=None, ge=0, le=24)
    start_time: time | None = None
    end_time: time | None = None
    description: str | None = None
    status: str | None = None


class WorkHourResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    staff_id: UUID
    project_id: UUID
    work_date: date
    hours: Decimal
    start_time: time | None = None
    end_time: time | None = None
    description: str | None = None
    status: str
    ai_suggested: bool = False
    created_at: datetime | None = None
    # 关联字段
    project_name: str | None = None


class WorkHourValidationWarning(BaseModel):
    warning_type: str  # daily_over_24h / consecutive_overtime / time_overlap
    message: str
    details: dict | None = None


class WorkHourAISuggestRequest(BaseModel):
    staff_id: UUID
    target_date: date


class WorkHourAISuggestResponse(BaseModel):
    suggestions: list[WorkHourCreate]
    reasoning: str | None = None


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


class StaffResumeResponse(BaseModel):
    staff_id: UUID
    name: str
    title: str | None = None
    department: str | None = None
    total_projects: int = 0
    industries: list[str] = []
    audit_types: list[str] = []
    recent_projects: list[dict] = []
