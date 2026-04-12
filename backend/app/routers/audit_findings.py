"""Audit Findings API Router.

Validates: Requirements 11.4
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.services.finding_service import AuditFindingService

router = APIRouter(prefix="/audit-findings", tags=["审计发现"])

# In-memory store
_findings_store: List[dict] = []


class AuditFindingCreate(BaseModel):
    finding_description: str
    severity: str  # high / medium / low
    affected_account: Optional[str] = None
    finding_amount: Optional[float] = None
    management_response: Optional[str] = None
    related_adjustment_id: Optional[str] = None
    related_wp_code: Optional[str] = None


class RecordManagementResponse(BaseModel):
    response: str
    treatment: str  # adjusted / unadjusted / disclosed / no_action


@router.post("/projects/{project_id}")
def create_finding(
    project_id: str,
    data: AuditFindingCreate,
    db: Session = Depends(get_db),
):
    """Create audit finding."""
    finding = AuditFindingService.create_finding(
        db=db,
        project_id=project_id,
        finding_description=data.finding_description,
        severity=data.severity,
        affected_account=data.affected_account,
        finding_amount=data.finding_amount,
        management_response=data.management_response,
        related_adjustment_id=data.related_adjustment_id,
        related_wp_code=data.related_wp_code,
    )
    _findings_store.append(finding)
    return finding


@router.post("/{finding_id}/record-response")
def record_management_response(
    finding_id: str,
    data: RecordManagementResponse,
    db: Session = Depends(get_db),
):
    """Record management response and final treatment."""
    for finding in _findings_store:
        if finding["id"] == finding_id:
            updated = AuditFindingService.update_finding(
                db, finding_id,
                management_response=data.response,
                final_treatment=data.treatment,
            )
            finding.update(updated)
            return finding
    raise HTTPException(status_code=404, detail="Audit finding not found")


@router.get("/projects/{project_id}")
def get_findings(
    project_id: str,
    db: Session = Depends(get_db),
):
    """List all findings for a project."""
    return [f for f in _findings_store if f["project_id"] == project_id and not f.get("is_deleted", False)]


@router.get("/projects/{project_id}/financial-impact")
def get_financial_impact(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Get financial impact summary of all findings."""
    return AuditFindingService.get_financial_impact_summary(db, project_id)
