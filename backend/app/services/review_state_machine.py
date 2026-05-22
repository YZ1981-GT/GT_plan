"""配置驱动的复核状态机

Phase 6 F8: 复核层级灵活化（2-4 级可配置）

状态流转公式:
  not_submitted → pending_level1 → level1_passed → pending_level2 → ... → levelN_passed
  最终层级 pass = 复核完成

ADR-5: 状态机根据 project.review_config.levels 动态决定"下一状态"
"""

from __future__ import annotations

from app.models.workpaper_models import WpReviewStatus


# Default config when review_config is null
DEFAULT_LEVELS = 2


class ReviewStateMachine:
    """配置驱动的复核状态机

    根据 project.review_config.levels 动态决定下一状态。
    review_config=null → 默认 2 级（等价当前行为）。
    """

    def __init__(self, levels: int = DEFAULT_LEVELS):
        """Initialize with the number of review levels (2, 3, or 4)."""
        if levels < 2 or levels > 4:
            raise ValueError(f"levels must be between 2 and 4, got {levels}")
        self.levels = levels

    @classmethod
    def from_config(cls, review_config: dict | None) -> "ReviewStateMachine":
        """Create a state machine from a project's review_config JSONB."""
        if review_config is None:
            return cls(levels=DEFAULT_LEVELS)
        return cls(levels=review_config.get("levels", DEFAULT_LEVELS))

    def get_next_status(self, current_status: WpReviewStatus) -> WpReviewStatus | None:
        """Get the next status after a 'pass' action.

        Returns None if the current status is already the final state (levelN_passed).
        Returns the next pending_level status if there are more levels.

        State flow:
          not_submitted → pending_level1
          pending_levelN / levelN_in_progress → levelN_passed (on pass)
          levelN_passed → pending_level{N+1} (if N < levels)
          levelN_passed → None (if N == levels, review complete)
        """
        # not_submitted → pending_level1
        if current_status == WpReviewStatus.not_submitted:
            return WpReviewStatus.pending_level1

        # levelN_passed → pending_level{N+1} or COMPLETED
        level = self._extract_level(current_status)
        if level is None:
            return None

        status_name = current_status.value

        # If current is pending_levelN or levelN_in_progress → levelN_passed (pass action)
        if "pending_level" in status_name or "in_progress" in status_name:
            return self._get_passed_status(level)

        # If current is levelN_passed → next level or complete
        if "passed" in status_name:
            if level < self.levels:
                return self._get_pending_status(level + 1)
            # Final level passed = review complete
            return None

        # If current is levelN_rejected → stays (needs resubmission)
        if "rejected" in status_name:
            return None

        return None

    def submit_for_review(self, current_status: WpReviewStatus) -> WpReviewStatus:
        """Submit a workpaper for review (from not_submitted or after rejection).

        Returns pending_level1.
        """
        return WpReviewStatus.pending_level1

    def pass_current_level(self, current_status: WpReviewStatus) -> WpReviewStatus | None:
        """Pass the current review level.

        Returns the passed status for the current level.
        If already at final level passed, returns None.
        """
        level = self._extract_level(current_status)
        if level is None:
            return None

        status_name = current_status.value

        # Can only pass from pending or in_progress
        if "pending_level" in status_name or "in_progress" in status_name:
            return self._get_passed_status(level)

        return None

    def advance_after_pass(self, current_status: WpReviewStatus) -> WpReviewStatus | None:
        """After a level is passed, advance to the next level's pending state.

        Returns None if this was the final level (review complete).
        """
        level = self._extract_level(current_status)
        if level is None:
            return None

        if "passed" not in current_status.value:
            return None

        if level < self.levels:
            return self._get_pending_status(level + 1)

        # Final level passed = review complete
        return None

    def is_review_complete(self, current_status: WpReviewStatus) -> bool:
        """Check if the review is complete (final level passed)."""
        level = self._extract_level(current_status)
        if level is None:
            return False
        return "passed" in current_status.value and level == self.levels

    def get_all_reviewable_statuses(self) -> set[WpReviewStatus]:
        """Get all statuses that allow a review pass action for this config."""
        statuses = set()
        for level in range(1, self.levels + 1):
            statuses.add(self._get_pending_status(level))
            statuses.add(self._get_in_progress_status(level))
        return statuses

    # ─── Private helpers ───

    def _extract_level(self, status: WpReviewStatus) -> int | None:
        """Extract the level number from a status enum value."""
        name = status.value
        for i in range(1, 5):
            if f"level{i}" in name:
                return i
        return None

    def _get_pending_status(self, level: int) -> WpReviewStatus:
        """Get the pending_levelN status."""
        return WpReviewStatus(f"pending_level{level}")

    def _get_in_progress_status(self, level: int) -> WpReviewStatus:
        """Get the levelN_in_progress status."""
        return WpReviewStatus(f"level{level}_in_progress")

    def _get_passed_status(self, level: int) -> WpReviewStatus:
        """Get the levelN_passed status."""
        return WpReviewStatus(f"level{level}_passed")

    def _get_rejected_status(self, level: int) -> WpReviewStatus:
        """Get the levelN_rejected status."""
        return WpReviewStatus(f"level{level}_rejected")
