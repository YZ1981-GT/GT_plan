"""Audit Plan API Router.

Validates: Requirements 11.2
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.services.audit_plan_service import AuditPlanService

router = APIRouter(prefix="/audit-plans", tags=["审计计划"])

# In-memory store (shared across requests in dev)
_plans_store: List[dict] = []


class AuditPlanCreate(BaseModel):
    audit_strategy: str = ""
    planned_start_date: Optional[str] = None
    planned_end_date: Optional[str] = None
    key_focus_areas: Optional[List[str]] = None
    team_assignment_summary: Optional[List[dict]] = None
    materiality_reference: str = ""


class AuditPlanApprove(BaseModel):
    approved_by: str


@router.post("/projects/{project_id}")
def create_audit_plan(
    project_id: str,
    data: AuditPlanCreate,
    db: Session = Depends(get_db),
):
    """Create audit plan for a project."""
    plan = AuditPlanService.create_plan(
        db=db,
        project_id=project_id,
        audit_strategy=data.audit_strategy,
        planned_start_date=data.planned_start_date,
        planned_end_date=data.planned_end_date,
        key_focus_areas=data.key_focus_areas,
        team_assignment_summary=data.team_assignment_summary,
        materiality_reference=data.materiality_reference,
    )
    _plans_store.append(plan)
    return plan


@router.post("/{plan_id}/approve")
def approve_audit_plan(
    plan_id: str,
    data: AuditPlanApprove,
    db: Session = Depends(get_db),
):
    """Approve an audit plan."""
    for plan in _plans_store:
        if plan["id"] == plan_id:
            updated = AuditPlanService.approve_plan(db, plan_id, data.approved_by)
            plan.update(updated)
            return plan
    raise HTTPException(status_code=404, detail="Audit plan not found")


@router.get("/projects/{project_id}")
def get_audit_plans(
    project_id: str,
    db: Session = Depends(get_db),
):
    """List all audit plans for a project."""
    return [p for p in _plans_store if p["project_id"] == project_id and not p.get("is_deleted", False)]
