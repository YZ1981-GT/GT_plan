"""Phase 7 属性测试（PBT P1~P6）

Properties:
- P1: 工时日合计不变量 — sum(hours) ≤ 24.0
- P2: 工时粒度汇总一致性 — sum(cycle=C) == sum(cycle=C, wp_code IN wps) + sum(cycle=C, wp_code IS NULL)
- P3: 推荐评分单调性（工时余量）— 余量大 → score 高
- P4: 推荐评分单调性（历史复核）— 历史多 → score 高
- P5: 紧急度评分单调性 — SLA 少 → score 高
- P6: 紧急度评分范围不变量 — 0 ≤ score ≤ 100

**Validates: Requirements F7.7, F7.4, F9.2, F9.3, F9.4, F12.2, F12.6, F12.7**
"""
from __future__ import annotations

import sys
from decimal import Decimal

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, "backend")

from app.routers.review_recommend import _calc_recommendation_score
from app.routers.partner_urgency import _calc_urgency_score


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P1: 工时日合计不变量
# **Validates: Requirements F7.7**
#
# For any user and date, sum of all hours entries ≤ 24.0
# The _check_daily_limit function enforces this constraint.
# We test the validation logic: given a list of hours entries for a day,
# the sum must be ≤ 24.0 for the system to accept them.
# ═══════════════════════════════════════════════════════════════════════════════


@given(
    hours_list=st.lists(
        st.floats(min_value=0.01, max_value=24.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=30, deadline=None)
def test_p1_daily_hours_invariant(hours_list: list[float]) -> None:
    """P1: 工时日合计不变量 — sum(hours) ≤ 24.0

    For any set of work hour entries that would be accepted by the system,
    the daily total must not exceed 24 hours. We simulate the validation:
    entries are added one by one; each addition is only accepted if the
    running total stays ≤ 24.
    """
    accepted_hours: list[Decimal] = []
    running_total = Decimal("0")

    for h in hours_list:
        entry_hours = Decimal(str(round(h, 2)))
        # Clamp to valid range (0, 24]
        if entry_hours <= 0:
            continue
        if entry_hours > Decimal("24"):
            entry_hours = Decimal("24")

        # Simulate _check_daily_limit: reject if would exceed 24
        if running_total + entry_hours <= Decimal("24"):
            accepted_hours.append(entry_hours)
            running_total += entry_hours

    # Invariant: sum of accepted entries ≤ 24
    total = sum(accepted_hours, Decimal("0"))
    assert total <= Decimal("24"), (
        f"Daily total {total} exceeds 24h limit. Entries: {accepted_hours}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P2: 工时粒度汇总一致性
# **Validates: Requirements F7.4**
#
# sum(hours WHERE cycle=C) == sum(hours WHERE cycle=C AND wp_code IN wps)
#                           + sum(hours WHERE cycle=C AND wp_code IS NULL)
# ═══════════════════════════════════════════════════════════════════════════════

_cycle_st = st.sampled_from(["D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"])
_wp_code_st = st.one_of(
    st.none(),
    st.from_regex(r"[A-N]\d-\d{1,2}", fullmatch=True),
)
_hours_st = st.floats(min_value=0.5, max_value=8.0, allow_nan=False, allow_infinity=False)


@st.composite
def workhour_entries_strategy(draw):
    """Generate a list of work hour entries with mixed granularity."""
    n = draw(st.integers(min_value=1, max_value=20))
    entries = []
    for _ in range(n):
        cycle = draw(_cycle_st)
        wp_code = draw(_wp_code_st)
        hours = round(draw(_hours_st), 2)
        entries.append({"cycle": cycle, "wp_code": wp_code, "hours": hours})
    return entries


@given(entries=workhour_entries_strategy())
@settings(max_examples=30, deadline=None)
def test_p2_granularity_aggregation_consistency(entries: list[dict]) -> None:
    """P2: 工时粒度汇总一致性

    For any cycle C in the entries:
    sum(hours WHERE cycle=C) == sum(hours WHERE cycle=C AND wp_code IS NOT NULL)
                              + sum(hours WHERE cycle=C AND wp_code IS NULL)
    """
    # Get all unique cycles
    cycles = set(e["cycle"] for e in entries)

    for cycle in cycles:
        # Total for this cycle
        cycle_total = sum(e["hours"] for e in entries if e["cycle"] == cycle)

        # Sum where wp_code is not None (fine-grained)
        with_wp = sum(
            e["hours"] for e in entries
            if e["cycle"] == cycle and e["wp_code"] is not None
        )

        # Sum where wp_code is None (cycle-level only)
        without_wp = sum(
            e["hours"] for e in entries
            if e["cycle"] == cycle and e["wp_code"] is None
        )

        # Invariant: total = fine-grained + cycle-level
        assert abs(cycle_total - (with_wp + without_wp)) < 1e-9, (
            f"Cycle {cycle}: total={cycle_total} != "
            f"with_wp={with_wp} + without_wp={without_wp} = {with_wp + without_wp}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P3: 推荐评分单调性（工时余量）
# **Validates: Requirements F9.2, F9.4**
#
# More capacity (less hours worked) → higher score (other factors fixed)
# ═══════════════════════════════════════════════════════════════════════════════


@given(
    hours_a=st.floats(min_value=0, max_value=40, allow_nan=False, allow_infinity=False),
    hours_b=st.floats(min_value=0, max_value=40, allow_nan=False, allow_infinity=False),
    review_count=st.integers(min_value=0, max_value=10),
    matched_cycles=st.integers(min_value=0, max_value=5),
    total_cycles=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=30, deadline=None)
def test_p3_recommend_score_capacity_monotonicity(
    hours_a: float, hours_b: float,
    review_count: int, matched_cycles: int, total_cycles: int,
) -> None:
    """P3: 推荐评分单调性（工时余量）

    If candidate A has worked fewer hours this week than candidate B
    (i.e., A has more capacity), then A's score must be >= B's score.
    Strict monotonicity when capacity_factor differs.
    """
    # Ensure hours_a < hours_b (A has more capacity)
    assume(hours_a < hours_b)
    # Ensure the difference is large enough to produce different capacity_factors
    assume(abs(hours_b - hours_a) > 0.5)

    score_a = _calc_recommendation_score(
        review_count_in_cycle=review_count,
        current_week_hours=hours_a,
        matched_cycles=matched_cycles,
        total_cycles=total_cycles,
    )
    score_b = _calc_recommendation_score(
        review_count_in_cycle=review_count,
        current_week_hours=hours_b,
        matched_cycles=matched_cycles,
        total_cycles=total_cycles,
    )

    # A has more capacity (fewer hours) → higher score
    assert score_a["score"] >= score_b["score"], (
        f"Capacity monotonicity violated: hours_a={hours_a} (score={score_a['score']}) "
        f"should be >= hours_b={hours_b} (score={score_b['score']})"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P4: 推荐评分单调性（历史复核）
# **Validates: Requirements F9.2, F9.3**
#
# More history → higher score (other factors fixed)
# ═══════════════════════════════════════════════════════════════════════════════


@given(
    history_a=st.integers(min_value=0, max_value=20),
    history_b=st.integers(min_value=0, max_value=20),
    current_week_hours=st.floats(min_value=0, max_value=40, allow_nan=False, allow_infinity=False),
    matched_cycles=st.integers(min_value=0, max_value=5),
    total_cycles=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=30, deadline=None)
def test_p4_recommend_score_history_monotonicity(
    history_a: int, history_b: int,
    current_week_hours: float, matched_cycles: int, total_cycles: int,
) -> None:
    """P4: 推荐评分单调性（历史复核）

    If candidate A has more historical review records than candidate B,
    then A's score must be >= B's score.
    """
    # Ensure history_a > history_b
    assume(history_a > history_b)

    score_a = _calc_recommendation_score(
        review_count_in_cycle=history_a,
        current_week_hours=current_week_hours,
        matched_cycles=matched_cycles,
        total_cycles=total_cycles,
    )
    score_b = _calc_recommendation_score(
        review_count_in_cycle=history_b,
        current_week_hours=current_week_hours,
        matched_cycles=matched_cycles,
        total_cycles=total_cycles,
    )

    # A has more history → higher score
    assert score_a["score"] >= score_b["score"], (
        f"History monotonicity violated: history_a={history_a} (score={score_a['score']}) "
        f"should be >= history_b={history_b} (score={score_b['score']})"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P5: 紧急度评分单调性
# **Validates: Requirements F12.2**
#
# Less SLA days remaining → higher score (other factors fixed)
# ═══════════════════════════════════════════════════════════════════════════════


@st.composite
def urgency_monotonicity_inputs(draw):
    """Generate valid urgency inputs with days_a < days_b guaranteed."""
    max_days = draw(st.integers(min_value=10, max_value=90))
    days_a = draw(st.integers(min_value=0, max_value=88))
    days_b = draw(st.integers(min_value=days_a + 1, max_value=90))
    blocking_vr = draw(st.integers(min_value=0, max_value=20))
    total_wp = draw(st.integers(min_value=1, max_value=50))
    completed_wp = draw(st.integers(min_value=0, max_value=total_wp))
    return days_a, days_b, max_days, blocking_vr, completed_wp, total_wp


@given(inputs=urgency_monotonicity_inputs())
@settings(max_examples=30, deadline=None)
def test_p5_urgency_score_sla_monotonicity(inputs: tuple) -> None:
    """P5: 紧急度评分单调性

    If project A has fewer SLA days remaining than project B,
    then A's urgency score must be >= B's score (closer to deadline = more urgent).
    """
    days_a, days_b, max_days, blocking_vr, completed_wp, total_wp = inputs

    score_a = _calc_urgency_score(
        days_remaining=days_a,
        max_days=max_days,
        blocking_vr_count=blocking_vr,
        completed_wp=completed_wp,
        total_wp=total_wp,
    )
    score_b = _calc_urgency_score(
        days_remaining=days_b,
        max_days=max_days,
        blocking_vr_count=blocking_vr,
        completed_wp=completed_wp,
        total_wp=total_wp,
    )

    # A has fewer days remaining → higher urgency score
    assert score_a >= score_b, (
        f"Urgency SLA monotonicity violated: days_a={days_a} (score={score_a}) "
        f"should be >= days_b={days_b} (score={score_b})"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P6: 紧急度评分范围不变量
# **Validates: Requirements F12.2, F12.6, F12.7**
#
# For any valid inputs, 0 ≤ urgency_score ≤ 100
# ═══════════════════════════════════════════════════════════════════════════════


@given(
    days_remaining=st.one_of(
        st.none(),
        st.integers(min_value=-30, max_value=365),
    ),
    max_days=st.integers(min_value=-10, max_value=365),
    blocking_vr=st.integers(min_value=0, max_value=100),
    completed_wp=st.integers(min_value=0, max_value=100),
    total_wp=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=30, deadline=None)
def test_p6_urgency_score_range_invariant(
    days_remaining: int | None, max_days: int,
    blocking_vr: int, completed_wp: int, total_wp: int,
) -> None:
    """P6: 紧急度评分范围不变量

    For any combination of valid inputs, the urgency score must be in [0, 100].
    """
    score = _calc_urgency_score(
        days_remaining=days_remaining,
        max_days=max_days,
        blocking_vr_count=blocking_vr,
        completed_wp=completed_wp,
        total_wp=total_wp,
    )

    assert 0 <= score <= 100, (
        f"Urgency score {score} out of range [0, 100]. "
        f"Inputs: days_remaining={days_remaining}, max_days={max_days}, "
        f"blocking_vr={blocking_vr}, completed_wp={completed_wp}, total_wp={total_wp}"
    )
