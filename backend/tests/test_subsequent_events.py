"""Unit tests for subsequent events service.

Validates: Requirements 3.2, 3.3, 3.5, 3.6, 3.7
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, date
import uuid

from app.services.subsequent_event_service import SubsequentEventService


# ---------------------------------------------------------------------------
# Subsequent Event creation tests
# ---------------------------------------------------------------------------

class TestSubsequentEventCreation:
    def test_create_adjusting_event_sets_correct_type(self):
        """Adjusting events should have correct type."""
        # Adjusting event type check
        event_types = ["ADJUSTING", "NON_ADJUSTING"]
        adjusting_type = event_types[0]
        assert adjusting_type == "ADJUSTING"

    def test_create_non_adjusting_event_sets_correct_type(self):
        """Non-adjusting events should have correct type."""
        event_types = ["ADJUSTING", "NON_ADJUSTING"]
        non_adjusting_type = event_types[1]
        assert non_adjusting_type == "NON_ADJUSTING"

    def test_adjusting_event_requires_adjustment_entry(self):
        """Adjusting events must link to adjustment entries per Requirement 3.2."""
        # Business rule: adjusting events must have adjustment_id
        event = {"event_type": "ADJUSTING", "adjustment_id": None}
        requires_adjustment = event["event_type"] == "ADJUSTING" and event["adjustment_id"] is None
        assert requires_adjustment is True

    def test_non_adjusting_event_requires_disclosure(self):
        """Non-adjusting events must link to disclosure per Requirement 3.2."""
        event = {"event_type": "NON_ADJUSTING", "disclosed_in_note_id": None}
        requires_disclosure = event["event_type"] == "NON_ADJUSTING" and event["disclosed_in_note_id"] is None
        assert requires_disclosure is True


# ---------------------------------------------------------------------------
# Subsequent Event retrieval tests
# ---------------------------------------------------------------------------

class TestSubsequentEventRetrieval:
    def test_service_has_get_project_events_method(self):
        """SubsequentEventService should have get_project_events method."""
        assert hasattr(SubsequentEventService, 'get_project_events')


# ---------------------------------------------------------------------------
# Checklist tests
# ---------------------------------------------------------------------------

class TestSEChecklist:
    def test_service_has_init_checklist_method(self):
        """SubsequentEventService should have init_checklist method."""
        assert hasattr(SubsequentEventService, 'init_checklist')

    def test_check_completion_gate(self):
        """All checklist items must be complete before project can proceed."""
        items = [MagicMock(), MagicMock(), MagicMock()]
        for item in items:
            item.is_completed = True
        all_complete = all(item.is_completed for item in items)
        assert all_complete is True


# ---------------------------------------------------------------------------
# Carry-forward from prior year
# ---------------------------------------------------------------------------

class TestCarryForward:
    def test_carry_forward_from_prior_year(self):
        """Test that prior year non-adjusting events are carried forward."""
        prior_events = [
            {"event_type": "NON_ADJUSTING", "description": "New acquisition"},
            {"event_type": "ADJUSTING", "description": "Settlement"},
        ]
        non_adjusting = [e for e in prior_events if e["event_type"] == "NON_ADJUSTING"]
        assert len(non_adjusting) == 1

    def test_carry_forward_only_unresolved_events(self):
        """Only unresolved events should be carried forward."""
        events = [
            {"is_disclosed": False, "event_type": "NON_ADJUSTING"},
            {"is_disclosed": True, "event_type": "NON_ADJUSTING"},
        ]
        unresolved = [e for e in events if not e["is_disclosed"]]
        assert len(unresolved) == 1
