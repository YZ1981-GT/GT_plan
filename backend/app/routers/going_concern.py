from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.going_concern_service import GoingConcernService
from app.services.permission_service import Permission, check_project_permission

router = APIRouter(prefix="/going-concern", tags=["going-concern"])


class CreateEvaluationRequest(BaseModel):
    assessment_date: Optional[date] = None


class UpdateEvaluationRequest(BaseModel):
    has_gc_indicator: bool
    risk_level: str  # HIGH, MEDIUM, LOW
    assessment_basis: Optional[str] = None
    management_plans: Optional[str] = None
    auditor_conclusion: Optional[str] = None


class IndicatorResponse(BaseModel):
    id: str
    indicator_type: str
    description: Optional[str]
    severity: str
    is_identified: bool
    evidence: Optional[str]

    class Config:
        from_attributes = True


@router.post("/{project_id}/init")
def init_indicators(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(status_code=403, detail="No permission")
    inds = GoingConcernService.init_indicators(db, project_id, str(user.id))
    return {"message": f"Initialized {len(inds)} indicators"}


@router.post("/{project_id}/evaluation")
def create_evaluation(
    project_id: str,
    req: CreateEvaluationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(status_code=403, detail="No permission")
    assessment_dt = str(req.assessment_date) if req.assessment_date else None
    gc = GoingConcernService.create_evaluation(db, project_id, assessment_dt, str(user.id))
    return {"id": str(gc.id)}


@router.get("/{project_id}/evaluation")
def get_evaluation(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    gc = GoingConcernService.get_evaluation(db, project_id)
    if not gc:
        return None
    inds = GoingConcernService.get_indicators(db, str(gc.id))
    return {
        "id": str(gc.id),
        "assessment_date": str(gc.assessment_date),
        "has_gc_indicator": gc.has_gc_indicator,
        "risk_level": str(gc.risk_level.value) if hasattr(gc.risk_level, 'value') else str(gc.risk_level),
        "assessment_basis": gc.assessment_basis,
        "management_plans": gc.management_plans,
        "auditor_conclusion": gc.auditor_conclusion,
        "indicators": [
            {
                "id": str(i.id),
                "indicator_type": i.indicator_type,
                "description": i.description,
                "severity": str(i.severity.value) if hasattr(i.severity, 'value') else str(i.severity),
                "is_identified": i.is_identified,
                "evidence": i.evidence,
            }
            for i in inds
        ],
    }


@router.patch("/{project_id}/evaluation/{gc_id}")
def update_evaluation(
    project_id: str,
    gc_id: str,
    req: UpdateEvaluationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    gc = GoingConcernService.update_evaluation(
        db, gc_id, req.has_gc_indicator, req.risk_level,
        req.assessment_basis, req.management_plans, req.auditor_conclusion,
    )
    if not gc:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return {
        "id": str(gc.id),
        "risk_level": str(gc.risk_level.value) if hasattr(gc.risk_level, 'value') else str(gc.risk_level)
    }


@router.get("/{project_id}/evaluation/{gc_id}/indicators")
def get_indicators(
    project_id: str,
    gc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    inds = GoingConcernService.get_indicators(db, gc_id)
    return [
        IndicatorResponse(
            id=str(i.id),
            indicator_type=i.indicator_type,
            description=i.description,
            severity=str(i.severity.value) if hasattr(i.severity, 'value') else str(i.severity),
            is_identified=i.is_identified,
            evidence=i.evidence,
        )
        for i in inds
    ]


@router.patch("/{project_id}/evaluation/{gc_id}/indicators/{ind_id}")
def update_indicator(
    project_id: str,
    gc_id: str,
    ind_id: str,
    is_identified: bool = Query(...),
    evidence: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ind = GoingConcernService.update_indicator(db, ind_id, is_identified, evidence)
    if not ind:
        raise HTTPException(status_code=404, detail="Indicator not found")
    return {"id": str(ind.id), "is_identified": ind.is_identified}
