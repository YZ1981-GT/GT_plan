"""Property-based tests for note_cell_merge — round-trip 三态不变量.

Spec: .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.5
Design: D1 三态合并规则（auto / manual / locked）

4 个不变量（PBT）：

  ① auto    round-trip：所有 col 都是 auto 时，
                merged.values[i] == new.values[i]（值同 new）
  ② manual  round-trip：所有 col 都是 manual 时，
                merged.values[i] == old.values[i]（值同 old）
  ③ locked  round-trip：所有 col 都是 locked 时，
                merged.values[i] == old.values[i]（值同 old）；_cell_meta 不变
  ④ manual_value 不丢失：manual 模式备份后再次合并，manual_value 保持首次值不变

Validates: Requirements R1.3 验收 10、11、12
"""

from __future__ import annotations

import copy

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.note_cell_merge import merge_row_preserving_cell_modes


# ---------------------------------------------------------------------------
# Strategies — 收敛快、聚焦合并语义
# ---------------------------------------------------------------------------

# 单元格值：含 None / int / float / str（前端单元格可能字符串数字）
_value_strategy = st.one_of(
    st.none(),
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(
        min_value=-1e6,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
    ),
    st.text(min_size=0, max_size=8),
)


def _values_strategy(min_size: int = 1, max_size: int = 5) -> st.SearchStrategy:
    return st.lists(_value_strategy, min_size=min_size, max_size=max_size)


def _make_meta(values_len: int) -> dict[str, dict]:
    return {
        str(i): {"manual_value": None, "semantic": None, "binding_id": None}
        for i in range(values_len)
    }


# ---------------------------------------------------------------------------
# 不变量 ① auto round-trip
# ---------------------------------------------------------------------------


@given(old_values=_values_strategy(), new_values=_values_strategy())
@settings(
    max_examples=80,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_auto_round_trip_uses_new_values(old_values, new_values) -> None:
    """**Validates: Requirements R1.3 验收 10**

    不变量 ①：所有 col 都是 auto 时，merged.values[i] == new.values[i]
    （new 长度为权威；超出 old 长度的 col 也按 auto 处理）.
    """
    n_new = len(new_values)
    n_old = len(old_values)
    common_max = max(n_new, n_old)
    old_row = {
        "label": "X",
        "values": list(old_values),
        "_cell_modes": {str(i): "auto" for i in range(common_max)},
        "_cell_meta": _make_meta(common_max),
    }
    new_row = {"label": "X", "values": list(new_values)}

    merged = merge_row_preserving_cell_modes(old_row, new_row)

    # values 长度跟 new
    assert len(merged["values"]) == n_new
    # 每个 col == new.values[i]
    for i in range(n_new):
        assert merged["values"][i] == new_values[i]


# ---------------------------------------------------------------------------
# 不变量 ② manual round-trip
# ---------------------------------------------------------------------------


@given(old_values=_values_strategy(), new_values=_values_strategy())
@settings(
    max_examples=80,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_manual_round_trip_keeps_old_values(old_values, new_values) -> None:
    """**Validates: Requirements R1.3 验收 11**

    不变量 ②：所有 col 都是 manual 时，
                merged.values[i] == old.values[i]（在 new 长度内）.
    超出 old 长度的 col 没有 old 值（None），也按 mode=manual 处理 → None.
    """
    n_new = len(new_values)
    n_old = len(old_values)
    common_max = max(n_new, n_old)
    old_row = {
        "label": "X",
        "values": list(old_values),
        "_cell_modes": {str(i): "manual" for i in range(common_max)},
        "_cell_meta": _make_meta(common_max),
    }
    new_row = {"label": "X", "values": list(new_values)}

    merged = merge_row_preserving_cell_modes(old_row, new_row)

    assert len(merged["values"]) == n_new
    for i in range(n_new):
        expected = old_values[i] if i < n_old else None
        assert merged["values"][i] == expected
        # 备份了原始 old.values[i] 到 manual_value（仅当 old 值非 None）
        if expected is not None:
            assert merged["_cell_meta"][str(i)]["manual_value"] == expected


# ---------------------------------------------------------------------------
# 不变量 ③ locked round-trip
# ---------------------------------------------------------------------------


@given(old_values=_values_strategy(), new_values=_values_strategy())
@settings(
    max_examples=80,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_locked_round_trip_keeps_old_values_and_meta_untouched(
    old_values, new_values,
) -> None:
    """**Validates: Requirements R1.3 验收 12**

    不变量 ③：所有 col 都是 locked 时，
                merged.values[i] == old.values[i]（在 new 长度内）；
                _cell_meta[i].manual_value 保持原状（None）— locked 不动 _cell_meta.
    """
    n_new = len(new_values)
    n_old = len(old_values)
    common_max = max(n_new, n_old)
    old_row = {
        "label": "X",
        "values": list(old_values),
        "_cell_modes": {str(i): "locked" for i in range(common_max)},
        "_cell_meta": _make_meta(common_max),
    }
    new_row = {"label": "X", "values": list(new_values)}

    merged = merge_row_preserving_cell_modes(old_row, new_row)

    assert len(merged["values"]) == n_new
    for i in range(n_new):
        expected = old_values[i] if i < n_old else None
        assert merged["values"][i] == expected
        # locked 不写 manual_value（保持 None）
        assert merged["_cell_meta"][str(i)]["manual_value"] is None


# ---------------------------------------------------------------------------
# 不变量 ④ manual_value 不丢失（再次合并幂等）
# ---------------------------------------------------------------------------


@given(
    old_values=_values_strategy(min_size=1, max_size=4),
    new_values_a=_values_strategy(min_size=1, max_size=4),
    new_values_b=_values_strategy(min_size=1, max_size=4),
)
@settings(
    max_examples=60,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_manual_value_never_lost_on_repeated_merge(
    old_values, new_values_a, new_values_b,
) -> None:
    """**Validates: Requirements R1.3 验收 11**

    不变量 ④：manual 模式 col 经过两次合并（new_a → new_b），
                manual_value 仍然等于第一次合并前的 old.values[i]
                （即首次备份的原始值，不被后续合并覆盖）.
    """
    n_old = len(old_values)
    n_new_a = len(new_values_a)
    n_new_b = len(new_values_b)
    common_max = max(n_old, n_new_a, n_new_b)

    old_row = {
        "label": "X",
        "values": list(old_values),
        "_cell_modes": {str(i): "manual" for i in range(common_max)},
        "_cell_meta": _make_meta(common_max),
    }
    new_row_a = {"label": "X", "values": list(new_values_a)}
    new_row_b = {"label": "X", "values": list(new_values_b)}

    # 第一次合并 — manual_value 备份原始 old
    merged1 = merge_row_preserving_cell_modes(old_row, new_row_a)

    # snapshot 第一次合并后的 manual_value
    expected_backups: dict[int, object] = {}
    for i in range(n_new_a):
        expected_backups[i] = merged1["_cell_meta"][str(i)]["manual_value"]

    # 第二次合并：用 merged1（其 _cell_modes 仍是全 manual）合 new_row_b
    merged2 = merge_row_preserving_cell_modes(merged1, new_row_b)

    # 在两次 new 长度交集内的 col：manual_value 应保持第一次的备份不变
    common = min(n_new_a, n_new_b)
    for i in range(common):
        assert merged2["_cell_meta"][str(i)]["manual_value"] == expected_backups[i]


# ---------------------------------------------------------------------------
# 附加：纯函数性 — 多次合并不破坏入参
# ---------------------------------------------------------------------------


@given(old_values=_values_strategy(), new_values=_values_strategy())
@settings(
    max_examples=40,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_pure_function_does_not_mutate_inputs(old_values, new_values) -> None:
    """合并函数是纯函数：不修改入参."""
    n = max(len(old_values), len(new_values))
    old_row = {
        "label": "X",
        "values": list(old_values),
        "_cell_modes": {str(i): "manual" for i in range(n)},
        "_cell_meta": _make_meta(n),
    }
    new_row = {"label": "X", "values": list(new_values)}

    old_snap = copy.deepcopy(old_row)
    new_snap = copy.deepcopy(new_row)

    _ = merge_row_preserving_cell_modes(old_row, new_row)

    assert old_row == old_snap
    assert new_row == new_snap
