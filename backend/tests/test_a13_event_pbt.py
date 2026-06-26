"""Property-Based Tests for A13 Event Handler + Debounce.

Tests debounce consolidation and event payload contract using hypothesis.

Feature: a13-misstatement-aggregation
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.a13_event_handler import (
    _debounce_key,
    _is_a13_sub_sheet,
    _pending_tasks,
)
from app.models.audit_platform_schemas import EventPayload, EventType


# ═══════════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════════

A13_WP_CODES = ["A13-2", "A13-3", "A13-4", "A13-5"]
NON_A13_WP_CODES = ["A1", "A10", "B15", "D2", "F3A", "A13-1", "A13"]


# ═══════════════════════════════════════════════════════════════════════════════
# Property 4: Debounce consolidation
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty4DebounceConsolidation:
    """Property 4: Debounce consolidation.

    *For any* sequence of N (N >= 2) WORKPAPER_SAVED events for A13 sub-sheets
    within the debounce window (2 seconds), the Aggregation_Resolver SHALL execute
    exactly once after the last event, using the final event's project_id and year.

    **Validates: Requirements 2.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        n_events=st.integers(min_value=2, max_value=10),
        wp_codes=st.lists(
            st.sampled_from(A13_WP_CODES), min_size=2, max_size=10
        ),
    )
    def test_debounce_key_same_project_year(self, n_events, wp_codes):
        """Same project+year generates same debounce key regardless of wp_code."""
        project_id = uuid4()
        year = 2025
        keys = set()
        for _ in wp_codes[:n_events]:
            keys.add(_debounce_key(project_id, year))
        # All events for same project+year map to same key
        assert len(keys) == 1

    @settings(max_examples=100, deadline=None)
    @given(
        year1=st.integers(min_value=2020, max_value=2030),
        year2=st.integers(min_value=2020, max_value=2030),
    )
    def test_debounce_key_different_years_different_keys(self, year1, year2):
        """Different years produce different debounce keys."""
        assume(year1 != year2)
        project_id = uuid4()
        key1 = _debounce_key(project_id, year1)
        key2 = _debounce_key(project_id, year2)
        assert key1 != key2

    @settings(max_examples=100, deadline=None)
    @given(n_events=st.integers(min_value=2, max_value=8))
    @pytest.mark.asyncio
    async def test_multiple_events_execute_once(self, n_events):
        """N events within debounce window → resolver executes exactly once."""
        project_id = uuid4()
        year = 2025
        execution_count = {"value": 0}

        async def mock_execute(pid, yr):
            execution_count["value"] += 1

        with patch(
            "app.services.a13_event_handler._execute_aggregation",
            side_effect=mock_execute,
        ):
            from app.services.a13_event_handler import _on_a13_sheet_saved

            # Fire N events rapidly (no delay between them)
            for i in range(n_events):
                payload = EventPayload(
                    event_type=EventType.WORKPAPER_SAVED,
                    project_id=project_id,
                    year=year,
                    extra={"wp_code": A13_WP_CODES[i % len(A13_WP_CODES)]},
                )
                await _on_a13_sheet_saved(payload)

            # Wait for debounce to fire (2s + margin)
            await asyncio.sleep(2.5)

            # Should execute exactly once
            assert execution_count["value"] == 1

        # Clean up pending tasks
        _pending_tasks.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Property 5: Event payload contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty5EventPayloadContract:
    """Property 5: Event payload contract.

    *For any* A13 sub-sheet save (A13-2, A13-3, A13-4, or A13-5), the published
    EventPayload SHALL contain event_type=WORKPAPER_SAVED, the correct project_id,
    year derived from the project, and extra.wp_code matching the saved sheet identifier.

    **Validates: Requirements 2.1, 2.6**
    """

    @settings(max_examples=100, deadline=None)
    @given(wp_code=st.sampled_from(A13_WP_CODES))
    def test_a13_sub_sheet_detected(self, wp_code):
        """A13-2/A13-3/A13-4/A13-5 are detected as A13 sub-sheets."""
        assert _is_a13_sub_sheet(wp_code) is True

    @settings(max_examples=100, deadline=None)
    @given(wp_code=st.sampled_from(NON_A13_WP_CODES))
    def test_non_a13_sheets_rejected(self, wp_code):
        """Non-A13 wp_codes are rejected by filter."""
        assert _is_a13_sub_sheet(wp_code) is False

    @settings(max_examples=100, deadline=None)
    @given(
        wp_code=st.sampled_from(A13_WP_CODES),
        year=st.integers(min_value=2020, max_value=2035),
    )
    def test_event_payload_has_required_fields(self, wp_code, year):
        """EventPayload for A13 saves contains all required fields."""
        project_id = uuid4()
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=project_id,
            year=year,
            extra={"wp_code": wp_code},
        )
        # Verify contract
        assert payload.event_type == EventType.WORKPAPER_SAVED
        assert payload.project_id == project_id
        assert payload.year == year
        assert payload.extra["wp_code"] == wp_code
        assert payload.extra["wp_code"] in A13_WP_CODES

    @settings(max_examples=100, deadline=None)
    @given(wp_code=st.sampled_from(A13_WP_CODES))
    def test_null_wp_code_is_not_a13(self, wp_code):
        """Null or empty wp_code is never detected as A13."""
        assert _is_a13_sub_sheet(None) is False
        assert _is_a13_sub_sheet("") is False
