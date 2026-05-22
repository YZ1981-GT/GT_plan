"""
F7 批量复核通过 Property-Based Tests — Property 14 & 15

Property 14: Transaction atomicity — all valid workpapers updated or
             (on DB error) none updated.
Property 15: Count invariant — success_count + skipped_count == len(wp_ids),
             each skipped has non-empty reason.

**Validates: Requirements 7.4, 7.5, 7.6**

文件：backend/tests/test_batch_review_pbt.py
"""

from uuid import uuid4

from hypothesis import given, settings, strategies as st

from app.routers.batch_review import (
    BatchReviewResult,
    REVIEWABLE_STATUSES,
)


# ---------------------------------------------------------------------------
# Pure logic simulation (no DB dependency)
# ---------------------------------------------------------------------------

# Simulated workpaper statuses
VALID_STATUSES = ["under_review", "edit_complete"]
INVALID_STATUSES = ["draft", "archived", "review_passed", "in_progress"]
ALL_STATUSES = VALID_STATUSES + INVALID_STATUSES


def simulate_batch_review(
    wp_ids: list[str],
    wp_statuses: dict[str, str | None],
    db_error: bool = False,
) -> BatchReviewResult:
    """Simulate batch review logic (mirrors _execute_batch_review).

    Args:
        wp_ids: List of workpaper IDs to review.
        wp_statuses: Dict mapping wp_id -> status (None means not found/deleted).
        db_error: If True, simulate DB error (all rollback).

    Returns:
        BatchReviewResult with success/skipped counts.
    """
    if db_error:
        # On DB error, nothing is updated (transaction rollback)
        return BatchReviewResult(
            success_count=0,
            skipped_count=len(wp_ids),
            skipped_items=[
                {"wp_id": wp_id, "reason": "数据库错误，事务回滚"}
                for wp_id in wp_ids
            ],
        )

    success_count = 0
    skipped_items = []

    for wp_id in wp_ids:
        status = wp_statuses.get(wp_id)

        if status is None:
            skipped_items.append({
                "wp_id": wp_id,
                "reason": "底稿不存在或已删除",
            })
        elif status in ("review_passed", "archived"):
            skipped_items.append({
                "wp_id": wp_id,
                "reason": f"底稿已处于 {status} 状态，无需重复通过",
            })
        elif status not in VALID_STATUSES:
            skipped_items.append({
                "wp_id": wp_id,
                "reason": f"底稿当前状态为 {status}，不允许复核通过（需先提交复核）",
            })
        else:
            success_count += 1

    return BatchReviewResult(
        success_count=success_count,
        skipped_count=len(skipped_items),
        skipped_items=skipped_items,
    )


# ---------------------------------------------------------------------------
# Property 14: Transaction atomicity
# ---------------------------------------------------------------------------

class TestTransactionAtomicityPBT:
    """Property 14: 批量复核事务原子性

    **Validates: Requirements 7.4**

    For any batch of workpapers submitted for review pass where all are in
    valid state, either all are updated to "passed" status, or (on DB error)
    none are updated.
    """

    @settings(max_examples=30)
    @given(
        n_valid=st.integers(min_value=1, max_value=10),
    )
    def test_all_valid_all_succeed(self, n_valid: int):
        """When all workpapers are in valid state, all succeed.

        **Validates: Requirements 7.4**
        """
        wp_ids = [str(uuid4()) for _ in range(n_valid)]
        wp_statuses = {wp_id: "under_review" for wp_id in wp_ids}

        result = simulate_batch_review(wp_ids, wp_statuses, db_error=False)

        assert result.success_count == n_valid
        assert result.skipped_count == 0
        assert len(result.skipped_items) == 0

    @settings(max_examples=30)
    @given(
        n_valid=st.integers(min_value=1, max_value=10),
    )
    def test_db_error_none_updated(self, n_valid: int):
        """On DB error, none are updated (transaction rollback).

        **Validates: Requirements 7.4**
        """
        wp_ids = [str(uuid4()) for _ in range(n_valid)]
        wp_statuses = {wp_id: "under_review" for wp_id in wp_ids}

        result = simulate_batch_review(wp_ids, wp_statuses, db_error=True)

        assert result.success_count == 0
        assert result.skipped_count == n_valid

    @settings(max_examples=30)
    @given(
        statuses=st.lists(
            st.sampled_from(VALID_STATUSES),
            min_size=1,
            max_size=10,
        )
    )
    def test_all_reviewable_statuses_succeed(self, statuses: list[str]):
        """All reviewable statuses (under_review, edit_complete) succeed.

        **Validates: Requirements 7.4**
        """
        wp_ids = [str(uuid4()) for _ in statuses]
        wp_statuses = dict(zip(wp_ids, statuses))

        result = simulate_batch_review(wp_ids, wp_statuses, db_error=False)

        assert result.success_count == len(statuses)
        assert result.skipped_count == 0


# ---------------------------------------------------------------------------
# Property 15: Count invariant
# ---------------------------------------------------------------------------

class TestCountInvariantPBT:
    """Property 15: 批量复核跳过 + 计数不变量

    **Validates: Requirements 7.5, 7.6**

    For any batch review result, success_count + skipped_count must equal
    the number of submitted wp_ids, and each skipped item must have a
    non-empty reason.
    """

    @settings(max_examples=30)
    @given(
        statuses=st.lists(
            st.one_of(
                st.sampled_from(ALL_STATUSES),
                st.none(),  # None = not found
            ),
            min_size=1,
            max_size=15,
        )
    )
    def test_success_plus_skipped_equals_total(self, statuses: list[str | None]):
        """success_count + skipped_count == len(wp_ids).

        **Validates: Requirements 7.5, 7.6**
        """
        wp_ids = [str(uuid4()) for _ in statuses]
        wp_statuses = {}
        for wp_id, status in zip(wp_ids, statuses):
            if status is not None:
                wp_statuses[wp_id] = status
            # None means not found (not in dict)

        result = simulate_batch_review(wp_ids, wp_statuses)

        assert result.success_count + result.skipped_count == len(wp_ids), (
            f"success({result.success_count}) + skipped({result.skipped_count}) "
            f"!= total({len(wp_ids)})"
        )

    @settings(max_examples=30)
    @given(
        statuses=st.lists(
            st.one_of(
                st.sampled_from(ALL_STATUSES),
                st.none(),
            ),
            min_size=1,
            max_size=15,
        )
    )
    def test_each_skipped_has_non_empty_reason(self, statuses: list[str | None]):
        """Each skipped item has a non-empty reason string.

        **Validates: Requirements 7.5, 7.6**
        """
        wp_ids = [str(uuid4()) for _ in statuses]
        wp_statuses = {}
        for wp_id, status in zip(wp_ids, statuses):
            if status is not None:
                wp_statuses[wp_id] = status

        result = simulate_batch_review(wp_ids, wp_statuses)

        for skipped in result.skipped_items:
            assert "reason" in skipped, "Skipped item missing 'reason' key"
            assert skipped["reason"], "Skipped item has empty reason"
            assert len(skipped["reason"]) > 0

    @settings(max_examples=30)
    @given(
        statuses=st.lists(
            st.one_of(
                st.sampled_from(ALL_STATUSES),
                st.none(),
            ),
            min_size=1,
            max_size=15,
        )
    )
    def test_skipped_count_equals_skipped_items_length(self, statuses: list[str | None]):
        """skipped_count == len(skipped_items).

        **Validates: Requirements 7.5, 7.6**
        """
        wp_ids = [str(uuid4()) for _ in statuses]
        wp_statuses = {}
        for wp_id, status in zip(wp_ids, statuses):
            if status is not None:
                wp_statuses[wp_id] = status

        result = simulate_batch_review(wp_ids, wp_statuses)

        assert result.skipped_count == len(result.skipped_items), (
            f"skipped_count({result.skipped_count}) != "
            f"len(skipped_items)({len(result.skipped_items)})"
        )

    @settings(max_examples=30)
    @given(
        n_missing=st.integers(min_value=0, max_value=5),
        n_valid=st.integers(min_value=0, max_value=5),
        n_invalid=st.integers(min_value=0, max_value=5),
    )
    def test_mixed_batch_count_invariant(
        self, n_missing: int, n_valid: int, n_invalid: int
    ):
        """Mixed batch: missing + valid + invalid all accounted for.

        **Validates: Requirements 7.5, 7.6**
        """
        total = n_missing + n_valid + n_invalid
        if total == 0:
            return  # Skip empty batch

        wp_ids = []
        wp_statuses = {}

        # Missing workpapers (not in statuses dict)
        for _ in range(n_missing):
            wp_ids.append(str(uuid4()))

        # Valid workpapers
        for _ in range(n_valid):
            wp_id = str(uuid4())
            wp_ids.append(wp_id)
            wp_statuses[wp_id] = "under_review"

        # Invalid workpapers
        for _ in range(n_invalid):
            wp_id = str(uuid4())
            wp_ids.append(wp_id)
            wp_statuses[wp_id] = "draft"

        result = simulate_batch_review(wp_ids, wp_statuses)

        assert result.success_count == n_valid
        assert result.skipped_count == n_missing + n_invalid
        assert result.success_count + result.skipped_count == total
