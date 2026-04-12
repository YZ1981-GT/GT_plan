"""Risk Assessment API Router.

Validates: Requirements 11.1, 11.6, 11.7, 11.10
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.services.risk_service import RiskAssessmentService, RISK_MATRIX

router = APIRouter(prefix="/risk-assessments", tags=["风险管理"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RiskAssessmentCreate(BaseModel):
    account_or_cycle: str
    assertion_level: str
    inherent_risk: str  # high / medium / low
    control_risk: str
    risk_description: str = ""
    is_significant_risk: bool = False
    response_strategy: Optional[str] = None


class RiskAssessmentResponse(BaseModel):
    id: str
    project_id: str
    account_or_cycle: str
    assertion_level: str
    inherent_risk: str
    control_risk: str
    combined_risk: str
    is_significant_risk: bool
    risk_description: str
    response_strategy: Optional[str]
    created_at: str
    updated_at: str


class ResponseStrategyUpdate(BaseModel):
    response_strategy: str


class RiskMatrixResponse(BaseModel):
    matrix: dict
    colors: dict
    legend: dict


class CoverageVerificationResponse(BaseModel):
    total_risks: int
    covered_risks: int
    uncovered_risks: int
    is_complete: bool
    uncovered_risk_ids: List[str]


class OverallRiskResponse(BaseModel):
    overall_risk: str
    significant_risks: int
    total_risks: int
    average_risk_score: float


# ---------------------------------------------------------------------------
# In-memory store (replace with DB in production)
# ---------------------------------------------------------------------------
_assessments_store: List[dict] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/risk-assessments", response_model=RiskAssessmentResponse)
def create_risk_assessment(
    project_id: str,
    data: RiskAssessmentCreate,
    db: Session = Depends(get_db),
):
    """Create a new risk assessment record."""
    try:
        assessment = RiskAssessmentService.create_assessment(
            db=db,
            project_id=project_id,
            account_or_cycle=data.account_or_cycle,
            assertion_level=data.assertion_level,
            inherent_risk=data.inherent_risk,
            control_risk=data.control_risk,
            risk_description=data.risk_description,
            is_significant_risk=data.is_significant_risk,
            response_strategy=data.response_strategy,
        )
        _assessments_store.append(assessment)
        return RiskAssessmentResponse(**assessment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/risk-assessments", response_model=List[RiskAssessmentResponse])
def list_risk_assessments(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Get all risk assessments for a project."""
    project_assessments = [a for a in _assessments_store if a["project_id"] == project_id]
    return [RiskAssessmentResponse(**a) for a in project_assessments]


@router.put("/projects/{project_id}/risk-assessments/{assessment_id}/response")
def assign_response_strategy(
    project_id: str,
    assessment_id: str,
    data: ResponseStrategyUpdate,
    db: Session = Depends(get_db),
):
    """Assign response strategy to a significant risk."""
    for assessment in _assessments_store:
        if assessment["id"] == assessment_id:
            assessment["response_strategy"] = data.response_strategy
            assessment["updated_at"] = datetime.utcnow().isoformat()
            return {"message": "Response strategy updated", "assessment": assessment}
    raise HTTPException(status_code=404, detail="Risk assessment not found")


@router.post("/projects/{project_id}/risk-assessments/{assessment_id}/verify-coverage")
def verify_coverage(
    project_id: str,
    assessment_id: str,
    db: Session = Depends(get_db),
):
    """Verify that each risk has at least one audit procedure."""
    # Get all assessments and procedures for the project
    assessments = [a for a in _assessments_store if a["project_id"] == project_id]
    # In production, would also query procedures from audit_program_service
    result = RiskAssessmentService.verify_risk_program_coverage(
        db=db,
        project_id=project_id,
        assessments=assessments,
        procedures=[],  # Would come from audit_program_service
    )
    return result


@router.get("/projects/{project_id}/risk-matrix", response_model=RiskMatrixResponse)
def get_risk_matrix(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Get risk matrix heatmap view."""
    assessments = [a for a in _assessments_store if a["project_id"] == project_id]
    matrix_data = RiskAssessmentService.get_risk_matrix(project_id, assessments)
    return RiskMatrixResponse(**matrix_data)


@router.get("/projects/{project_id}/overall-risk", response_model=OverallRiskResponse)
def get_overall_risk(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Calculate overall project risk level."""
    assessments = [a for a in _assessments_store if a["project_id"] == project_id]
    result = RiskAssessmentService.calculate_overall_risk(
        db=db,
        project_id=project_id,
        assessments=assessments,
    )
    return OverallRiskResponse(**result)
