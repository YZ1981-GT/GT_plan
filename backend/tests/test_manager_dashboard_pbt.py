"""Property test for urgency_score monotonicity (P5)

**Validates: Requirements F7.3, F7.4**

Property 5: SLA days less → score higher (other factors equal);
same for VR and WP factors.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.routers.manager_dashboard import _calc_urgency_score, MAX_SLA_DAYS, VR_CAP


class TestUrgencyScoreMonotonicity:
    """Property 5: urgency_score monotonicity."""

    @settings(max_examples=30)
    @given(
        days_a=st.floats(min_value=0, max_value=90),
        days_b=st.floats(min_value=0, max_value=90),
        vr=st.integers(min_value=0, max_value=10),
        completed=st.integers(min_value=0, max_value=50),
        total=st.integers(min_value=1, max_value=50),
    )
    def test_p5_sla_monotonicity(self, days_a, days_b, vr, completed, total):
        """Less SLA days remaining → higher score (other factors equal)."""
        assume(days_a < days_b)
        assume(completed <= total)
        # Ensure meaningful difference (avoid float precision issues)
        assume(days_b - days_a > 0.1)

        score_a = _calc_urgency_score(days_a, vr, completed, total)
        score_b = _calc_urgency_score(days_b, vr, completed, total)

        assert score_a >= score_b  # fewer days = higher urgency

    @settings(max_examples=30)
    @given(
        days=st.floats(min_value=0, max_value=90),
        vr_low=st.integers(min_value=0, max_value=4),
        vr_high=st.integers(min_value=5, max_value=VR_CAP),
        completed=st.integers(min_value=0, max_value=50),
        total=st.integers(min_value=1, max_value=50),
    )
    def test_p5_vr_monotonicity(self, days, vr_low, vr_high, completed, total):
        """More blocking VRs → higher score (other factors equal)."""
        assume(completed <= total)

        score_high = _calc_urgency_score(days, vr_high, completed, total)
        score_low = _calc_urgency_score(days, vr_low, completed, total)

        assert score_high >= score_low  # more VRs = higher urgency

    @settings(max_examples=30)
    @given(
        days=st.floats(min_value=0, max_value=90),
        vr=st.integers(min_value=0, max_value=10),
        completed_low=st.integers(min_value=0, max_value=24),
        completed_high=st.integers(min_value=25, max_value=50),
        total=st.integers(min_value=50, max_value=50),
    )
    def test_p5_wp_monotonicity(self, days, vr, completed_low, completed_high, total):
        """More incomplete WPs → higher score (other factors equal)."""
        score_low = _calc_urgency_score(days, vr, completed_low, total)
        score_high = _calc_urgency_score(days, vr, completed_high, total)

        assert score_low >= score_high  # fewer completed = higher urgency
