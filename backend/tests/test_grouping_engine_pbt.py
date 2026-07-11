"""GroupingEngine 属性测试（advanced-query-module Tasks 9.2–9.5）

逐条实现 design.md §Correctness Properties 的分组相关属性（Hypothesis）：

- **P6**（Task 9.2）分组正确性与升序排序 — Validates: Requirements 5.2, 5.3
- **P7**（Task 9.3）聚合值与参考实现一致 — Validates: Requirements 5.4, 6.1, 6.7
- **P8**（Task 9.4）分组维度校验 — Validates: Requirements 5.1, 5.5
- **P9**（Task 9.5）非数值聚合拒绝 — Validates: Requirements 5.6

每条属性一个测试。按平台「测试提速铁律」，本文件显式使用
``@settings(max_examples=5)``（conftest 已注册 fast profile，此处再显式收敛）。
"""

from __future__ import annotations

import copy

import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.custom_query.grouping_engine import GroupingEngine, _sort_key
from app.services.custom_query.pivot_engine import PivotConfig, PivotEngine

# 维度值池：混合类型 + None，用于覆盖异构维度值的稳定升序
_DIM_VALUE = st.sampled_from([0, 1, 2, "x", "y", None])
# 数值池：整数 + None（用整数保证聚合精确比较，avg 用 approx）
_NUM_VALUE = st.one_of(st.none(), st.integers(min_value=-50, max_value=50))


# ─────────────────────────────────────────────────────────────────────────────
# Feature: advanced-query-module, Property 6: 分组正确性与升序排序
#   For any 结果行集与 1–10 个分组维度，分组结果的行数等于维度值唯一组合的数量，
#   且结果行按分组维度组合升序排列。
# ─────────────────────────────────────────────────────────────────────────────
@st.composite
def _rows_and_dims(draw):
    n_dims = draw(st.integers(min_value=1, max_value=10))
    dim_names = [f"d{i}" for i in range(n_dims)]
    n_rows = draw(st.integers(min_value=0, max_value=20))
    rows = []
    for _ in range(n_rows):
        row = {name: draw(_DIM_VALUE) for name in dim_names}
        row["v"] = draw(st.integers(min_value=-100, max_value=100))
        rows.append(row)
    return rows, dim_names


@settings(max_examples=5)
@given(_rows_and_dims())
def test_property_6_group_count_and_ascending(case) -> None:
    """Feature: advanced-query-module, Property 6: 分组正确性与升序排序.

    Validates: Requirements 5.2, 5.3
    """
    rows, dim_names = case
    engine = GroupingEngine()
    # 显式声明列，使空结果集也能通过维度有效性校验
    res = engine.group(rows, dims=dim_names, aggs=[], columns=dim_names + ["v"])

    # 行数 == 维度值唯一组合数（R5.2）
    unique_combos = {tuple(r.get(d) for d in dim_names) for r in rows}
    assert len(res.rows) == len(unique_combos)

    # 每个输出行对应一个唯一组合，且组合集合一致
    out_combos = {tuple(r.get(d) for d in dim_names) for r in res.rows}
    assert out_combos == unique_combos

    # 按维度组合升序排列（R5.3）
    sort_keys = [
        tuple(_sort_key(r.get(d)) for d in dim_names) for r in res.rows
    ]
    assert sort_keys == sorted(sort_keys)


# ─────────────────────────────────────────────────────────────────────────────
# Feature: advanced-query-module, Property 7: 聚合值与参考实现一致
#   For any 数值型值字段与 sum/count/avg/max/min 聚合方式，无论用于多维度分组还是
#   透视交叉表，聚合结果都等于对同一源值集合的朴素参考实现计算结果；透视中无对应
#   源值的交叉组合置为空值（而非 0）。
# ─────────────────────────────────────────────────────────────────────────────
def _naive_group_agg(rows, func, field="v", group_key="g"):
    """朴素参考实现：按 group_key 分组，对 field 应用 func（与 _compute_agg 同义）。"""
    groups: dict = {}
    for r in rows:
        groups.setdefault(r[group_key], []).append(r.get(field))
    out: dict = {}
    for g, vals in groups.items():
        nn = [x for x in vals if x is not None]
        if func == "count":
            out[g] = len(nn)
        elif func == "sum":
            out[g] = sum(nn) if nn else 0
        elif func == "avg":
            out[g] = (sum(nn) / len(nn)) if nn else None
        elif func == "min":
            out[g] = min(nn) if nn else None
        elif func == "max":
            out[g] = max(nn) if nn else None
    return out


@st.composite
def _agg_dataset(draw):
    # 分组数据集（单维度 g + 数值 v）
    n = draw(st.integers(min_value=0, max_value=25))
    group_rows = [
        {"g": draw(st.sampled_from(["a", "b", "c"])), "v": draw(_NUM_VALUE)}
        for _ in range(n)
    ]
    # 透视数据集（行维度 r × 列维度 c + 数值 v，整数保证 sum 精确）
    m = draw(st.integers(min_value=1, max_value=20))
    pivot_rows = [
        {
            "r": draw(st.sampled_from(["r1", "r2", "r3"])),
            "c": draw(st.sampled_from(["c1", "c2", "c3"])),
            "v": draw(st.integers(min_value=0, max_value=20)),
        }
        for _ in range(m)
    ]
    return group_rows, pivot_rows


@settings(max_examples=5)
@given(_agg_dataset())
def test_property_7_agg_matches_reference(case) -> None:
    """Feature: advanced-query-module, Property 7: 聚合值与参考实现一致.

    Validates: Requirements 5.4, 6.1, 6.7
    """
    group_rows, pivot_rows = case
    engine = GroupingEngine()

    # ── (a) 分组聚合与朴素参考实现一致（R5.4）──
    for func in ("count", "sum", "avg", "min", "max"):
        res = engine.group(
            group_rows,
            dims=["g"],
            aggs=[{"field": "v", "func": func}],
            columns=["g", "v"],
        )
        ref = _naive_group_agg(group_rows, func)
        out_key = f"{func}_v"
        for row in res.rows:
            expected = ref[row["g"]]
            actual = row[out_key]
            if func == "avg" and expected is not None:
                assert actual == pytest.approx(expected)
            else:
                assert actual == expected

    # ── (b) 透视聚合一致 + 空交叉组合置空值而非 0（R6.1 / R6.7）──
    pengine = PivotEngine()
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")
    grid = pengine.pivot(pivot_rows, cfg)

    for i, rlabel in enumerate(grid.row_labels):
        for j, clabel in enumerate(grid.col_labels):
            sources = [
                row["v"]
                for row in pivot_rows
                if str(row["r"]) == rlabel and str(row["c"]) == clabel
            ]
            cell = grid.cells[i][j]
            if not sources:
                # R6.7：无对应源值 → 空值（None），不得为 0
                assert cell.value is None
            else:
                # R6.1：交叉单元格聚合等于源值集合的 sum（参考实现）
                assert cell.value == sum(sources)


# ─────────────────────────────────────────────────────────────────────────────
# Feature: advanced-query-module, Property 8: 分组维度校验
#   For any 分组维度集合，若包含无法解析为有效 addr_id/有效列的维度或维度数超过
#   10，则系统返回描述性错误并标明无效/超限维度，保留原始查询条件不变，且不执行查询。
# ─────────────────────────────────────────────────────────────────────────────
@st.composite
def _invalid_dim_case(draw):
    valid_cols = ["a", "b", "c"]
    rows = [{"a": 1, "b": 2, "c": 3}, {"a": 4, "b": 5, "c": 6}]
    mode = draw(st.sampled_from(["invalid_name", "over_limit"]))
    if mode == "invalid_name":
        invalid_names = draw(
            st.lists(
                st.sampled_from(["zzz", "qqq", "www", "bad1", "nope"]),
                min_size=1,
                max_size=3,
                unique=True,
            )
        )
        prefix = draw(st.lists(st.sampled_from(valid_cols), max_size=2, unique=True))
        dims = prefix + invalid_names
        return rows, valid_cols, dims, mode, invalid_names
    # over_limit：> 10 个维度
    n = draw(st.integers(min_value=11, max_value=15))
    dims = [f"d{i}" for i in range(n)]
    return rows, valid_cols, dims, mode, dims


@settings(max_examples=5)
@given(_invalid_dim_case())
def test_property_8_group_dim_validation(case) -> None:
    """Feature: advanced-query-module, Property 8: 分组维度校验.

    Validates: Requirements 5.1, 5.5
    """
    rows, valid_cols, dims, mode, named = case
    engine = GroupingEngine()

    rows_snapshot = copy.deepcopy(rows)
    dims_snapshot = list(dims)

    with pytest.raises(HTTPException) as ei:
        engine.group(rows, dims=dims, aggs=[], columns=valid_cols)

    detail = ei.value.detail
    assert ei.value.status_code == 400
    # 描述性错误标明无效/超限维度（R5.5）
    assert detail["error_code"] == "INVALID_GROUP_DIM"
    if mode == "over_limit":
        assert detail["count"] == len(dims)
        assert detail["max_dims"] == 10
    else:
        for name in named:
            assert name in detail["invalid"]

    # 保留原始查询条件不变、不执行（纯函数不改入参）
    assert rows == rows_snapshot
    assert dims == dims_snapshot


# ─────────────────────────────────────────────────────────────────────────────
# Feature: advanced-query-module, Property 9: 非数值聚合拒绝
#   For any 非数值型值字段与 sum/avg/max/min 聚合方式的组合，系统返回描述性错误并
#   标明不兼容的字段与聚合方式，保留原始查询条件不变，且不执行查询。
# ─────────────────────────────────────────────────────────────────────────────
@st.composite
def _non_numeric_case(draw):
    func = draw(st.sampled_from(["sum", "avg", "max", "min"]))
    n = draw(st.integers(min_value=0, max_value=8))
    rows = [
        {"g": "a", "label": draw(st.one_of(st.none(), st.text(min_size=1, max_size=4)))}
        for _ in range(n)
    ]
    # 强制至少一个非 None 的非数值（字符串）值，确保类型校验触发
    rows.append({"g": "a", "label": draw(st.text(min_size=1, max_size=4))})
    return rows, func


@settings(max_examples=5)
@given(_non_numeric_case())
def test_property_9_non_numeric_agg_rejected(case) -> None:
    """Feature: advanced-query-module, Property 9: 非数值聚合拒绝.

    Validates: Requirements 5.6
    """
    rows, func = case
    engine = GroupingEngine()

    rows_snapshot = copy.deepcopy(rows)

    with pytest.raises(HTTPException) as ei:
        engine.group(
            rows,
            dims=["g"],
            aggs=[{"field": "label", "func": func}],
            columns=["g", "label"],
        )

    detail = ei.value.detail
    assert ei.value.status_code == 400
    # 描述性错误标明不兼容的字段与聚合方式（R5.6）
    assert detail["error_code"] == "AGG_TYPE_MISMATCH"
    assert detail["field"] == "label"
    assert detail["agg"] == func

    # 保留原始查询条件不变、不执行
    assert rows == rows_snapshot
