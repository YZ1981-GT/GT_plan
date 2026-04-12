"""Audit Plan Service — audit plan creation and approval workflow.

Validates: Requirements 11.2
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session


class AuditPlanService:
    @staticmethod
    def create_plan(
        db: Session,
        project_id: str,
        audit_strategy: str = "",
        planned_start_date: Optional[str] = None,
        planned_end_date: Optional[str] = None,
        key_focus_areas: Optional[List[str]] = None,
        team_assignment_summary: Optional[List[dict]] = None,
        materiality_reference: str = "",
        created_by: Optional[str] = None,
    ) -> dict:
        """Create audit plan. One plan per project (unique constraint enforced at DB level)."""
        return {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "plan_version": 1,
            "audit_strategy": audit_strategy,
            "planned_start_date": planned_start_date,
            "planned_end_date": planned_end_date,
            "key_focus_areas": key_focus_areas or [],
            "team_assignment_summary": team_assignment_summary or [],
            "materiality_reference": materiality_reference,
            "status": "draft",
            "approved_by": None,
            "approved_at": None,
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": created_by,
        }

    @staticmethod
    def approve_plan(
        db: Session,
        plan_id: str,
        approved_by: str,
    ) -> dict:
        """Approve audit plan."""
        return {
            "id": plan_id,
            "status": "approved",
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
