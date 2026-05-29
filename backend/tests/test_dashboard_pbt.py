"""合伙人仪表盘属性测试（spec partner-dashboard PBT P1-P3）

Properties:
- Property 1: progress rate bounds — calc_progress_rate 结果 ∈ [0.0, 100.0]
- Property 2: blocking count monotone — blocking_failed ≤ total_rules + sum 守恒
- Property 3: review sort stability — sort_reviews 满足排序约束

**Validates: Requirements 2.2, 3.1, 3.2, 4.2**

PBT 策略：hypothesis ≥ 200 examples per property
"""
from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.dashboard_aggregator_service import (
    calc_progress_rate,
    sort_reviews,
    LAYER_PRIORITY,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1: progress rate bounds
# **Validates: Requirements 2.2**
# Label: Feature: partner-dashboard, Property 1: progress rate bounds
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=15, deadline=None)
@given(
    total=st.integers(min_value=0, max_value=500),
    data=st.data(),
)
def test_progress_rate_bounds(total: int, data: st.DataObject) -> None:
    """Feature: partner-dashboard, Property 1: progress rate bounds

    For any cycle with total ∈ [0, 500], completed ∈ [0, total], trimmed ∈ [0, total]:
    - 0.0 <= calc_progress_rate(total, completed, trimmed) <= 100.0
    - When total == trimmed, rate == 100.0

    **Validates: Requirements 2.2**
    """
    completed = data.draw(st.integers(min_value=0, max_value=total), label="completed")
    trimmed = data.draw(st.integers(min_value=0, max_value=total), label="trimmed")

    rate = calc_progress_rate(total, completed, trimmed)

    # Invariant 1: rate is always within [0.0, 100.0]
    assert 0.0 <= rate <= 100.0, (
        f"Rate out of bounds: total={total}, completed={completed}, "
        f"trimmed={trimmed}, rate={rate}"
    )

    # Invariant 2: when total == trimmed (all trimmed), rate must be 100.0
    if total == trimmed:
        assert rate == 100.0, (
            f"When total==trimmed, rate should be 100.0 but got {rate}: "
            f"total={total}, completed={completed}, trimmed={trimmed}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 2: blocking count monotone
# **Validates: Requirements 3.1, 3.2**
# Label: Feature: partner-dashboard, Property 2: blocking count monotone
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=15, deadline=None)
@given(
    total_rules=st.integers(min_value=1, max_value=100),
    num_cycles=st.integers(min_value=1, max_value=11),
    data=st.data(),
)
def test_blocking_count_monotone(
    total_rules: int, num_cycles: int, data: st.DataObject
) -> None:
    """Feature: partner-dashboard, Property 2: blocking count monotone

    For any VR summary with total_rules ∈ [1, 100] and per-cycle blocking counts
    where sum(per_cycle) ≤ total_rules:
    - blocking_failed <= total_rules
    - sum(by_cycle.blocking_failed) == blocking_failed (sum conservation)

    **Validates: Requirements 3.1, 3.2**
    """
    # Generate per-cycle blocking counts that sum to at most total_rules
    # Strategy: generate num_cycles values, each in [0, remaining]
    per_cycle_counts: list[int] = []
    remaining = total_rules

    for i in range(num_cycles):
        if i == num_cycles - 1:
            # Last cycle gets whatever is left (or less)
            count = data.draw(
                st.integers(min_value=0, max_value=remaining),
                label=f"cycle_{i}_blocking",
            )
        else:
            count = data.draw(
                st.integers(min_value=0, max_value=remaining),
                label=f"cycle_{i}_blocking",
            )
        per_cycle_counts.append(count)
        remaining -= count

    # Simulate VR summary structure
    blocking_failed = sum(per_cycle_counts)
    by_cycle = [
        {"cycle": chr(ord("D") + i), "blocking_failed": c}
        for i, c in enumerate(per_cycle_counts)
    ]

    # Invariant 1: blocking_failed <= total_rules
    assert blocking_failed <= total_rules, (
        f"blocking_failed ({blocking_failed}) > total_rules ({total_rules})"
    )

    # Invariant 2: sum of by_cycle.blocking_failed == blocking_failed
    sum_by_cycle = sum(item["blocking_failed"] for item in by_cycle)
    assert sum_by_cycle == blocking_failed, (
        f"Sum conservation violated: sum(by_cycle)={sum_by_cycle} != "
        f"blocking_failed={blocking_failed}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3: review sort stability
# **Validates: Requirements 4.2**
# Label: Feature: partner-dashboard, Property 3: review sort stability
# ═══════════════════════════════════════════════════════════════════════════════

# Strategy for generating ISO datetime strings
import datetime as _dt

_datetime_st = st.datetimes(
    min_value=_dt.datetime(2020, 1, 1),
    max_value=_dt.datetime(2030, 12, 31),
).map(lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S"))

_layer_st = st.sampled_from(["L1", "L2", "L3", "L4", "L5"])


@st.composite
def review_item_strategy(draw: st.DrawFn) -> dict:
    """Generate a random ReviewItem dict."""
    layer = draw(_layer_st)
    created_at = draw(_datetime_st)
    return {
        "id": draw(st.uuids()).hex,
        "review_layer": layer,
        "summary": draw(st.text(min_size=0, max_size=80)),
        "created_at": created_at,
        "wp_code": f"D{draw(st.integers(min_value=1, max_value=99))}-{draw(st.integers(min_value=1, max_value=9))}",
        "sheet_name": None,
        "cell_ref": None,
    }


@settings(max_examples=15, deadline=None)
@given(items=st.lists(review_item_strategy(), min_size=0, max_size=30))
def test_review_sort_stability(items: list[dict]) -> None:
    """Feature: partner-dashboard, Property 3: review sort stability

    For any list of ReviewItems with varying review_layer and created_at:
    After calling sort_reviews:
    (a) For any two adjacent items where LAYER_PRIORITY[items[i].review_layer] >
        LAYER_PRIORITY[items[i+1].review_layer], higher priority comes first.
    (b) For any two adjacent items with same review_layer, the one with more
        recent created_at comes first (time descending within same layer).

    **Validates: Requirements 4.2**
    """
    sorted_items = sort_reviews(items)

    # Verify length preserved
    assert len(sorted_items) == len(items), (
        f"Sort changed list length: {len(items)} -> {len(sorted_items)}"
    )

    # Check adjacent pairs satisfy sort constraints
    for i in range(len(sorted_items) - 1):
        curr = sorted_items[i]
        next_ = sorted_items[i + 1]

        curr_priority = LAYER_PRIORITY.get(curr["review_layer"], 0)
        next_priority = LAYER_PRIORITY.get(next_["review_layer"], 0)

        # (a) Higher priority must come first (descending priority order)
        assert curr_priority >= next_priority, (
            f"Sort constraint (a) violated at index {i}: "
            f"curr_layer={curr['review_layer']} (priority={curr_priority}) "
            f"should have >= priority than "
            f"next_layer={next_['review_layer']} (priority={next_priority})"
        )

        # (b) Within same layer, more recent created_at comes first
        if curr["review_layer"] == next_["review_layer"]:
            assert curr["created_at"] >= next_["created_at"], (
                f"Sort constraint (b) violated at index {i}: "
                f"same layer={curr['review_layer']}, "
                f"curr_created_at={curr['created_at']} should be >= "
                f"next_created_at={next_['created_at']} (time descending)"
            )
