"""Property test for review state machine N-level chain (P6)

**Validates: Requirements F8.5, F8.6, F8.7**

Property 6: levels=N → submit then N sequential passes → completed.
Test N ∈ {2, 3, 4}.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.workpaper_models import WpReviewStatus
from app.services.review_state_machine import ReviewStateMachine


class TestReviewChainNLevelProperty:
    """Property 6: N-level chain completeness."""

    @settings(max_examples=10)
    @given(levels=st.sampled_from([2, 3, 4]))
    def test_p6_n_passes_reach_completed(self, levels: int):
        """levels=N → submit then exactly N sequential passes → completed."""
        sm = ReviewStateMachine(levels=levels)

        # Start: not_submitted → submit → pending_level1
        current = sm.submit_for_review(WpReviewStatus.not_submitted)
        assert current == WpReviewStatus.pending_level1

        # Walk through N levels
        pass_count = 0
        for level in range(1, levels + 1):
            # Pass current level
            passed = sm.pass_current_level(current)
            assert passed is not None, f"Failed to pass level {level}"
            assert passed.value == f"level{level}_passed"
            pass_count += 1

            # Advance to next level or complete
            next_status = sm.advance_after_pass(passed)
            if level < levels:
                assert next_status is not None
                assert next_status.value == f"pending_level{level + 1}"
                current = next_status
            else:
                assert next_status is None  # review complete
                assert sm.is_review_complete(passed)

        assert pass_count == levels

    @settings(max_examples=10)
    @given(levels=st.sampled_from([2, 3, 4]))
    def test_p6_intermediate_not_complete(self, levels: int):
        """Intermediate level passes are NOT complete (only final level is)."""
        sm = ReviewStateMachine(levels=levels)

        for level in range(1, levels):
            passed_status = WpReviewStatus(f"level{level}_passed")
            assert not sm.is_review_complete(passed_status)

        # Only final level is complete
        final = WpReviewStatus(f"level{levels}_passed")
        assert sm.is_review_complete(final)

    @settings(max_examples=10)
    @given(levels=st.sampled_from([2, 3, 4]))
    def test_p6_reviewable_statuses_count(self, levels: int):
        """N-level config has exactly 2*N reviewable statuses."""
        sm = ReviewStateMachine(levels=levels)
        statuses = sm.get_all_reviewable_statuses()
        assert len(statuses) == 2 * levels
