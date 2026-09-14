# Feature: workpaper-bad-debt-nested-structure, Property 1-4: AutoSumEngine 三级汇总/平衡/精度
"""AutoSumEngine 纯计算模块的 Property-Based Tests（hypothesis, max_examples=5）。

- Property 1: 父行汇总等于子行合计      (Validates Requirements 3.1, 3.3)
- Property 2: 合计行等于所有父行合计    (Validates Requirements 3.2, 3.3)
- Property 3: 平衡公式不变量            (Validates Requirements 3.4)
- Property 4: Decimal 精度保持          (Validates Requirements 3.6, 10.3)
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.schemas.bad_debt_schemas import RowAmounts
from app.services.bad_debt_auto_sum import AutoSumEngine

_COLUMNS = AutoSumEngine.AMOUNT_COLUMNS  # amount_b ~ amount_n (13 列)


# ─── 生成策略 ────────────────────────────────────────────────────────────────

# 单个金额：Decimal，恰好 2 位小数，范围适中以保证逐列累加后仍落在 NUMERIC(18,2) 内
st_decimals = st.decimals(
    min_value=Decimal("-1000000.00"),
    max_value=Decimal("1000000.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

# 单元格：None 或一个 2 位小数 Decimal（模拟 None 混合分布）
st_cell = st.one_of(st.none(), st_decimals)


@st.composite
def st_row_amounts(draw) -> RowAmounts:
    """生成一个 RowAmounts（13 列，每列 None 或 2 位小数）。"""
    values = {col: draw(st_cell) for col in _COLUMNS}
    return RowAmounts(**values)


# 子行集合：0~6 行（含空列表边界）
st_child_rows = st.lists(st_row_amounts(), min_size=0, max_size=6)
# 父行集合：0~4 行
st_parent_rows = st.lists(st_row_amounts(), min_size=0, max_size=4)


def _manual_column_sum(rows: list[RowAmounts], col: str) -> Decimal | None:
    """参考实现：None 视作 0；全 None 列返回 None；否则量化两位小数。"""
    total = Decimal("0")
    has_value = False
    for row in rows:
        raw = getattr(row, col)
        if raw is None:
            continue
        has_value = True
        total += Decimal(str(raw))
    return total.quantize(Decimal("0.01")) if has_value else None


# ─── Property 1: 父行汇总等于子行合计 ───────────────────────────────────────


@given(children=st_child_rows)
@settings(max_examples=5, deadline=None)
def test_property_1_parent_equals_children_sum(children):
    """Property 1: 父行 13 列逐列等于其全部子行对应列之和。

    Validates: Requirements 3.1, 3.3
    """
    parent = AutoSumEngine.sum_children(children)
    for col in _COLUMNS:
        expected = _manual_column_sum(children, col)
        actual = getattr(parent, col)
        assert actual == expected, f"列 {col} 父汇总 {actual} != 子合计 {expected}"


# ─── Property 2: 合计行等于所有父行合计 ─────────────────────────────────────


@given(parents=st_parent_rows)
@settings(max_examples=5, deadline=None)
def test_property_2_summary_equals_parents_sum(parents):
    """Property 2: 合计行 13 列逐列等于全部父行对应列之和。

    Validates: Requirements 3.2, 3.3
    """
    summary = AutoSumEngine.sum_parents(parents)
    for col in _COLUMNS:
        expected = _manual_column_sum(parents, col)
        actual = getattr(summary, col)
        assert actual == expected, f"列 {col} 合计 {actual} != 父合计 {expected}"


# ─── Property 3: 平衡公式不变量 ─────────────────────────────────────────────


@given(row=st_row_amounts())
@settings(max_examples=5, deadline=None)
def test_property_3_balance_formula_invariant(row):
    """Property 3: expected_n = E+F+G-H-I-J+L+M，is_balanced iff |expected-actual|<0.01。

    Validates: Requirements 3.4
    """

    def v(col: str) -> Decimal:
        raw = getattr(row, col)
        return Decimal("0") if raw is None else Decimal(str(raw))

    expected_manual = (
        v("amount_e") + v("amount_f") + v("amount_g")
        - v("amount_h") - v("amount_i") - v("amount_j")
        + v("amount_l") + v("amount_m")
    ).quantize(Decimal("0.01"))
    actual_manual = v("amount_n").quantize(Decimal("0.01"))

    check = AutoSumEngine.validate_balance_formula(row)

    assert check.expected_n == expected_manual
    assert check.actual_n == actual_manual
    assert check.diff == (expected_manual - actual_manual).quantize(Decimal("0.01"))
    assert check.is_balanced == (abs(expected_manual - actual_manual) < Decimal("0.01"))


# ─── Property 4: Decimal 精度保持 ───────────────────────────────────────────


@given(children=st_child_rows)
@settings(max_examples=5, deadline=None)
def test_property_4_decimal_precision_preserved(children):
    """Property 4: 求和结果非 None 时恰好两位小数且为 Decimal（无 float 漂移）。

    Validates: Requirements 3.6, 10.3
    """
    parent = AutoSumEngine.sum_children(children)
    for col in _COLUMNS:
        val = getattr(parent, col)
        if val is None:
            continue
        assert isinstance(val, Decimal), f"列 {col} 结果非 Decimal: {type(val)}"
        # 恰好两位小数：量化后 exponent == -2
        assert val.as_tuple().exponent == -2, f"列 {col} 非两位小数: {val}"
