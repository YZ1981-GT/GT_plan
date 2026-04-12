"""Unit tests for management letter service — carry-forward and follow-up.

Validates: Requirements 11.9
"""

import pytest
from unittest.mock import MagicMock
from app.services.management_letter_service import ManagementLetterService


# ---------------------------------------------------------------------------
# Carry-forward tests
# ---------------------------------------------------------------------------

class TestCarryForward:
    """Test that only unresolved items are carried forward."""

    def test_carry_forward_only_unresolved_items(self):
        """Only items where follow_up_status != 'resolved' should be carried forward."""
        db = MagicMock()
        source_project_id = "proj-prior"
        target_project_id = "proj-current"

        prior_items = [
            {"id": "item-1", "item_code": "ML-2024-001", "follow_up_status": "new"},
            {"id": "item-2", "item_code": "ML-2024-002", "follow_up_status": "in_progress"},
            {"id": "item-3", "item_code": "ML-2024-003", "follow_up_status": "carried_forward"},
            {"id": "item-4", "item_code": "ML-2024-004", "follow_up_status": "resolved"},  # Skip
        ]

        carried = ManagementLetterService.carry_forward_items(
            db=db,
            source_project_id=source_project_id,
            target_project_id=target_project_id,
            prior_items=prior_items,
        )

        assert len(carried) == 3
        item_ids = [item["id"] for item in carried]
        assert "item-4" not in item_ids  # Resolved item should not be carried

    def test_carry_forward_prior_year_item_id_linked(self):
        """Carried items should have prior_year_item_id pointing to original."""
        db = MagicMock()
        prior_items = [
            {
                "id": "prior-item-1",
                "item_code": "ML-2024-001",
                "follow_up_status": "new",
                "deficiency_type": "significant_deficiency",
                "deficiency_description": "Segregation of duties issue",
                "recommendation": "Implement access controls",
            },
        ]

        carried = ManagementLetterService.carry_forward_items(
            db=db,
            source_project_id="proj-prior",
            target_project_id="proj-current",
            prior_items=prior_items,
        )

        assert len(carried) == 1
        assert carried[0]["prior_year_item_id"] == "prior-item-1"
        assert carried[0]["project_id"] == "proj-current"
        assert carried[0]["follow_up_status"] == "carried_forward"

    def test_carry_forward_resets_management_response(self):
        """Carried items should have management_response reset for new year."""
        prior_items = [
            {
                "id": "item-1",
                "item_code": "ML-2024-001",
                "follow_up_status": "new",
                "management_response": "We will fix this in 2025",
            },
        ]

        carried = ManagementLetterService.carry_forward_items(
            db=MagicMock(),
            source_project_id="proj-prior",
            target_project_id="proj-current",
            prior_items=prior_items,
        )

        assert carried[0]["management_response"] is None
        assert carried[0]["response_deadline"] is None

    def test_carry_forward_preserves_deficiency_details(self):
        """Deficiency description and recommendation should be preserved."""
        prior_items = [
            {
                "id": "item-1",
                "item_code": "ML-2024-001",
                "follow_up_status": "new",
                "deficiency_type": "material_weakness",
                "deficiency_description": "Inadequate IT general controls",
                "potential_impact": "Risk of material misstatement",
                "recommendation": "Enhance IT control environment",
            },
        ]

        carried = ManagementLetterService.carry_forward_items(
            db=MagicMock(),
            source_project_id="proj-prior",
            target_project_id="proj-current",
            prior_items=prior_items,
        )

        assert carried[0]["deficiency_type"] == "material_weakness"
        assert carried[0]["deficiency_description"] == "Inadequate IT general controls"
        assert carried[0]["potential_impact"] == "Risk of material misstatement"
        assert carried[0]["recommendation"] == "Enhance IT control environment"

    def test_carry_forward_all_resolved(self):
        """If all items are resolved, no items should be carried."""
        prior_items = [
            {"id": "item-1", "item_code": "ML-001", "follow_up_status": "resolved"},
            {"id": "item-2", "item_code": "ML-002", "follow_up_status": "resolved"},
        ]

        carried = ManagementLetterService.carry_forward_items(
            db=MagicMock(),
            source_project_id="proj-prior",
            target_project_id="proj-current",
            prior_items=prior_items,
        )

        assert len(carried) == 0


# ---------------------------------------------------------------------------
# Follow-up status update tests
# ---------------------------------------------------------------------------

class TestFollowUpUpdate:
    """Test follow-up status updates."""

    def test_update_to_in_progress(self):
        db = MagicMock()
        result = ManagementLetterService.update_follow_up(
            db=db,
            item_id="item-1",
            follow_up_status="in_progress",
            management_response="Management is working on remediation",
        )
        assert result["follow_up_status"] == "in_progress"
        assert result["management_response"] == "Management is working on remediation"

    def test_update_to_resolved(self):
        db = MagicMock()
        result = ManagementLetterService.update_follow_up(
            db=db,
            item_id="item-1",
            follow_up_status="resolved",
            management_response="Controls have been implemented and tested",
        )
        assert result["follow_up_status"] == "resolved"

    def test_update_with_deadline(self):
        db = MagicMock()
        result = ManagementLetterService.update_follow_up(
            db=db,
            item_id="item-1",
            follow_up_status="in_progress",
            response_deadline="2025-06-30",
        )
        assert result["response_deadline"] == "2025-06-30"

    def test_update_with_notes(self):
        db = MagicMock()
        result = ManagementLetterService.update_follow_up(
            db=db,
            item_id="item-1",
            follow_up_status="in_progress",
            notes="Second follow-up meeting held on 2025-03-15",
        )
        assert "notes" in result

    def test_invalid_follow_up_status_raises(self):
        db = MagicMock()
        with pytest.raises(ValueError, match="Invalid follow_up_status"):
            ManagementLetterService.update_follow_up(
                db=db,
                item_id="item-1",
                follow_up_status="invalid_status",
            )


# ---------------------------------------------------------------------------
# Management letter item creation tests
# ---------------------------------------------------------------------------

class TestItemCreation:
    """Test management letter item creation."""

    def test_create_item_generates_code(self):
        db = MagicMock()
        item = ManagementLetterService.create_item(
            db=db,
            project_id="proj-1",
            deficiency_type="significant_deficiency",
            deficiency_description="Inadequate reconciliations",
            potential_impact="Could lead to errors",
            recommendation="Implement monthly reconciliations",
        )
        assert item["item_code"].startswith("ML-")
        assert item["deficiency_type"] == "significant_deficiency"
        assert item["follow_up_status"] == "new"
        assert item["prior_year_item_id"] is None

    def test_create_item_defaults(self):
        db = MagicMock()
        item = ManagementLetterService.create_item(
            db=db,
            project_id="proj-1",
            deficiency_type="material_weakness",
            deficiency_description="Control deficiency",
        )
        assert item["potential_impact"] == ""
        assert item["recommendation"] == ""
        assert item["management_response"] is None


# ---------------------------------------------------------------------------
# Retrieval tests
# ---------------------------------------------------------------------------

class TestRetrieval:
    """Test management letter item retrieval."""

    def test_get_items_by_project(self):
        db = MagicMock()
        items = ManagementLetterService.get_items_by_project(db, "proj-1", include_resolved=True)
        assert isinstance(items, list)

    def test_get_unresolved_items(self):
        db = MagicMock()
        items = ManagementLetterService.get_unresolved_items(db, "proj-1")
        assert isinstance(items, list)
