"""GroupingEngine 单元测试（advanced-query-module Task 9.1）

覆盖核心分组聚合逻辑与关键边界：
- 无维度 → 明细结果集（R5.7）
- 单/多维度分组聚合，维度组合升序排序（R5.2 / R5.3）
- 五种聚合 sum/count/avg/min/max（R5.4）；count 适用任意类型
- 维度无效 / 超 10 → INVALID_GROUP_DIM（含 invalid），保留条件不执行（R5.1 / R5.5）
- 非数值列施加 sum/avg/min/max → AGG_TYPE_MISMATCH（含 field, agg），不执行（R5.6）

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import decimal

import pytest
from fastapi import HTTPException

from app.services.custom_query.grouping_engine import (
    Agg,
    GroupingEngine,
    GroupResult,
)


@pytest.fixture()
def engine() -> GroupingEngine:
    return GroupingEngine()


# ─────────────────────────────────────────────────────────────────────────────
# R5.7：无维度 → 明细结果集
# ─────────────────────────────────────────────────────────────────────────────
def test_no_dims_returns_detail(engine: GroupingEngine) -> None:
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    res = engine.group(rows, dims=[], aggs=[{"field": "a", "func": "sum"}])
    assert isinstance(res, GroupResult)
    assert res.grouped is False
    assert res.dims == []
    assert res.rows == rows
    assert res.agg_keys == []


# ─────────────────────────────────────────────────────────────────────────────
# R5.2 / R5.3 / R5.4：单维度分组聚合 + 升序
# ─────────────────────────────────────────────────────────────────────────────
def test_single_dim_sum_and_count(engine: GroupingEngine) -> None:
    rows = [
        {"cycle": "B", "amt": 10},
        {"cycle": "A", "amt": 5},
        {"cycle": "B", "amt": 20},
        {"cycle": "A", "amt": 7},
    ]
    res = engine.group(
        rows,
        dims=["cycle"],
        aggs=[{"field": "amt", "func": "sum"}, {"field": "*", "func": "count"}],
    )
    assert res.grouped is True
    assert res.dims == ["cycle"]
    # 升序：A 在 B 之前
    assert [r["cycle"] for r in res.rows] == ["A", "B"]
    a_row, b_row = res.rows
    assert a_row["sum_amt"] == 12
    assert a_row["count_all"] == 2
    assert b_row["sum_amt"] == 30
    assert b_row["count_all"] == 2


def test_multi_dim_grouping_unique_combos(engine: GroupingEngine) -> None:
    rows = [
        {"d1": "x", "d2": 1, "v": 100},
        {"d1": "x", "d2": 1, "v": 50},
        {"d1": "x", "d2": 2, "v": 30},
        {"d1": "y", "d2": 1, "v": 10},
    ]
    res = engine.group(rows, dims=["d1", "d2"], aggs=[{"field": "v", "func": "sum"}])
    # 3 个唯一组合 (x,1) (x,2) (y,1)，升序
    assert [(r["d1"], r["d2"]) for r in res.rows] == [("x", 1), ("x", 2), ("y", 1)]
    assert res.rows[0]["sum_v"] == 150


def test_avg_min_max(engine: GroupingEngine) -> None:
    rows = [
        {"g": "a", "n": 2},
        {"g": "a", "n": 4},
        {"g": "a", "n": 9},
    ]
    res = engine.group(
        rows,
        dims=["g"],
        aggs=[
            {"field": "n", "func": "avg"},
            {"field": "n", "func": "min"},
            {"field": "n", "func": "max"},
        ],
    )
    row = res.rows[0]
    assert row["avg_n"] == pytest.approx(5.0)
    assert row["min_n"] == 2
    assert row["max_n"] == 9


def test_decimal_sum_preserves_type(engine: GroupingEngine) -> None:
    rows = [
        {"g": "a", "amt": decimal.Decimal("1.50")},
        {"g": "a", "amt": decimal.Decimal("2.25")},
    ]
    res = engine.group(rows, dims=["g"], aggs=[{"field": "amt", "func": "sum"}])
    assert res.rows[0]["sum_amt"] == decimal.Decimal("3.75")


def test_count_works_on_non_numeric_field(engine: GroupingEngine) -> None:
    rows = [
        {"g": "a", "label": "foo"},
        {"g": "a", "label": None},
        {"g": "a", "label": "bar"},
    ]
    res = engine.group(rows, dims=["g"], aggs=[{"field": "label", "func": "count"}])
    # count(field) 只计非 None
    assert res.rows[0]["count_label"] == 2


def test_alias_override(engine: GroupingEngine) -> None:
    rows = [{"g": "a", "v": 1}, {"g": "a", "v": 2}]
    res = engine.group(
        rows, dims=["g"], aggs=[{"field": "v", "func": "sum", "alias": "total"}]
    )
    assert "total" in res.agg_keys
    assert res.rows[0]["total"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# R5.1 / R5.5：维度无效 / 超 10 → INVALID_GROUP_DIM
# ─────────────────────────────────────────────────────────────────────────────
def test_invalid_dim_rejected(engine: GroupingEngine) -> None:
    rows = [{"a": 1}]
    with pytest.raises(HTTPException) as ei:
        engine.group(rows, dims=["nope"], aggs=[])
    assert ei.value.status_code == 400
    assert ei.value.detail["error_code"] == "INVALID_GROUP_DIM"
    assert "nope" in ei.value.detail["invalid"]


def test_too_many_dims_rejected(engine: GroupingEngine) -> None:
    cols = [f"d{i}" for i in range(11)]
    rows = [{c: i for i, c in enumerate(cols)}]
    with pytest.raises(HTTPException) as ei:
        engine.group(rows, dims=cols, aggs=[])
    assert ei.value.status_code == 400
    assert ei.value.detail["error_code"] == "INVALID_GROUP_DIM"
    assert ei.value.detail["count"] == 11
    assert ei.value.detail["max_dims"] == 10


def test_exactly_ten_dims_allowed(engine: GroupingEngine) -> None:
    cols = [f"d{i}" for i in range(10)]
    rows = [{c: 1 for c in cols}]
    res = engine.group(rows, dims=cols, aggs=[])
    assert res.grouped is True
    assert len(res.dims) == 10


def test_valid_dims_allows_empty_result_set(engine: GroupingEngine) -> None:
    # 空结果集：借助 columns 显式声明列，维度仍可校验通过
    res = engine.group([], dims=["cycle"], aggs=[], columns=["cycle", "amt"])
    assert res.grouped is True
    assert res.rows == []


# ─────────────────────────────────────────────────────────────────────────────
# R5.6：非数值列施加 sum/avg/min/max → AGG_TYPE_MISMATCH
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("func", ["sum", "avg", "min", "max"])
def test_non_numeric_agg_rejected(engine: GroupingEngine, func: str) -> None:
    rows = [{"g": "a", "label": "text"}, {"g": "a", "label": "more"}]
    with pytest.raises(HTTPException) as ei:
        engine.group(rows, dims=["g"], aggs=[{"field": "label", "func": func}])
    assert ei.value.status_code == 400
    assert ei.value.detail["error_code"] == "AGG_TYPE_MISMATCH"
    assert ei.value.detail["field"] == "label"
    assert ei.value.detail["agg"] == func


def test_bool_is_non_numeric_for_sum(engine: GroupingEngine) -> None:
    rows = [{"g": "a", "flag": True}, {"g": "a", "flag": False}]
    with pytest.raises(HTTPException) as ei:
        engine.group(rows, dims=["g"], aggs=[{"field": "flag", "func": "sum"}])
    assert ei.value.detail["error_code"] == "AGG_TYPE_MISMATCH"


def test_agg_not_in_whitelist_rejected(engine: GroupingEngine) -> None:
    rows = [{"g": "a", "v": 1}]
    with pytest.raises(HTTPException) as ei:
        engine.group(rows, dims=["g"], aggs=[{"field": "v", "func": "median"}])
    assert ei.value.detail["error_code"] == "AGG_NOT_ALLOWED"


def test_none_values_skipped_in_numeric_agg(engine: GroupingEngine) -> None:
    rows = [
        {"g": "a", "v": 10},
        {"g": "a", "v": None},
        {"g": "a", "v": 20},
    ]
    res = engine.group(rows, dims=["g"], aggs=[{"field": "v", "func": "sum"}])
    # None 不阻断数值校验，且被跳过
    assert res.rows[0]["sum_v"] == 30


def test_agg_dataclass_input(engine: GroupingEngine) -> None:
    rows = [{"g": "a", "v": 1}, {"g": "a", "v": 2}]
    res = engine.group(rows, dims=["g"], aggs=[Agg(field="v", func="sum")])
    assert res.rows[0]["sum_v"] == 3
