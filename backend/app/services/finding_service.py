"""Audit Finding Service — audit finding tracking and adjustment linkage.

Validates: Requirements 11.4
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import uuid


class AuditFindingService:
    @staticmethod
    def create_finding(
        db: Session,
        project_id: str,
        finding_description: str,
        severity: str,
        affected_account: Optional[str] = None,
        finding_amount: Optional[float] = None,
        management_response: Optional[str] = None,
        related_adjustment_id: Optional[str] = None,
        related_wp_code: Optional[str] = None,
        identified_by: Optional[str] = None,
    ) -> dict:
        """Create audit finding."""
        # Generate finding code
        finding_code = f"FIND-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

        finding = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "finding_code": finding_code,
            "finding_description": finding_description,
            "severity": severity.lower(),  # high / medium / low
            "affected_account": affected_account,
            "finding_amount": finding_amount,
            "management_response": management_response,
            "final_treatment": None,  # adjusted / unadjusted / disclosed / no_action
            "related_adjustment_id": related_adjustment_id,
            "related_wp_code": related_wp_code,
            "identified_by": identified_by,
            "review_status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return finding

    @staticmethod
    def update_finding(
        db: Session,
        finding_id: str,
        management_response: Optional[str] = None,
        final_treatment: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> dict:
        """Update finding details."""
        result = {
            "id": finding_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if management_response is not None:
            result["management_response"] = management_response
        if final_treatment is not None:
            result["final_treatment"] = final_treatment
        if severity is not None:
            result["severity"] = severity.lower()
        return result

    @staticmethod
    def link_to_adjustment(
        db: Session,
        finding_id: str,
        adjustment_id: str,
    ) -> dict:
        """Link finding to adjustment entry."""
        return {
            "id": finding_id,
            "related_adjustment_id": adjustment_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def get_findings_by_project(
        db: Session,
        project_id: str,
        severity_filter: Optional[str] = None,
    ) -> List[dict]:
        """Get all findings for a project, optionally filtered by severity."""
        # In production, would query the database
        findings: List[dict] = []
        if severity_filter:
            findings = [f for f in findings if f.get("severity") == severity_filter.lower()]
        return findings

    @staticmethod
    def get_financial_impact_summary(
        db: Session,
        project_id: str,
    ) -> dict:
        """Calculate total financial impact of findings."""
        findings = AuditFindingService.get_findings_by_project(db, project_id)
        total_amount = sum(
            f.get("finding_amount", 0) or 0
            for f in findings
        )
        high_severity_count = sum(
            1 for f in findings if f.get("severity") == "high"
        )
        adjusted_count = sum(
            1 for f in findings if f.get("final_treatment") == "adjusted"
        )
        unadjusted_count = sum(
            1 for f in findings if f.get("final_treatment") == "unadjusted"
        )

        return {
            "total_findings": len(findings),
            "total_financial_impact": total_amount,
            "high_severity_count": high_severity_count,
            "adjusted_count": adjusted_count,
            "unadjusted_count": unadjusted_count,
        }
