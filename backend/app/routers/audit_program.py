"""Audit Program API Router.

Validates: Requirements 11.3, 11.8, 11.10
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.services.audit_program_service import AuditProgramService

router = APIRouter(prefix="/audit-programs", tags=["审计程序"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AuditProcedureCreate(BaseModel):
    procedure_code: str
    procedure_name: str
    procedure_type: str  # risk_assessment / control_test / substantive
    audit_cycle: str
    description: str
    account_code: Optional[str] = None
    related_risk_id: Optional[str] = None
    related_wp_code: Optional[str] = None


class AuditProgramCreate(BaseModel):
    program_name: str
    audit_strategy: str = ""
    planned_start_date: Optional[str] = None
    planned_end_date: Optional[str] = None
    key_focus_areas: Optional[List[str]] = None
    team_assignment_summary: Optional[List[dict]] = None


class ProcedureStatusUpdate(BaseModel):
    status: str  # not_started / in_progress / completed / not_applicable
    conclusion: Optional[str] = None


class LinkWorkpaperRequest(BaseModel):
    workpaper_id: str
    workpaper_code: Optional[str] = None


class CoverageReportResponse(BaseModel):
    program_id: str
    total_risks: int
    covered_risks: int
    uncovered_risks: int
    coverage_rate: float
    details: List[dict]


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------
_programs_store: List[dict] = []
_procedures_store: List[dict] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/audit-programs")
def create_audit_program(
    project_id: str,
    data: AuditProgramCreate,
    db: Session = Depends(get_db),
):
    """Create a new audit program."""
    program = AuditProgramService.create_program(
        db=db,
        project_id=project_id,
        program_name=data.program_name,
        audit_strategy=data.audit_strategy,
        planned_start_date=data.planned_start_date,
        planned_end_date=data.planned_end_date,
        key_focus_areas=data.key_focus_areas,
        team_assignment_summary=data.team_assignment_summary,
    )
    _programs_store.append(program)
    return program


@router.get("/projects/{project_id}/audit-programs")
def list_audit_programs(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Get all audit programs for a project."""
    programs = [p for p in _programs_store if p["project_id"] == project_id]
    return programs


@router.post("/projects/{project_id}/procedures")
def create_procedure(
    project_id: str,
    program_id: str,
    data: AuditProcedureCreate,
    db: Session = Depends(get_db),
):
    """Create a new audit procedure."""
    procedure = AuditProgramService.create_procedure(
        db=db,
        project_id=project_id,
        program_id=program_id,
        procedure_code=data.procedure_code,
        procedure_name=data.procedure_name,
        procedure_type=data.procedure_type,
        audit_cycle=data.audit_cycle,
        description=data.description,
        account_code=data.account_code,
        related_risk_id=data.related_risk_id,
        related_wp_code=data.related_wp_code,
    )
    _procedures_store.append(procedure)
    return procedure


@router.get("/programs/{program_id}/procedures")
def list_procedures(
    program_id: str,
    db: Session = Depends(get_db),
):
    """Get all procedures for an audit program."""
    procedures = [p for p in _procedures_store if p["program_id"] == program_id]
    return procedures


@router.put("/programs/{program_id}/procedures/{procedure_id}")
def update_procedure_status(
    program_id: str,
    procedure_id: str,
    data: ProcedureStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update procedure execution status."""
    try:
        result = AuditProgramService.update_procedure_status(
            db=db,
            program_id=program_id,
            procedure_id=procedure_id,
            status=data.status,
            conclusion=data.conclusion,
        )
        # Update in store
        for proc in _procedures_store:
            if proc["id"] == procedure_id:
                proc.update(result)
                break
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/programs/{program_id}/procedures/{procedure_id}/link-workpaper")
def link_procedure_to_workpaper(
    program_id: str,
    procedure_id: str,
    data: LinkWorkpaperRequest,
    db: Session = Depends(get_db),
):
    """Link an audit procedure to a workpaper."""
    result = AuditProgramService.link_procedure_to_workpaper(
        db=db,
        program_id=program_id,
        procedure_id=procedure_id,
        workpaper_id=data.workpaper_id,
        workpaper_code=data.workpaper_code,
    )
    # Update in store
    for proc in _procedures_store:
        if proc["id"] == procedure_id:
            proc.update(result)
            break
    return result


@router.get("/programs/{program_id}/coverage-report", response_model=CoverageReportResponse)
def get_coverage_report(
    program_id: str,
    db: Session = Depends(get_db),
):
    """Get risk-program coverage matrix report."""
    # Get risks and procedures
    risks = [a for a in _assessments_store]  # From risk router's store
    procedures = [p for p in _procedures_store if p["program_id"] == program_id]

    result = AuditProgramService.get_program_coverage_report(
        db=db,
        program_id=program_id,
        risks=risks,
        procedures=procedures,
    )
    return CoverageReportResponse(**result)


# ---------------------------------------------------------------------------
# Reference to assessments store (shared with risk router)
# ---------------------------------------------------------------------------
_assessments_store: List[dict] = []


def _set_assessments_store(store: List[dict]):
    global _assessments_store
    _assessments_store = store
