"""Sprint A.2.8 — 合计公式自动适配单测 + PBT.

覆盖：
  1. 静态 data 行 → 合计正确
  2. dynamic_data 行参与合计
  3. 多个合计行（小计 + 总计）取范围正确
  4. is_total=True / row_type=subtotal/total 双判定
  5. dynamic_marker_end / header_label / dynamic_anchor 跳过
  6. None / 非数字 / 空字符串 跳过；整列空保持 None
  7. 多表 _tables schema
  8. 纯函数：不 mutate 入参
  9. 空 rows / None 入参安全
 10. PBT：合计 = sum(数据行)
"""

from __future__ import annotations

import copy
import math
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from app.services.note_total_recalc import (
    is_dynamic_data_row,
    is_total_row,
    recalc_totals_after_dynamic_expansion,
)


# ---------------------------------------------------------------------------
# 1) 基础 — 静态 data 行
# ---------------------------------------------------------------------------


def test_basic_total_recalc_after_static_rows() -> None:
    td = {
        "rows": [
            {"label": "A", "values": [100.0, 50.0], "row_type": "data"},
            {"label": "B", "values": [200.0, 30.0], "row_type": "data"},
            {"label": "合计", "values": [None, None], "row_type": "total", "is_total": True},
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    assert out["rows"][2]["values"] == [300.0, 80.0]


# ---------------------------------------------------------------------------
# 2) dynamic_data 行参与合计
# ---------------------------------------------------------------------------


def test_dynamic_data_rows_summed() -> None:
    td = {
        "rows": [
            {"label": "客户A", "values": [100.0], "row_type": "dynamic_data"},
            {"label": "客户B", "values": [200.0], "row_type": "dynamic_data"},
            {"label": "客户C", "values": [50.0], "row_type": "dynamic_data"},
            {"label": "", "values": [None], "row_type": "dynamic_marker_end"},
            {"label": "合计", "values": [None], "row_type": "total"},
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    assert out["rows"][-1]["values"] == [350.0]


# ---------------------------------------------------------------------------
# 3) 多个合计行：小计 + 总计 范围正确
# ---------------------------------------------------------------------------


def test_multi_total_rows_with_correct_ranges() -> None:
    td = {
        "rows": [
            {"label": "A1", "values": [10.0], "row_type": "data"},
            {"label": "A2", "values": [20.0], "row_type": "data"},
            {"label": "小计 A", "values": [None], "row_type": "subtotal"},
            {"label": "B1", "values": [100.0], "row_type": "data"},
            {"label": "B2", "values": [200.0], "row_type": "data"},
            {"label": "小计 B", "values": [None], "row_type": "subtotal"},
            {"label": "总计", "values": [None], "row_type": "total", "is_total": True},
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    rows = out["rows"]
    assert rows[2]["values"] == [30.0]    # 小计 A = 10 + 20
    assert rows[5]["values"] == [300.0]   # 小计 B = 100 + 200
    # 总计 = 上一个合计行（小计 B）之后到本行之前 = 无数据行 → None
    # 但等价于「整列无数据」 → None
    assert rows[6]["values"] == [None]


def test_total_after_subtotal_uses_subtotal_only_range() -> None:
    """小计 / 总计 范围按「上一个合计行之后到当前合计行之前」严格计算."""
    td = {
        "rows": [
            {"label": "A1", "values": [10.0], "row_type": "data"},
            {"label": "小计 A", "values": [None], "row_type": "subtotal"},
            {"label": "B1", "values": [20.0], "row_type": "data"},
            {"label": "B2", "values": [30.0], "row_type": "data"},
            {"label": "总计", "values": [None], "row_type": "total"},
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    assert out["rows"][1]["values"] == [10.0]
    # 总计 = B1 + B2 = 50（不重复加 A1，因为已被「小计 A」边界切断）
    assert out["rows"][4]["values"] == [50.0]


# ---------------------------------------------------------------------------
# 4) is_total / row_type 双判定
# ---------------------------------------------------------------------------


def test_is_total_via_legacy_is_total_field() -> None:
    """is_total=True（无 row_type）也算合计行."""
    td = {
        "rows": [
            {"label": "A", "values": [100.0]},
            {"label": "合计", "values": [None], "is_total": True},
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    assert out["rows"][1]["values"] == [100.0]


def test_is_total_via_row_type_subtotal() -> None:
    """row_type=subtotal 也算合计行."""
    td = {
        "rows": [
            {"label": "A", "values": [100.0], "row_type": "data"},
            {"label": "小计", "values": [None], "row_type": "subtotal"},
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    assert out["rows"][1]["values"] == [100.0]


# ---------------------------------------------------------------------------
# 5) skip row_types
# ---------------------------------------------------------------------------


def test_skip_header_label_and_anchor_in_sum() -> None:
    td = {
        "rows": [
            {"label": "----", "values": [None], "row_type": "header_label"},
            {"label": "anchor", "values": [None], "row_type": "dynamic_anchor"},
            {"label": "客户A", "values": [100.0], "row_type": "dynamic_data"},
            {"label": "", "values": [None], "row_type": "dynamic_marker_end"},
            {"label": "合计", "values": [None], "row_type": "total"},
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    assert out["rows"][-1]["values"] == [100.0]


# ---------------------------------------------------------------------------
# 6) None / 非数字 / 空字符串 / 整列空
# ---------------------------------------------------------------------------


def test_none_and_invalid_values_skipped() -> None:
    td = {
        "rows": [
            {"label": "A", "values": [None, "abc"], "row_type": "data"},
            {"label": "B", "values": [100.0, ""], "row_type": "data"},
            {"label": "C", "values": [50.0, 30.0], "row_type": "data"},
            {"label": "合计", "values": [None, None], "row_type": "total"},
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    # col 0: 100 + 50 = 150
    # col 1: 30 (其他都是无效)
    assert out["rows"][-1]["values"] == [150.0, 30.0]


def test_empty_column_stays_none() -> None:
    td = {
        "rows": [
            {"label": "A", "values": [100.0, None], "row_type": "data"},
            {"label": "B", "values": [200.0, None], "row_type": "data"},
            {"label": "合计", "values": [None, None], "row_type": "total"},
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    # col 1 全是 None → 保持 None（不强制 0）
    assert out["rows"][-1]["values"] == [300.0, None]


# ---------------------------------------------------------------------------
# 7) 多表 _tables
# ---------------------------------------------------------------------------


def test_multi_tables_each_recalc() -> None:
    td = {
        "_tables": [
            {
                "name": "T1",
                "rows": [
                    {"label": "A", "values": [10.0], "row_type": "data"},
                    {"label": "合计", "values": [None], "row_type": "total"},
                ],
            },
            {
                "name": "T2",
                "rows": [
                    {"label": "B", "values": [20.0], "row_type": "data"},
                    {"label": "合计", "values": [None], "row_type": "total"},
                ],
            },
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    assert out["_tables"][0]["rows"][1]["values"] == [10.0]
    assert out["_tables"][1]["rows"][1]["values"] == [20.0]
    # 顶层 rows 镜像首张表
    assert out["rows"] == out["_tables"][0]["rows"]


# ---------------------------------------------------------------------------
# 8) 纯函数 — 不 mutate 入参
# ---------------------------------------------------------------------------


def test_pure_function_does_not_mutate_input() -> None:
    td = {
        "rows": [
            {"label": "A", "values": [10.0], "row_type": "data"},
            {"label": "合计", "values": [None], "row_type": "total"},
        ],
    }
    snapshot = copy.deepcopy(td)
    _ = recalc_totals_after_dynamic_expansion(td)
    assert td == snapshot


# ---------------------------------------------------------------------------
# 9) 边界
# ---------------------------------------------------------------------------


def test_none_or_non_dict_returns_empty() -> None:
    assert recalc_totals_after_dynamic_expansion(None) == {}
    assert recalc_totals_after_dynamic_expansion("not a dict") == {}  # type: ignore[arg-type]


def test_no_total_rows_passthrough_unchanged() -> None:
    td = {"rows": [{"label": "A", "values": [10.0], "row_type": "data"}]}
    out = recalc_totals_after_dynamic_expansion(td)
    assert out["rows"][0]["values"] == [10.0]


def test_no_data_rows_total_stays_none() -> None:
    td = {"rows": [{"label": "合计", "values": [None], "row_type": "total"}]}
    out = recalc_totals_after_dynamic_expansion(td)
    # i=0 时不重算（没有 prev rows）
    assert out["rows"][0]["values"] == [None]


def test_decimal_values_preserved_as_decimal() -> None:
    """Decimal 输入 → 输出仍是 Decimal（保持精度）."""
    td = {
        "rows": [
            {"label": "A", "values": [Decimal("100.50")], "row_type": "data"},
            {"label": "B", "values": [Decimal("200.25")], "row_type": "data"},
            {"label": "合计", "values": [None], "row_type": "total"},
        ],
    }
    out = recalc_totals_after_dynamic_expansion(td)
    total = out["rows"][2]["values"][0]
    assert isinstance(total, Decimal)
    assert total == Decimal("300.75")


# ---------------------------------------------------------------------------
# 10) Helpers — is_total_row / is_dynamic_data_row
# ---------------------------------------------------------------------------


def test_is_total_row_helpers() -> None:
    assert is_total_row({"is_total": True}) is True
    assert is_total_row({"row_type": "total"}) is True
    assert is_total_row({"row_type": "subtotal"}) is True
    assert is_total_row({"row_type": "data"}) is False
    assert is_total_row({}) is False
    assert is_total_row(None) is False  # type: ignore[arg-type]


def test_is_dynamic_data_row_helpers() -> None:
    assert is_dynamic_data_row({"row_type": "data"}) is True
    assert is_dynamic_data_row({"row_type": "dynamic_data"}) is True
    assert is_dynamic_data_row({"row_type": "header_label"}) is False
    assert is_dynamic_data_row({"row_type": "dynamic_anchor"}) is False
    assert is_dynamic_data_row({"row_type": "dynamic_marker_end"}) is False
    assert is_dynamic_data_row({"is_total": True}) is False
    assert is_dynamic_data_row({"row_type": "total"}) is False
    assert is_dynamic_data_row({}) is True  # 旧 schema 兼容


# ---------------------------------------------------------------------------
# 11) PBT — Validates: Requirements R1.1 / Sprint A.2.8 / CI-5
# ---------------------------------------------------------------------------


_finite_floats = st.floats(
    min_value=-1e9,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
).map(lambda x: round(x, 2))


@given(values=st.lists(_finite_floats, min_size=0, max_size=15))
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_pbt_total_equals_sum_of_data_rows(values: list[float]) -> None:
    """PBT：total = sum(data 行 col 0)（误差 ≤ 1e-6）."""
    rows = [
        {"label": f"row_{i}", "values": [v], "row_type": "dynamic_data"}
        for i, v in enumerate(values)
    ]
    rows.append({"label": "合计", "values": [None], "row_type": "total"})

    out = recalc_totals_after_dynamic_expansion({"rows": rows})

    expected = sum(values) if values else None
    actual = out["rows"][-1]["values"][0]
    if expected is None:
        assert actual is None
    else:
        assert math.isclose(float(actual), expected, abs_tol=1e-6)


@given(
    values_a=st.lists(_finite_floats, min_size=0, max_size=8),
    values_b=st.lists(_finite_floats, min_size=0, max_size=8),
)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_pbt_subtotals_partition_total(
    values_a: list[float], values_b: list[float]
) -> None:
    """PBT：小计 A + 小计 B = 总计（数学等价）."""
    rows: list[dict] = []
    for i, v in enumerate(values_a):
        rows.append({"label": f"a{i}", "values": [v], "row_type": "data"})
    rows.append({"label": "小计 A", "values": [None], "row_type": "subtotal"})
    for i, v in enumerate(values_b):
        rows.append({"label": f"b{i}", "values": [v], "row_type": "data"})
    rows.append({"label": "小计 B", "values": [None], "row_type": "subtotal"})

    out = recalc_totals_after_dynamic_expansion({"rows": rows})

    sub_a = out["rows"][len(values_a)]["values"][0]
    sub_b = out["rows"][-1]["values"][0]

    expect_a = sum(values_a) if values_a else None
    expect_b = sum(values_b) if values_b else None

    if expect_a is None:
        assert sub_a is None
    else:
        assert math.isclose(float(sub_a), expect_a, abs_tol=1e-6)
    if expect_b is None:
        assert sub_b is None
    else:
        assert math.isclose(float(sub_b), expect_b, abs_tol=1e-6)
