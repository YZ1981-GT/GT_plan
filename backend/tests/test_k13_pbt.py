"""K13 营业外支出 公式引擎 PBT（CP-K13-01 ~ CP-K13-05）

Properties:
- CP-K13-01: 审定数 = 未审 + AJE + RJE
- CP-K13-02: 支出类发生额 = 借方发生 - 贷方发生（6711借方科目）
- CP-K13-03: 同比变动率 = (本期 - 上期) / 上期
- CP-K13-04: 占比 = 单项 / 合计
- CP-K13-05: 合计行恒等 SUM

镜像自 useK13FormulaEngine.ts（前端纯函数），Python mirror 在 k13_formula_mirror.py。
max_examples=5（项目 PBT 约定）。

**Validates: Requirements 2.3-2.4, 5.1-5.3, 6.3-6.7**
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from .k13_formula_mirror import (
    calc_audited_amount,
    calc_income_statement_occurrence,
    calc_proportion,
    calc_subtotal,
    calc_yoy_change,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 策略定义
# ═══════════════════════════════════════════════════════════════════════════════

_amount_st = st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False)
_positive_st = st.floats(min_value=0.01, max_value=1e12, allow_nan=False, allow_infinity=False)
_nonzero_st = st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False).filter(lambda x: x != 0)
_arr_st = st.lists(_amount_st, min_size=0, max_size=50)


# ═══════════════════════════════════════════════════════════════════════════════
# CP-K13-01: 审定数公式链
# **Validates: Requirements 2.3**
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5, deadline=None)
@given(
    u=_amount_st,
    a=_amount_st,
    r=_amount_st,
)
def test_cp_k13_01_audited_amount(u: float, a: float, r: float) -> None:
    """CP-K13-01: 审定数 = 未审 + AJE + RJE"""
    result = calc_audited_amount(u, a, r)
    assert result == pytest.approx(u + a + r, rel=1e-9)


# ═══════════════════════════════════════════════════════════════════════════════
# CP-K13-02: 损益类发生额（借-贷）
# **Validates: Requirements 2.4**
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5, deadline=None)
@given(
    dr=st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False),
    cr=st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False),
)
def test_cp_k13_02_income_statement_occurrence(dr: float, cr: float) -> None:
    """CP-K13-02: 支出类发生额 = 借方发生 - 贷方发生（6711借方科目）"""
    result = calc_income_statement_occurrence(dr, cr)
    assert result == pytest.approx(dr - cr, rel=1e-9)


# ═══════════════════════════════════════════════════════════════════════════════
# CP-K13-03: 同比变动率
# **Validates: Requirements 6.5**
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5, deadline=None)
@given(
    current=_amount_st,
    prior=_nonzero_st,
)
def test_cp_k13_03_yoy_change(current: float, prior: float) -> None:
    """CP-K13-03: 同比变动率 = (本期 - 上期) / 上期；上期≠0"""
    result = calc_yoy_change(current, prior)
    expected = (current - prior) / prior
    assert result == pytest.approx(expected, rel=1e-9)


@settings(max_examples=5, deadline=None)
@given(
    current=_amount_st,
)
def test_cp_k13_03_yoy_change_zero_prior(current: float) -> None:
    """CP-K13-03: 上期为0时返回None"""
    result = calc_yoy_change(current, 0.0)
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# CP-K13-04: 占比公式
# **Validates: Requirements 6.6**
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5, deadline=None)
@given(
    item=_amount_st,
    total=_nonzero_st,
)
def test_cp_k13_04_proportion(item: float, total: float) -> None:
    """CP-K13-04: 占比 = 单项 / 合计；合计≠0"""
    result = calc_proportion(item, total)
    expected = item / total
    assert result == pytest.approx(expected, rel=1e-9)


@settings(max_examples=5, deadline=None)
@given(
    item=_amount_st,
)
def test_cp_k13_04_proportion_zero_total(item: float) -> None:
    """CP-K13-04: 合计为0时返回None"""
    result = calc_proportion(item, 0.0)
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# CP-K13-05: 合计行恒等
# **Validates: Requirements 6.7**
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5, deadline=None)
@given(
    arr=_arr_st,
)
def test_cp_k13_05_subtotal(arr: list[float]) -> None:
    """CP-K13-05: 合计行 = SUM(数组全部元素)"""
    result = calc_subtotal(arr)
    expected = sum(arr)
    assert result == pytest.approx(expected, rel=1e-9)
