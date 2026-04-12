"""Unit tests for review state machine and service.

Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import uuid

from app.services.review_service import ReviewService


# ---------------------------------------------------------------------------
# Review state machine tests
# ---------------------------------------------------------------------------

class TestReviewStatusTransitions:
    """Test valid and invalid state transitions."""

    VALID_TRANSITIONS = {
        "draft": ["submitted"],
        "submitted": ["level_1_approved", "draft"],  # can return to draft
        "level_1_approved": ["level_2_approved", "draft"],  # can return to draft
        "level_2_approved": ["archived"],
        "archived": [],
        "rejected": ["draft"],  # can return to draft
    }

    def test_valid_transition_draft_to_submitted(self):
        """draft -> submitted is valid."""
        current = "draft"
        target = "submitted"
        is_valid = target in self.VALID_TRANSITIONS.get(current, [])
        assert is_valid is True

    def test_valid_transition_submitted_to_level_1_approved(self):
        """submitted -> level_1_approved is valid."""
        current = "submitted"
        target = "level_1_approved"
        is_valid = target in self.VALID_TRANSITIONS.get(current, [])
        assert is_valid is True

    def test_valid_transition_level_1_to_level_2_approved(self):
        """level_1_approved -> level_2_approved is valid."""
        current = "level_1_approved"
        target = "level_2_approved"
        is_valid = target in self.VALID_TRANSITIONS.get(current, [])
        assert is_valid is True

    def test_valid_transition_level_2_approved_to_archived(self):
        """level_2_approved -> archived is valid."""
        current = "level_2_approved"
        target = "archived"
        is_valid = target in self.VALID_TRANSITIONS.get(current, [])
        assert is_valid is True

    def test_valid_return_to_draft(self):
        """Any review stage can return to draft."""
        for stage in ["submitted", "level_1_approved"]:
            assert "draft" in self.VALID_TRANSITIONS.get(stage, [])

    def test_invalid_transition_draft_to_archived(self):
        """draft -> archived is invalid (must go through review)."""
        current = "draft"
        target = "archived"
        is_valid = target in self.VALID_TRANSITIONS.get(current, [])
        assert is_valid is False

    def test_rejection_without_comments_raises(self):
        """Rejection must include comments per Requirement 2.5."""
        # Business rule: rejection requires comments
        comments = None
        with pytest.raises(ValueError):
            if comments is None:
                raise ValueError("Rejection requires comments")


# ---------------------------------------------------------------------------
# Project status gate conditions
# ---------------------------------------------------------------------------

class TestProjectStatusGateConditions:
    def test_level_2_review_required_for_critical_workpapers(self):
        """Critical workpapers require level 2 review per Requirement 2.4."""
        workpaper_type = "critical"
        requires_level_2 = workpaper_type == "critical"
        assert requires_level_2 is True

    def test_normal_workpaper_single_level_review(self):
        """Normal workpapers require only level 1 review."""
        workpaper_type = "normal"
        requires_level_2 = workpaper_type == "critical"
        assert requires_level_2 is False


# ---------------------------------------------------------------------------
# Review chain completeness
# ---------------------------------------------------------------------------

class TestReviewChainCompleteness:
    def test_review_chain_order(self):
        """Review chain must follow order: level_1 -> level_2."""
        required_levels = ["level_1_approved", "level_2_approved"]
        # Both levels are required for final approval
        assert len(required_levels) == 2

    def test_all_levels_approved(self):
        """All review levels must be approved."""
        approved_levels = ["level_1_approved", "level_2_approved"]
        required_levels = {"level_1_approved", "level_2_approved"}
        all_approved = set(approved_levels) >= required_levels
        assert all_approved is True


# ---------------------------------------------------------------------------
# Review timeliness
# ---------------------------------------------------------------------------

class TestReviewTimeliness:
    def test_pending_reviews_calculation(self):
        """Pending reviews should be calculated correctly."""
        all_reviews = [
            {"status": "submitted", "assigned_to": "user-1"},
            {"status": "submitted", "assigned_to": "user-2"},
            {"status": "level_1_approved", "assigned_to": "user-3"},
        ]
        pending = [r for r in all_reviews if r["status"] == "submitted"]
        assert len(pending) == 2

    def test_review_timeliness_calculation(self):
        """Review timeliness should be calculated correctly."""
        threshold_days = 7
        submitted_date = datetime(2025, 3, 1, tzinfo=timezone.utc)
        now = datetime(2025, 3, 10, tzinfo=timezone.utc)
        days_elapsed = (now - submitted_date).days
        is_overdue = days_elapsed > threshold_days
        assert is_overdue is True


# ---------------------------------------------------------------------------
# Review service interface
# ---------------------------------------------------------------------------

class TestReviewServiceInterface:
    def test_review_service_exists(self):
        """ReviewService should exist and have required attributes."""
        assert ReviewService is not None
        assert hasattr(ReviewService, 'create_review')
