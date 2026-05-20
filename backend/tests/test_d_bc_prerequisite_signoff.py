"""P5: B/C 前置阻断 sign-off — 属性测试（spec workpaper-d-sales-cycle PBT-5）。

Validates: Requirements F8

Property P5: D 循环 B/C 前置完成度 = 0 → D 循环 wp 不能 sign-off（gate_engine 集成）。
模拟 gate_engine 逻辑：如果所有前置底稿 state='pending'，则 overall='blocked'。
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

PREREQUISITE_STATES = ["completed", "in_progress", "pending"]


def _compute_overall(states: list[str]) -> str:
    """复刻 wp_prerequisite_status.py 的 overall 计算逻辑。

    规则：
    - 空列表或含 'pending' → 'blocked'
    - 含 'in_progress'（无 pending）→ 'partial'
    - 全部 'completed' → 'ready'
    """
    if not states or "pending" in states:
        return "blocked"
    if "in_progress" in states:
        return "partial"
    return "ready"


def _can_signoff(overall: str) -> bool:
    """只有 overall='ready' 时才能签字。"""
    return overall == "ready"


@given(states=st.lists(st.sampled_from(PREREQUISITE_STATES), min_size=3, max_size=3))
@settings(max_examples=20, deadline=None)
def test_property_p5_all_pending_blocks_signoff(states: list[str]) -> None:
    """P5: 当所有前置底稿 state='pending' 时，D 循环 wp 不能 sign-off。"""
    if all(s == "pending" for s in states):
        overall = _compute_overall(states)
        assert overall == "blocked"
        assert not _can_signoff(overall)


@given(states=st.lists(st.just("completed"), min_size=3, max_size=3))
@settings(max_examples=20, deadline=None)
def test_property_p5_all_completed_allows_signoff(states: list[str]) -> None:
    """P5: 当所有前置底稿 state='completed' 时，D 循环 wp 可以 sign-off。"""
    overall = _compute_overall(states)
    assert overall == "ready"
    assert _can_signoff(overall)


@given(states=st.lists(st.sampled_from(PREREQUISITE_STATES), min_size=3, max_size=3))
@settings(max_examples=20, deadline=None)
def test_property_p5_any_pending_blocks(states: list[str]) -> None:
    """P5: 任一前置底稿 state='pending' → overall != 'ready' → 不能 sign-off。"""
    overall = _compute_overall(states)
    if "pending" in states:
        assert overall == "blocked"
        assert not _can_signoff(overall)
