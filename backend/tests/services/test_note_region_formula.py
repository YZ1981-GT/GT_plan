"""单测 — REGION 公式函数（Sprint A.3.1）.

Spec:    .kiro/specs/note-dynamic-tables-and-template-inheritance/ Sprint A.3.1
Design:  D1 行动态 + D4 公式 DSL — REGION('region','col', agg='sum')
Reqs:    Sprint A.3 验收 — REGION + WP 公式函数完善（CI-4 引用解析）

覆盖：
- 5 种 agg：sum / count / max / min / avg
- 边界：region 不存在 / col 不存在 / dynamic_data 0 行 / 非 dynamic_data 行被跳过
- 组合表达式：REGION + TB / REGION + REGION
- 输入校验：None / 非 dict / 非字符串 token / 非法 agg
"""

from __future__ import annotations

import pytest

from app.services.note_formula_generator import (
    exec_with_region,
    resolve_region_token,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _table_with_region(
    *,
    rows: list[dict],
    region_start: int,
    region_end: int,
    region_name: str = "客户",
    cols: list[dict] | None = None,
) -> dict:
    """构造含单个 row region 的 table_data."""
    columns_meta = cols or [
        {"id": "col_label", "label": "客户名称", "col_type": "fixed"},
        {"id": "col_amount_end", "label": "期末余额", "col_type": "fixed"},
        {"id": "col_amount_start", "label": "期初余额", "col_type": "fixed"},
    ]
    return {
        "_columns_meta": columns_meta,
        "_dynamic_regions": [
            {
                "name": region_name,
                "axis": "row",
                "start_idx": region_start,
                "end_idx": region_end,
                "expandable": True,
                "dynamic_source": "aux_balance",
            }
        ],
        "rows": rows,
    }


def _dyn_row(label: str, vals: list) -> dict:
    return {"row_type": "dynamic_data", "label": label, "values": vals}


# ===========================================================================
# 1. agg=sum 默认
# ===========================================================================


def test_region_sum_default_agg():
    """REGION('客户','col_amount_end') 默认 agg=sum."""
    td = _table_with_region(
        rows=[
            _dyn_row("客户A", [None, 100.0, 80.0]),
            _dyn_row("客户B", [None, 200.0, 150.0]),
            _dyn_row("客户C", [None, 50.0, 40.0]),
        ],
        region_start=0,
        region_end=2,
    )
    val = resolve_region_token("REGION('客户','col_amount_end')", td)
    assert val == pytest.approx(350.0)


def test_region_sum_explicit_agg():
    """REGION 显式 agg='sum'."""
    td = _table_with_region(
        rows=[
            _dyn_row("c1", [None, 10.0, 0]),
            _dyn_row("c2", [None, 20.0, 0]),
        ],
        region_start=0,
        region_end=1,
    )
    val = resolve_region_token(
        "REGION('客户','col_amount_end', agg='sum')", td
    )
    assert val == pytest.approx(30.0)


# ===========================================================================
# 2. count / max / min / avg
# ===========================================================================


def test_region_count_includes_zero_rows():
    """count 计数所有 dynamic_data 行（含 0 值，但跳过 None）."""
    td = _table_with_region(
        rows=[
            _dyn_row("c1", [None, 100.0, None]),
            _dyn_row("c2", [None, 0.0, None]),
            _dyn_row("c3", [None, None, None]),  # None 不计入
        ],
        region_start=0,
        region_end=2,
    )
    val = resolve_region_token(
        "REGION('客户','col_amount_end', agg='count')", td
    )
    assert val == 2.0


def test_region_count_zero_when_no_dynamic_rows():
    """count 在无 dynamic_data 行时返 0（不返 None）."""
    td = _table_with_region(
        rows=[{"row_type": "header_label", "label": "x", "values": [None, None, None]}],
        region_start=0,
        region_end=0,
    )
    val = resolve_region_token(
        "REGION('客户','col_amount_end', agg='count')", td
    )
    assert val == 0.0


def test_region_max():
    td = _table_with_region(
        rows=[
            _dyn_row("c1", [None, 10.0, 0]),
            _dyn_row("c2", [None, 50.0, 0]),
            _dyn_row("c3", [None, 30.0, 0]),
        ],
        region_start=0,
        region_end=2,
    )
    assert resolve_region_token(
        "REGION('客户','col_amount_end', agg='max')", td
    ) == 50.0


def test_region_min():
    td = _table_with_region(
        rows=[
            _dyn_row("c1", [None, 10.0, 0]),
            _dyn_row("c2", [None, 50.0, 0]),
            _dyn_row("c3", [None, 30.0, 0]),
        ],
        region_start=0,
        region_end=2,
    )
    assert resolve_region_token(
        "REGION('客户','col_amount_end', agg='min')", td
    ) == 10.0


def test_region_avg():
    td = _table_with_region(
        rows=[
            _dyn_row("c1", [None, 10.0, 0]),
            _dyn_row("c2", [None, 30.0, 0]),
        ],
        region_start=0,
        region_end=1,
    )
    val = resolve_region_token(
        "REGION('客户','col_amount_end', agg='avg')", td
    )
    assert val == pytest.approx(20.0)


# ===========================================================================
# 3. 边界
# ===========================================================================


def test_region_skips_non_dynamic_data_rows():
    """region 范围内的 dynamic_anchor / dynamic_marker_end 不参与聚合."""
    td = _table_with_region(
        rows=[
            {"row_type": "dynamic_anchor", "label": "锚点", "values": [None, 999, 999]},
            _dyn_row("c1", [None, 10.0, 0]),
            _dyn_row("c2", [None, 20.0, 0]),
            {"row_type": "dynamic_marker_end", "label": "", "values": [None, None, None]},
        ],
        region_start=0,
        region_end=3,
    )
    val = resolve_region_token("REGION('客户','col_amount_end')", td)
    assert val == pytest.approx(30.0)


def test_region_unknown_region_returns_none():
    td = _table_with_region(
        rows=[_dyn_row("c1", [None, 10.0, 0])],
        region_start=0,
        region_end=0,
    )
    val = resolve_region_token("REGION('NOT_EXIST','col_amount_end')", td)
    assert val is None


def test_region_unknown_col_returns_none():
    td = _table_with_region(
        rows=[_dyn_row("c1", [None, 10.0, 0])],
        region_start=0,
        region_end=0,
    )
    val = resolve_region_token("REGION('客户','NOT_EXIST_COL')", td)
    assert val is None


def test_region_no_data_sum_returns_none():
    """sum 在无有效数字时返 None（用于触发 fallback）."""
    td = _table_with_region(
        rows=[_dyn_row("c1", [None, None, None])],
        region_start=0,
        region_end=0,
    )
    val = resolve_region_token("REGION('客户','col_amount_end')", td)
    assert val is None


def test_region_invalid_agg_returns_none():
    td = _table_with_region(
        rows=[_dyn_row("c1", [None, 10.0, 0])],
        region_start=0,
        region_end=0,
    )
    val = resolve_region_token(
        "REGION('客户','col_amount_end', agg='median')", td
    )
    assert val is None


def test_region_axis_column_region_ignored():
    """axis=column 的 region 不参与 row 聚合（找不到 row region 即返 None）."""
    td = {
        "_columns_meta": [{"id": "col_amount_end", "label": "期末"}],
        "_dynamic_regions": [
            {
                "name": "客户",
                "axis": "column",
                "start_idx": 0,
                "end_idx": 0,
            }
        ],
        "rows": [_dyn_row("c1", [10.0])],
    }
    val = resolve_region_token("REGION('客户','col_amount_end')", td)
    assert val is None


def test_region_invalid_inputs():
    """None / 非 dict / 非字符串 / 非匹配 token → None."""
    assert resolve_region_token(None, {"rows": []}) is None  # type: ignore[arg-type]
    assert resolve_region_token("REGION('a','b')", None) is None
    assert resolve_region_token("REGION('a','b')", []) is None  # type: ignore[arg-type]
    assert resolve_region_token("NOT_REGION('a','b')", {"rows": []}) is None
    assert resolve_region_token("", {"rows": []}) is None


# ===========================================================================
# 4. exec_with_region — 组合表达式
# ===========================================================================


def test_exec_with_region_pure_region():
    td = _table_with_region(
        rows=[
            _dyn_row("c1", [None, 10.0, 0]),
            _dyn_row("c2", [None, 20.0, 0]),
        ],
        region_start=0,
        region_end=1,
    )
    val = exec_with_region("REGION('客户','col_amount_end')", {}, td)
    assert val == pytest.approx(30.0)


def test_exec_with_region_combine_with_tb():
    """REGION + TB 组合表达式."""
    td = _table_with_region(
        rows=[
            _dyn_row("c1", [None, 10.0, 0]),
            _dyn_row("c2", [None, 20.0, 0]),
        ],
        region_start=0,
        region_end=1,
    )
    cross = {
        "tb": {"1001": {"audited": 5.0, "unadjusted": 5.0, "opening": 0}},
        "report": {}, "notes": {}, "wp": {}, "prior": {}, "aging": {},
    }
    val = exec_with_region(
        "REGION('客户','col_amount_end') + TB('1001','期末')",
        cross, td,
    )
    assert val == pytest.approx(35.0)


def test_exec_with_region_two_regions_subtract():
    td = _table_with_region(
        rows=[
            _dyn_row("c1", [None, 100.0, 80.0]),
            _dyn_row("c2", [None, 200.0, 150.0]),
        ],
        region_start=0,
        region_end=1,
    )
    val = exec_with_region(
        "REGION('客户','col_amount_end') - REGION('客户','col_amount_start')",
        {}, td,
    )
    assert val == pytest.approx(70.0)


def test_exec_with_region_failure_propagates_none():
    """REGION 解析失败 → exec_with_region 返 None."""
    td = _table_with_region(
        rows=[_dyn_row("c1", [None, 10.0, 0])],
        region_start=0,
        region_end=0,
    )
    val = exec_with_region(
        "REGION('NOT_EXIST','col_amount_end') + TB('1001','期末')",
        {"tb": {"1001": {"audited": 5.0, "opening": 0, "unadjusted": 5.0}}},
        td,
    )
    assert val is None


def test_exec_with_region_invalid_inputs():
    assert exec_with_region(None, {}, {}) is None  # type: ignore[arg-type]
    assert exec_with_region("", {}, {}) is None
    assert exec_with_region("REGION('a','b')", {}, None) is None
