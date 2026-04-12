"""Audit Program Service — audit procedures management and coverage reporting.

Validates: Requirements 11.3, 11.8, 11.10
"""

from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from datetime import datetime, timezone, date
import uuid


class AuditProgramService:
    @staticmethod
    def create_program(
        db: Session,
        project_id: str,
        program_name: str,
        audit_strategy: str = "",
        planned_start_date: Optional[str] = None,
        planned_end_date: Optional[str] = None,
        key_focus_areas: Optional[List[str]] = None,
        team_assignment_summary: Optional[List[dict]] = None,
        created_by: Optional[str] = None,
    ) -> dict:
        """Create audit program with initial procedures."""
        program = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "program_name": program_name,
            "audit_strategy": audit_strategy,
            "planned_start_date": planned_start_date,
            "planned_end_date": planned_end_date,
            "key_focus_areas": key_focus_areas or [],
            "team_assignment_summary": team_assignment_summary or [],
            "plan_version": 1,
            "status": "draft",
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return program

    @staticmethod
    def create_procedure(
        db: Session,
        project_id: str,
        program_id: str,
        procedure_code: str,
        procedure_name: str,
        procedure_type: str,
        audit_cycle: str,
        description: str,
        related_risk_id: Optional[str] = None,
        related_wp_code: Optional[str] = None,
        account_code: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> dict:
        """Create audit procedure linked to risk assessment and workpaper."""
        procedure = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "program_id": program_id,
            "procedure_code": procedure_code,
            "procedure_name": procedure_name,
            "procedure_type": procedure_type,  # risk_assessment / control_test / substantive
            "audit_cycle": audit_cycle,
            "description": description,
            "account_code": account_code,
            "execution_status": "not_started",
            "executed_by": None,
            "executed_at": None,
            "conclusion": None,
            "related_risk_id": related_risk_id,
            "related_wp_code": related_wp_code,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return procedure

    @staticmethod
    def update_procedure_status(
        db: Session,
        program_id: str,
        procedure_id: str,
        status: str,
        conclusion: Optional[str] = None,
        executed_by: Optional[str] = None,
    ) -> dict:
        """Update procedure execution status and conclusion."""
        valid_statuses = ["not_started", "in_progress", "completed", "not_applicable"]
        if status not in valid_statuses:
            raise ValueError(f"Invalid status. Must be one of: {valid_statuses}")

        result = {
            "id": procedure_id,
            "program_id": program_id,
            "execution_status": status,
            "conclusion": conclusion,
            "executed_by": executed_by,
            "executed_at": datetime.now(timezone.utc).isoformat() if status == "completed" else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return result

    @staticmethod
    def link_procedure_to_workpaper(
        db: Session,
        program_id: str,
        procedure_id: str,
        workpaper_id: str,
        workpaper_code: Optional[str] = None,
    ) -> dict:
        """Link procedure to a workpaper."""
        return {
            "id": procedure_id,
            "program_id": program_id,
            "related_wp_id": workpaper_id,
            "related_wp_code": workpaper_code,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def get_program_coverage_report(
        db: Session,
        program_id: str,
        risks: List[dict],
        procedures: List[dict],
    ) -> dict:
        """Generate risk-program coverage matrix report."""
        # Build coverage matrix
        coverage: Dict[str, List[dict]] = {}
        for proc in procedures:
            related_risk_id = proc.get("related_risk_id")
            if related_risk_id:
                if related_risk_id not in coverage:
                    coverage[related_risk_id] = []
                coverage[related_risk_id].append({
                    "procedure_id": proc.get("id"),
                    "procedure_name": proc.get("procedure_name"),
                    "procedure_code": proc.get("procedure_code"),
                    "status": proc.get("execution_status"),
                })

        coverage_details: List[dict] = []
        for risk in risks:
            risk_id = risk.get("id", "")
            procedures_for_risk = coverage.get(risk_id, [])
            coverage_details.append({
                "risk": risk,
                "procedures": procedures_for_risk,
                "is_covered": len(procedures_for_risk) > 0,
                "all_completed": all(p.get("status") == "completed" for p in procedures_for_risk),
            })

        total_risks = len(risks)
        covered_risks = sum(1 for c in coverage_details if c["is_covered"])
        fully_covered = sum(1 for c in coverage_details if c["all_completed"])

        return {
            "program_id": program_id,
            "total_risks": total_risks,
            "covered_risks": covered_risks,
            "uncovered_risks": total_risks - covered_risks,
            "fully_covered": fully_covered,
            "coverage_rate": round(covered_risks / total_risks * 100, 2) if total_risks > 0 else 100.0,
            "details": coverage_details,
        }

    @staticmethod
    def approve_program(
        db: Session,
        program_id: str,
        approved_by: str,
    ) -> dict:
        """Approve audit program."""
        return {
            "id": program_id,
            "status": "approved",
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def revise_program(
        db: Session,
        program_id: str,
        revised_by: str,
        revision_reason: str = "",
    ) -> dict:
        """Revise audit program (creates new version)."""
        return {
            "id": program_id,
            "status": "revised",
            "plan_version_increment": 1,
            "revision_reason": revision_reason,
            "revised_by": revised_by,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def update_execution_status(
        db: Session,
        procedure_id: str,
        execution_status: str,
        conclusion: Optional[str] = None,
        executed_by: Optional[str] = None,
    ) -> dict:
        """Update audit procedure execution status and conclusion."""
        return {
            "id": procedure_id,
            "execution_status": execution_status,  # not_started / in_progress / completed / not_applicable
            "conclusion": conclusion,
            "executed_by": executed_by,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
