"""Management Letter Service — internal control deficiency tracking and follow-up.

Validates: Requirements 11.5, 11.9
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import uuid


class ManagementLetterService:
    @staticmethod
    def create_item(
        db: Session,
        project_id: str,
        deficiency_type: str,
        deficiency_description: str,
        potential_impact: str = "",
        recommendation: str = "",
        management_response: Optional[str] = None,
        response_deadline: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> dict:
        """Create management letter item."""
        # Generate item code
        item_code = f"ML-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

        item = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "item_code": item_code,
            "deficiency_type": deficiency_type,  # significant_deficiency / material_weakness / other_deficiency
            "deficiency_description": deficiency_description,
            "potential_impact": potential_impact,
            "recommendation": recommendation,
            "management_response": management_response,
            "response_deadline": response_deadline,
            "prior_year_item_id": None,
            "follow_up_status": "new",
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return item

    @staticmethod
    def carry_forward_items(
        db: Session,
        source_project_id: str,
        target_project_id: str,
        prior_items: List[dict],
    ) -> List[dict]:
        """Carry forward unresolved items from prior year.

        Only items where follow_up_status != 'resolved' are carried forward.
        """
        carried_items: List[dict] = []
        for item in prior_items:
            # Only carry forward unresolved items
            if item.get("follow_up_status") in ("new", "in_progress", "carried_forward"):
                new_item = {
                    "id": str(uuid.uuid4()),
                    "project_id": target_project_id,
                    "item_code": f"{item.get('item_code', 'ML')}-CF",
                    "deficiency_type": item.get("deficiency_type"),
                    "deficiency_description": item.get("deficiency_description"),
                    "potential_impact": item.get("potential_impact"),
                    "recommendation": item.get("recommendation"),
                    "management_response": None,  # Reset for new year
                    "response_deadline": None,
                    "prior_year_item_id": item.get("id"),  # Link to prior year item
                    "follow_up_status": "carried_forward",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                carried_items.append(new_item)
            # Skip resolved items
        return carried_items

    @staticmethod
    def update_follow_up(
        db: Session,
        item_id: str,
        follow_up_status: str,
        management_response: Optional[str] = None,
        response_deadline: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Update follow-up status of management letter item."""
        valid_statuses = ["new", "in_progress", "resolved", "carried_forward"]
        if follow_up_status not in valid_statuses:
            raise ValueError(f"Invalid follow_up_status. Must be one of: {valid_statuses}")

        result = {
            "id": item_id,
            "follow_up_status": follow_up_status,
            "management_response": management_response,
            "response_deadline": response_deadline,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if notes:
            result["notes"] = notes
        return result

    @staticmethod
    def get_items_by_project(
        db: Session,
        project_id: str,
        include_resolved: bool = True,
    ) -> List[dict]:
        """Get all management letter items for a project."""
        # In production, would query the database
        return []

    @staticmethod
    def get_unresolved_items(
        db: Session,
        project_id: str,
    ) -> List[dict]:
        """Get unresolved items (follow_up_status != resolved) for carry-forward."""
        return []
