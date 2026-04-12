from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.project_mgmt_service import ProjectTimelineService, WorkHoursService, BudgetHoursService
from app.services.permission_service import Permission, check_project_permission

router = APIRouter(prefix="/projects", tags=["project-mgmt"])

# Timeline endpoints
@router.post("/{project_id}/timeline")
def create_milestone(
    project_id: str,
    milestone_type: str = Query(...),
    due_date: date = Query(...),
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(403, "No permission")
    m = ProjectTimelineService.create_milestone(db, project_id, milestone_type, due_date, notes)
    return {"id": str(m.id), "milestone_type": str(m.milestone_type.value), "due_date": str(m.due_date)}

@router.get("/{project_id}/timeline")
def get_timeline(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    milestones = ProjectTimelineService.get_project_timeline(db, project_id)
    return [
        {
            "id": str(m.id),
            "milestone_type": str(m.milestone_type.value) if hasattr(m.milestone_type, 'value') else str(m.milestone_type),
            "due_date": str(m.due_date),
            "completed_date": str(m.completed_date) if m.completed_date else None,
            "is_completed": m.is_completed,
            "notes": m.notes,
        }
        for m in milestones
    ]

@router.post("/{project_id}/timeline/{timeline_id}/complete")
def complete_milestone(
    project_id: str,
    timeline_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    m = ProjectTimelineService.complete_milestone(db, timeline_id)
    return {"id": str(m.id), "is_completed": m.is_completed}

# Work Hours endpoints
@router.post("/{project_id}/work-hours")
def log_work_hours(
    project_id: str,
    work_date: date = Query(...),
    hours: float = Query(..., gt=0),
    work_description: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    w = WorkHoursService.log_hours(db, project_id, str(user.id), work_date, hours, work_description)
    return {"id": str(w.id), "hours": float(w.hours), "work_date": str(w.work_date)}

@router.get("/{project_id}/work-hours")
def get_work_hours(
    project_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hours = WorkHoursService.get_user_hours(db, project_id, str(user.id), skip, limit)
    total = WorkHoursService.get_project_total_hours(db, project_id)
    return {
        "total_hours": total,
        "entries": [
            {"id": str(h.id), "work_date": str(h.work_date), "hours": float(h.hours), "description": h.work_description}
            for h in hours
        ],
    }

# Budget Hours endpoints
@router.post("/{project_id}/budget-hours")
def set_budget(
    project_id: str,
    phase: str = Query(...),
    budget_hours: float = Query(..., gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_ADMIN):
        raise HTTPException(403, "No permission")
    b = BudgetHoursService.set_budget(db, project_id, phase, budget_hours)
    return {"id": str(b.id), "phase": b.phase, "budget_hours": float(b.budget_hours)}

@router.get("/{project_id}/budget-hours")
def get_budget_summary(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    budgets = BudgetHoursService.get_budget_summary(db, project_id)
    return [
        {
            "id": str(b.id),
            "phase": b.phase,
            "budget_hours": float(b.budget_hours),
            "actual_hours": float(b.actual_hours),
            "variance": float(b.budget_hours - b.actual_hours),
        }
        for b in budgets
    ]
