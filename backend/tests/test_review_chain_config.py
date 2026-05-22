"""Tests for Phase 6 F8: Review chain configuration + state machine

Tests cover:
- ReviewStateMachine: N-level chain completeness
- review_config API: GET/PUT endpoints
- RBAC and validation
"""

import pytest
from app.models.workpaper_models import WpReviewStatus
from app.services.review_state_machine import ReviewStateMachine


# ---------------------------------------------------------------------------
# ReviewStateMachine unit tests
# ---------------------------------------------------------------------------


class TestReviewStateMachine:
    """Test the configuration-driven review state machine."""

    def test_default_2_levels(self):
        """Default config (null) → 2-level state machine."""
        sm = ReviewStateMachine.from_config(None)
        assert sm.levels == 2

    def test_from_config_3_levels(self):
        """Config with levels=3."""
        sm = ReviewStateMachine.from_config({"levels": 3, "level_roles": {"L1": "manager", "L2": "partner", "L3": "eqcr"}})
        assert sm.levels == 3

    def test_from_config_4_levels(self):
        """Config with levels=4."""
        sm = ReviewStateMachine.from_config({"levels": 4, "level_roles": {"L1": "manager", "L2": "partner", "L3": "eqcr", "L4": "qc"}})
        assert sm.levels == 4

    def test_invalid_levels_raises(self):
        """levels < 2 or > 4 raises ValueError."""
        with pytest.raises(ValueError):
            ReviewStateMachine(levels=1)
        with pytest.raises(ValueError):
            ReviewStateMachine(levels=5)

    @pytest.mark.parametrize("levels", [2, 3, 4])
    def test_full_chain_pass_sequence(self, levels: int):
        """A workpaper requires exactly N sequential pass actions to complete."""
        sm = ReviewStateMachine(levels=levels)

        # Start from not_submitted
        current = WpReviewStatus.not_submitted

        # Submit → pending_level1
        current = sm.submit_for_review(current)
        assert current == WpReviewStatus.pending_level1

        # Walk through each level
        for level in range(1, levels + 1):
            # Pass current level
            passed = sm.pass_current_level(current)
            assert passed is not None
            assert passed.value == f"level{level}_passed"

            # Advance to next level (or complete)
            next_status = sm.advance_after_pass(passed)
            if level < levels:
                assert next_status is not None
                assert next_status.value == f"pending_level{level + 1}"
                current = next_status
            else:
                # Final level → None (complete)
                assert next_status is None
                assert sm.is_review_complete(passed)

    def test_2_level_chain_states(self):
        """2-level chain: not_submitted → pending_l1 → l1_passed → pending_l2 → l2_passed."""
        sm = ReviewStateMachine(levels=2)

        assert sm.pass_current_level(WpReviewStatus.pending_level1) == WpReviewStatus.level1_passed
        assert sm.advance_after_pass(WpReviewStatus.level1_passed) == WpReviewStatus.pending_level2
        assert sm.pass_current_level(WpReviewStatus.pending_level2) == WpReviewStatus.level2_passed
        assert sm.advance_after_pass(WpReviewStatus.level2_passed) is None
        assert sm.is_review_complete(WpReviewStatus.level2_passed)

    def test_3_level_chain_states(self):
        """3-level chain includes level3."""
        sm = ReviewStateMachine(levels=3)

        assert sm.advance_after_pass(WpReviewStatus.level2_passed) == WpReviewStatus.pending_level3
        assert sm.pass_current_level(WpReviewStatus.pending_level3) == WpReviewStatus.level3_passed
        assert sm.advance_after_pass(WpReviewStatus.level3_passed) is None
        assert sm.is_review_complete(WpReviewStatus.level3_passed)
        assert not sm.is_review_complete(WpReviewStatus.level2_passed)

    def test_4_level_chain_states(self):
        """4-level chain includes level4."""
        sm = ReviewStateMachine(levels=4)

        assert sm.advance_after_pass(WpReviewStatus.level3_passed) == WpReviewStatus.pending_level4
        assert sm.pass_current_level(WpReviewStatus.pending_level4) == WpReviewStatus.level4_passed
        assert sm.advance_after_pass(WpReviewStatus.level4_passed) is None
        assert sm.is_review_complete(WpReviewStatus.level4_passed)
        assert not sm.is_review_complete(WpReviewStatus.level3_passed)

    def test_in_progress_status_passes(self):
        """level_in_progress status can also be passed."""
        sm = ReviewStateMachine(levels=2)
        assert sm.pass_current_level(WpReviewStatus.level1_in_progress) == WpReviewStatus.level1_passed
        assert sm.pass_current_level(WpReviewStatus.level2_in_progress) == WpReviewStatus.level2_passed

    def test_rejected_status_returns_none(self):
        """Rejected status cannot advance (needs resubmission)."""
        sm = ReviewStateMachine(levels=2)
        assert sm.pass_current_level(WpReviewStatus.level1_rejected) is None

    def test_get_all_reviewable_statuses_2_levels(self):
        """2-level config has 4 reviewable statuses."""
        sm = ReviewStateMachine(levels=2)
        statuses = sm.get_all_reviewable_statuses()
        assert WpReviewStatus.pending_level1 in statuses
        assert WpReviewStatus.level1_in_progress in statuses
        assert WpReviewStatus.pending_level2 in statuses
        assert WpReviewStatus.level2_in_progress in statuses
        assert len(statuses) == 4

    def test_get_all_reviewable_statuses_4_levels(self):
        """4-level config has 8 reviewable statuses."""
        sm = ReviewStateMachine(levels=4)
        statuses = sm.get_all_reviewable_statuses()
        assert len(statuses) == 8
        assert WpReviewStatus.pending_level3 in statuses
        assert WpReviewStatus.level3_in_progress in statuses
        assert WpReviewStatus.pending_level4 in statuses
        assert WpReviewStatus.level4_in_progress in statuses

    def test_is_review_complete_false_for_intermediate(self):
        """Intermediate passed states are not complete."""
        sm = ReviewStateMachine(levels=4)
        assert not sm.is_review_complete(WpReviewStatus.level1_passed)
        assert not sm.is_review_complete(WpReviewStatus.level2_passed)
        assert not sm.is_review_complete(WpReviewStatus.level3_passed)
        assert sm.is_review_complete(WpReviewStatus.level4_passed)


# ---------------------------------------------------------------------------
# urgency_score calculation tests
# ---------------------------------------------------------------------------


class TestUrgencyScore:
    """Test the urgency_score calculation from manager_dashboard."""

    def test_urgency_score_formula(self):
        """Verify urgency_score = 0.4 * sla + 0.3 * vr + 0.3 * wp."""
        from app.routers.manager_dashboard import _calc_urgency_score

        # All factors at maximum
        score = _calc_urgency_score(
            days_remaining=0,
            blocking_vr_count=10,
            completed_wp=0,
            total_wp=10,
        )
        assert score == pytest.approx(1.0, abs=0.01)

    def test_urgency_score_all_zero(self):
        """All factors at minimum → score = 0."""
        from app.routers.manager_dashboard import _calc_urgency_score

        score = _calc_urgency_score(
            days_remaining=90,
            blocking_vr_count=0,
            completed_wp=10,
            total_wp=10,
        )
        assert score == pytest.approx(0.0, abs=0.01)

    def test_urgency_score_sla_monotonicity(self):
        """Less days remaining → higher score (other factors equal)."""
        from app.routers.manager_dashboard import _calc_urgency_score

        score_30 = _calc_urgency_score(30, 0, 5, 10)
        score_10 = _calc_urgency_score(10, 0, 5, 10)
        score_0 = _calc_urgency_score(0, 0, 5, 10)

        assert score_0 > score_10 > score_30

    def test_urgency_score_vr_monotonicity(self):
        """More blocking VRs → higher score (other factors equal)."""
        from app.routers.manager_dashboard import _calc_urgency_score

        score_0 = _calc_urgency_score(45, 0, 5, 10)
        score_5 = _calc_urgency_score(45, 5, 5, 10)
        score_10 = _calc_urgency_score(45, 10, 5, 10)

        assert score_10 > score_5 > score_0

    def test_urgency_score_wp_monotonicity(self):
        """More incomplete WPs → higher score (other factors equal)."""
        from app.routers.manager_dashboard import _calc_urgency_score

        score_all_done = _calc_urgency_score(45, 3, 10, 10)
        score_half = _calc_urgency_score(45, 3, 5, 10)
        score_none = _calc_urgency_score(45, 3, 0, 10)

        assert score_none > score_half > score_all_done

    def test_urgency_score_vr_cap(self):
        """VR factor caps at 1.0 when blocking_vr_count >= VR_CAP."""
        from app.routers.manager_dashboard import _calc_urgency_score

        score_10 = _calc_urgency_score(45, 10, 5, 10)
        score_20 = _calc_urgency_score(45, 20, 5, 10)

        # Both should be the same (capped)
        assert score_10 == score_20

    def test_urgency_score_zero_total_wp(self):
        """total_wp=0 → wp_factor=0 (no division by zero)."""
        from app.routers.manager_dashboard import _calc_urgency_score

        score = _calc_urgency_score(45, 3, 0, 0)
        # Should not raise, wp_factor = 0
        assert score >= 0


# ---------------------------------------------------------------------------
# batch_review REVIEWABLE_REVIEW_STATUSES tests
# ---------------------------------------------------------------------------


class TestBatchReviewStatuses:
    """Verify batch_review includes level3/level4 statuses."""

    def test_reviewable_statuses_include_level3_level4(self):
        """REVIEWABLE_REVIEW_STATUSES includes level3 and level4."""
        from app.routers.batch_review import REVIEWABLE_REVIEW_STATUSES

        assert WpReviewStatus.pending_level3 in REVIEWABLE_REVIEW_STATUSES
        assert WpReviewStatus.level3_in_progress in REVIEWABLE_REVIEW_STATUSES
        assert WpReviewStatus.pending_level4 in REVIEWABLE_REVIEW_STATUSES
        assert WpReviewStatus.level4_in_progress in REVIEWABLE_REVIEW_STATUSES

    def test_reviewable_statuses_count(self):
        """Should have 8 reviewable statuses (4 levels × 2 states each)."""
        from app.routers.batch_review import REVIEWABLE_REVIEW_STATUSES

        assert len(REVIEWABLE_REVIEW_STATUSES) == 8
