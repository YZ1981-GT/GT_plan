"""Unit tests for PivotEngine.pivot — Task 10.2（advanced-query-module）.

覆盖 R6.1（交叉透视）、R6.4（列基数上限）、R6.5/6.6（addr_id 单源保留 / 多源不携带）、
R6.7（空组合空值）以及与 GroupingEngine 聚合参考实现一致（P7 共享）。

Validates: Requirements 6.1, 6.4, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.custom_query.grouping_engine import Agg, GroupingEngine
from app.services.custom_query.pivot_engine import (
    Cell,
    PivotConfig,
    PivotEngine,
)


def _cell_map(grid):
    """{(row_label, col_label): Cell} 便于按标签断言。"""
    out = {}
    for r, rl in enumerate(grid.row_labels):
        for c, cl in enumerate(grid.col_labels):
            out[(rl, cl)] = grid.cells[r][c]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# R6.1：基本交叉透视 + 升序标签
# ─────────────────────────────────────────────────────────────────────────────
def test_pivot_basic_cross_table():
    eng = PivotEngine()
    rows = [
        {"acct": "现金", "period": "Q1", "amt": 10},
        {"acct": "现金", "period": "Q2", "amt": 20},
        {"acct": "银行", "period": "Q1", "amt": 30},
    ]
    cfg = PivotConfig(row_dims=["acct"], col_dims=["period"], value_field="amt", agg="sum")
    grid = eng.pivot(rows, cfg)

    assert grid.row_labels == ["现金", "银行"]  # 升序
    assert grid.col_labels == ["Q1", "Q2"]
    m = _cell_map(grid)
    assert m[("现金", "Q1")].value == 10
    assert m[("现金", "Q2")].value == 20
    assert m[("银行", "Q1")].value == 30


def test_pivot_ascending_sorted_labels():
    eng = PivotEngine()
    rows = [
        {"r": "b", "c": "y", "v": 1},
        {"r": "a", "c": "z", "v": 2},
        {"r": "a", "c": "x", "v": 3},
    ]
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")
    grid = eng.pivot(rows, cfg)
    assert grid.row_labels == ["a", "b"]
    assert grid.col_labels == ["x", "y", "z"]


# ─────────────────────────────────────────────────────────────────────────────
# R6.7：空组合 → None（非 0、非报错）
# ─────────────────────────────────────────────────────────────────────────────
def test_pivot_empty_combination_is_none_not_zero():
    eng = PivotEngine()
    rows = [
        {"r": "a", "c": "x", "v": 5},
        {"r": "b", "c": "y", "v": 7},
    ]
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")
    grid = eng.pivot(rows, cfg)
    m = _cell_map(grid)
    # (a, y) 与 (b, x) 无源行 → None（不是 0）
    assert m[("a", "y")].value is None
    assert m[("b", "x")].value is None
    assert m[("a", "y")].addr_id is None
    assert m[("a", "x")].value == 5


# ─────────────────────────────────────────────────────────────────────────────
# R6.5 / R6.6：addr_id 单源保留 / 多源不携带
# ─────────────────────────────────────────────────────────────────────────────
def test_pivot_single_source_carries_addr_id():
    eng = PivotEngine()
    rows = [
        {"r": "a", "c": "x", "v": 5, "addr_id": "D2/S1/A1"},
    ]
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")
    grid = eng.pivot(rows, cfg)
    cell = grid.cells[0][0]
    assert cell.value == 5
    assert cell.addr_id == "D2/S1/A1"


def test_pivot_multi_source_drops_addr_id():
    eng = PivotEngine()
    rows = [
        {"r": "a", "c": "x", "v": 5, "addr_id": "D2/S1/A1"},
        {"r": "a", "c": "x", "v": 15, "addr_id": "D2/S1/A2"},
    ]
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")
    grid = eng.pivot(rows, cfg)
    cell = grid.cells[0][0]
    assert cell.value == 20  # 聚合
    assert cell.addr_id is None  # 多源 → 不可下钻


def test_pivot_single_source_without_addr_id_stays_none():
    eng = PivotEngine()
    rows = [{"r": "a", "c": "x", "v": 5}]  # 源行无 addr_id
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")
    grid = eng.pivot(rows, cfg)
    assert grid.cells[0][0].addr_id is None


# ─────────────────────────────────────────────────────────────────────────────
# R6.4：列基数上限
# ─────────────────────────────────────────────────────────────────────────────
def test_pivot_col_limit_exceeded_raises():
    eng = PivotEngine()
    rows = [{"r": "a", "c": f"col{i}", "v": i} for i in range(5)]
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")
    with pytest.raises(HTTPException) as ei:
        eng.pivot(rows, cfg, max_cols=3)
    detail = ei.value.detail
    assert ei.value.status_code == 400
    assert detail["error_code"] == "PIVOT_COL_LIMIT"
    assert detail["actual"] == 5
    assert detail["limit"] == 3


def test_pivot_col_limit_boundary_ok():
    eng = PivotEngine()
    rows = [{"r": "a", "c": f"col{i}", "v": i} for i in range(3)]
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")
    grid = eng.pivot(rows, cfg, max_cols=3)  # 恰好等于上限 → 允许
    assert grid.n_cols == 3


# ─────────────────────────────────────────────────────────────────────────────
# P7 共享：透视聚合与 GroupingEngine 参考实现一致
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("func", ["sum", "count", "avg", "min", "max"])
def test_pivot_agg_matches_grouping_reference(func):
    eng = PivotEngine()
    ref = GroupingEngine()
    rows = [
        {"r": "a", "c": "x", "v": 10},
        {"r": "a", "c": "x", "v": 20},
        {"r": "a", "c": "x", "v": 30},
    ]
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg=func)
    grid = eng.pivot(rows, cfg)
    pivot_val = grid.cells[0][0].value

    # 参考：对同一源值集合按同一聚合计算
    ref_val = GroupingEngine._compute_agg(Agg(field="v", func=func), rows)
    assert pivot_val == ref_val


# ─────────────────────────────────────────────────────────────────────────────
# 退化形态：无维度
# ─────────────────────────────────────────────────────────────────────────────
def test_pivot_no_dims_single_cell():
    eng = PivotEngine()
    rows = [{"v": 1}, {"v": 2}, {"v": 3}]
    cfg = PivotConfig(row_dims=[], col_dims=[], value_field="v", agg="sum")
    grid = eng.pivot(rows, cfg)
    assert grid.n_rows == 1 and grid.n_cols == 1
    assert grid.cells[0][0].value == 6  # 多源聚合
    assert grid.cells[0][0].addr_id is None


def test_pivot_no_rows_empty_grid():
    eng = PivotEngine()
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")
    grid = eng.pivot([], cfg)
    assert grid.row_labels == []
    assert grid.col_labels == []
    assert grid.cells == []


def test_pivot_accepts_duck_typed_config():
    """pivot 以鸭子类型接受字段同名的配置（如 query_orchestrator.PivotConfig）。"""
    eng = PivotEngine()

    class _DuckCfg:
        row_dims = ["r"]
        col_dims = ["c"]
        value_field = "v"
        agg = "sum"
        max_cols = 512

    rows = [{"r": "a", "c": "x", "v": 9}]
    grid = eng.pivot(rows, _DuckCfg())
    assert grid.cells[0][0].value == 9
