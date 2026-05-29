"""P1: scenario 文件加载幂等 — 属性测试（spec workpaper-d-sales-cycle PBT-1）。

Validates: Requirements F4

Property P1: scenario ∈ {normal, ipo, listed, transfer, restructure, fraud_response}
→ _filter_files_by_scenario(paths, s) 对同一输入调用两次结果相同（幂等）。
且过滤结果是输入的子集。
"""
from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings, strategies as st

from app.services.wp_template_init_service import _filter_files_by_scenario

SCENARIOS = ["normal", "ipo", "listed", "transfer", "restructure", "fraud_response"]


@given(
    scenario=st.sampled_from(SCENARIOS),
    file_names=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=20),
)
@settings(max_examples=15, deadline=None)
def test_property_p1_filter_idempotent(scenario: str, file_names: list[str]) -> None:
    """P1: _filter_files_by_scenario 幂等 — 对同一输入调用两次结果相同。"""
    paths = [Path(f"D/{n}.xlsx") for n in file_names]
    first = _filter_files_by_scenario(paths, scenario)
    second = _filter_files_by_scenario(paths, scenario)
    assert first == second, (
        f"scenario={scenario} 两次调用结果不同: first={first}, second={second}"
    )


@given(
    scenario=st.sampled_from(SCENARIOS),
    file_names=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=20),
)
@settings(max_examples=15, deadline=None)
def test_property_p1_subset_of_input(scenario: str, file_names: list[str]) -> None:
    """P1: 过滤结果是输入的子集。"""
    paths = [Path(f"D/{n}.xlsx") for n in file_names]
    result = _filter_files_by_scenario(paths, scenario)
    assert all(p in paths for p in result), (
        f"scenario={scenario} 结果含非输入元素: result={result}, paths={paths}"
    )
