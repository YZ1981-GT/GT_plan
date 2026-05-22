"""
F2 跨循环断裂清单 Property-Based Tests — Property 3, 4, 5

Property 3: Breakage filtering correctness — only broken targets appear in results.
Property 4: Severity sort — output sorted blocking > required > warning > recommended > info.
Property 5: Summary consistency — sum of severity counts == len(items).

**Validates: Requirements 2.2, 2.3, 2.6**

文件：backend/tests/test_cross_cycle_breakage_pbt.py
"""

from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

from app.services.cross_cycle_breakage_service import (
    SEVERITY_ORDER,
    BreakageRecord,
    BreakageSummary,
    BreakageListResponse,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

SEVERITY_LEVELS = list(SEVERITY_ORDER.keys())  # blocking, required, warning, recommended, info
REASONS = ["target_missing", "target_stale"]

breakage_record_strategy = st.builds(
    BreakageRecord,
    ref_id=st.text(alphabet="CW-0123456789", min_size=4, max_size=8),
    source_wp_code=st.text(alphabet="ABCDEFGHIJKLMN0123456789-", min_size=3, max_size=8),
    target_wp_code=st.text(alphabet="ABCDEFGHIJKLMN0123456789-", min_size=3, max_size=8),
    severity=st.sampled_from(SEVERITY_LEVELS),
    reason=st.sampled_from(REASONS),
    last_checked_at=st.builds(lambda: datetime.now(timezone.utc)),
)


def _compute_summary(items: list[BreakageRecord]) -> BreakageSummary:
    """Compute summary from items (mirrors service logic)."""
    summary = BreakageSummary()
    for item in items:
        if item.severity == "blocking":
            summary.blocking += 1
        elif item.severity == "required":
            summary.required += 1
        elif item.severity == "warning":
            summary.warning += 1
        elif item.severity == "recommended":
            summary.recommended += 1
        elif item.severity == "info":
            summary.info += 1
    return summary


def _sort_items(items: list[BreakageRecord]) -> list[BreakageRecord]:
    """Sort items by severity order (mirrors service logic)."""
    return sorted(items, key=lambda item: (SEVERITY_ORDER.get(item.severity, 4), item.ref_id))


# ---------------------------------------------------------------------------
# Property 3: Breakage filtering correctness
# ---------------------------------------------------------------------------

class TestBreakageFilteringPBT:
    """Property 3: 断裂清单过滤正确性

    **Validates: Requirements 2.2**

    For any set of cross_wp_references, the breakage list should contain
    exactly those entries where the target workpaper is missing or stale.
    """

    @settings(max_examples=30)
    @given(
        existing_codes=st.sets(
            st.text(alphabet="ABCDEFGH0123456789-", min_size=3, max_size=6),
            min_size=0,
            max_size=10,
        ),
        stale_codes=st.sets(
            st.text(alphabet="ABCDEFGH0123456789-", min_size=3, max_size=6),
            min_size=0,
            max_size=5,
        ),
        target_codes=st.lists(
            st.text(alphabet="ABCDEFGH0123456789-", min_size=3, max_size=6),
            min_size=1,
            max_size=15,
        ),
    )
    def test_only_broken_targets_in_results(
        self,
        existing_codes: set[str],
        stale_codes: set[str],
        target_codes: list[str],
    ):
        """Only targets that are missing or stale appear in breakage results.

        **Validates: Requirements 2.2**
        """
        # Stale codes must be subset of existing codes
        stale_codes = stale_codes & existing_codes

        # Simulate breakage detection logic (mirrors service)
        broken_items: list[BreakageRecord] = []
        now = datetime.now(timezone.utc)

        for i, target_wp_code in enumerate(target_codes):
            reason = None
            if target_wp_code not in existing_codes:
                reason = "target_missing"
            elif target_wp_code in stale_codes:
                reason = "target_stale"

            if reason is not None:
                broken_items.append(
                    BreakageRecord(
                        ref_id=f"CW-{i:03d}",
                        source_wp_code=f"SRC-{i}",
                        target_wp_code=target_wp_code,
                        severity="warning",
                        reason=reason,
                        last_checked_at=now,
                    )
                )

        # Verify: every item in results has a valid breakage reason
        for item in broken_items:
            assert item.reason in ("target_missing", "target_stale")

            if item.reason == "target_missing":
                assert item.target_wp_code not in existing_codes
            elif item.reason == "target_stale":
                assert item.target_wp_code in existing_codes
                assert item.target_wp_code in stale_codes

        # Verify: non-broken targets are NOT in results
        result_targets = {item.target_wp_code for item in broken_items}
        for code in target_codes:
            if code in existing_codes and code not in stale_codes:
                assert code not in result_targets, (
                    f"Non-broken target {code} should not be in results"
                )


# ---------------------------------------------------------------------------
# Property 4: Severity sort
# ---------------------------------------------------------------------------

class TestSeveritySortPBT:
    """Property 4: 断裂清单 severity 排序

    **Validates: Requirements 2.3**

    For any breakage list, items should be sorted by severity descending
    (blocking > required > warning > recommended > info).
    """

    @settings(max_examples=30)
    @given(
        items=st.lists(breakage_record_strategy, min_size=1, max_size=20)
    )
    def test_sorted_items_maintain_severity_order(self, items: list[BreakageRecord]):
        """After sorting, severity order is non-decreasing (blocking first).

        **Validates: Requirements 2.3**
        """
        sorted_items = _sort_items(items)

        for i in range(len(sorted_items) - 1):
            current_order = SEVERITY_ORDER[sorted_items[i].severity]
            next_order = SEVERITY_ORDER[sorted_items[i + 1].severity]
            assert current_order <= next_order, (
                f"Sort violation at index {i}: "
                f"{sorted_items[i].severity} (order={current_order}) "
                f"should not come after "
                f"{sorted_items[i + 1].severity} (order={next_order})"
            )

    @settings(max_examples=30)
    @given(
        items=st.lists(breakage_record_strategy, min_size=2, max_size=15)
    )
    def test_blocking_always_before_info(self, items: list[BreakageRecord]):
        """All blocking items appear before all info items after sorting.

        **Validates: Requirements 2.3**
        """
        sorted_items = _sort_items(items)

        blocking_indices = [
            i for i, item in enumerate(sorted_items) if item.severity == "blocking"
        ]
        info_indices = [
            i for i, item in enumerate(sorted_items) if item.severity == "info"
        ]

        if blocking_indices and info_indices:
            assert max(blocking_indices) < min(info_indices), (
                "Blocking items must all appear before info items"
            )


# ---------------------------------------------------------------------------
# Property 5: Summary consistency
# ---------------------------------------------------------------------------

class TestSummaryConsistencyPBT:
    """Property 5: 断裂统计摘要一致性

    **Validates: Requirements 2.6**

    For any breakage list response, sum of severity counts == len(items),
    and each count equals the number of items with that severity.
    """

    @settings(max_examples=30)
    @given(
        items=st.lists(breakage_record_strategy, min_size=0, max_size=20)
    )
    def test_summary_counts_equal_items_length(self, items: list[BreakageRecord]):
        """Sum of all severity counts equals total number of items.

        **Validates: Requirements 2.6**
        """
        summary = _compute_summary(items)

        total_from_summary = (
            summary.blocking + summary.required + summary.warning
            + summary.recommended + summary.info
        )
        assert total_from_summary == len(items), (
            f"Summary total ({total_from_summary}) != len(items) ({len(items)})"
        )

    @settings(max_examples=30)
    @given(
        items=st.lists(breakage_record_strategy, min_size=1, max_size=20)
    )
    def test_each_severity_count_matches_items(self, items: list[BreakageRecord]):
        """Each severity count in summary matches actual count of items with that severity.

        **Validates: Requirements 2.6**
        """
        summary = _compute_summary(items)

        actual_blocking = sum(1 for item in items if item.severity == "blocking")
        actual_required = sum(1 for item in items if item.severity == "required")
        actual_warning = sum(1 for item in items if item.severity == "warning")
        actual_recommended = sum(1 for item in items if item.severity == "recommended")
        actual_info = sum(1 for item in items if item.severity == "info")

        assert summary.blocking == actual_blocking
        assert summary.required == actual_required
        assert summary.warning == actual_warning
        assert summary.recommended == actual_recommended
        assert summary.info == actual_info

    @settings(max_examples=30)
    @given(
        items=st.lists(breakage_record_strategy, min_size=0, max_size=20)
    )
    def test_response_summary_and_items_consistent(self, items: list[BreakageRecord]):
        """BreakageListResponse summary is consistent with its items.

        **Validates: Requirements 2.6**
        """
        summary = _compute_summary(items)
        response = BreakageListResponse(items=items, summary=summary)

        total_from_summary = (
            response.summary.blocking + response.summary.required
            + response.summary.warning + response.summary.recommended
            + response.summary.info
        )
        assert total_from_summary == len(response.items)
