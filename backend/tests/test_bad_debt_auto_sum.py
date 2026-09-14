# Feature: workpaper-bad-debt-nested-structure — Task 2.6 AutoSumEngine 单元测试（边界）
"""AutoSumEngine 边界单元测试：

空子行 / 单子行 / 负数金额 / None 混合 / Parent 无 Child 允许直接编辑（不强制清零）。

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 10.3
"""

from __future__ import annotations

from decimal import Decimal

from app.schemas.bad_debt_schemas import RowAmounts
from app.services.bad_debt_auto_sum import AutoSumEngine

_COLUMNS = AutoSumEngine.AMOUNT_COLUMNS


def _amounts(**kwargs) -> RowAmounts:
    return RowAmounts(**kwargs)


def test_amount_columns_are_13():
    """金额列恰好 13 个：amount_b ~ amount_n。"""
    assert _COLUMNS == [f"amount_{c}" for c in "bcdefghijklmn"]
    assert len(_COLUMNS) == 13


# ─── 空子行 ──────────────────────────────────────────────────────────────────


def test_sum_children_empty_returns_all_none():
    """无子行：每一列汇总返回 None（不返回 0）。"""
    result = AutoSumEngine.sum_children([])
    for col in _COLUMNS:
        assert getattr(result, col) is None, f"空子行列 {col} 应为 None"


def test_sum_parents_empty_returns_all_none():
    """无父行：合计每列 None。"""
    result = AutoSumEngine.sum_parents([])
    for col in _COLUMNS:
        assert getattr(result, col) is None


# ─── 单子行 ──────────────────────────────────────────────────────────────────


def test_sum_children_single_row_equals_itself():
    """单子行：父行各列等于该子行的值（量化两位小数）。"""
    child = _amounts(amount_e=Decimal("100.00"), amount_k=Decimal("250.50"),
                     amount_n=Decimal("99.99"))
    result = AutoSumEngine.sum_children([child])
    assert result.amount_e == Decimal("100.00")
    assert result.amount_k == Decimal("250.50")
    assert result.amount_n == Decimal("99.99")
    # 未填列保持 None
    assert result.amount_b is None
    assert result.amount_f is None


# ─── 负数金额 ────────────────────────────────────────────────────────────────


def test_sum_children_negative_amounts():
    """负数金额（如转回/核销减项）正确累加。"""
    c1 = _amounts(amount_f=Decimal("500.00"), amount_h=Decimal("-100.00"))
    c2 = _amounts(amount_f=Decimal("300.00"), amount_h=Decimal("-50.00"))
    result = AutoSumEngine.sum_children([c1, c2])
    assert result.amount_f == Decimal("800.00")
    assert result.amount_h == Decimal("-150.00")


def test_sum_children_mixed_sign_cancels_to_zero():
    """正负相抵为 0 时返回 0.00（有值列，区别于全 None）。"""
    c1 = _amounts(amount_g=Decimal("100.00"))
    c2 = _amounts(amount_g=Decimal("-100.00"))
    result = AutoSumEngine.sum_children([c1, c2])
    assert result.amount_g == Decimal("0.00")
    assert result.amount_g is not None


# ─── None 混合 ───────────────────────────────────────────────────────────────


def test_sum_children_none_treated_as_zero():
    """部分行某列为 None：视作 0 参与，结果非 None。"""
    c1 = _amounts(amount_e=Decimal("100.00"))
    c2 = _amounts(amount_e=None, amount_k=Decimal("200.00"))
    result = AutoSumEngine.sum_children([c1, c2])
    assert result.amount_e == Decimal("100.00")  # 100 + 0
    assert result.amount_k == Decimal("200.00")  # 0 + 200


def test_sum_children_all_none_column_returns_none():
    """某列在所有子行均为 None：该列汇总 None（区分无数据与零）。"""
    c1 = _amounts(amount_e=Decimal("100.00"))
    c2 = _amounts(amount_e=Decimal("50.00"))
    result = AutoSumEngine.sum_children([c1, c2])
    # amount_e 有值
    assert result.amount_e == Decimal("150.00")
    # amount_b 两行均 None → None
    assert result.amount_b is None


# ─── Parent 无 Child 允许直接编辑（不强制清零）──────────────────────────────


def test_parent_without_children_amounts_preserved():
    """Parent 无 Child：直接持有的金额保持原值，不被强制清零。

    AutoSumEngine 仅在被显式调用 sum_children 时计算；无子行时父行金额由调用方
    （NestedTableService）直接保留——本测试验证引擎不会把"无子行"误判为"清零"。
    Requirements: 3.5
    """
    # 模拟：父行无子行，调用方不应调用 sum_children 覆盖，父值应保持
    parent_direct = _amounts(amount_e=Decimal("888.88"), amount_n=Decimal("888.88"))
    # 平衡校验仍可对直接编辑的父行运作
    check = AutoSumEngine.validate_balance_formula(parent_direct)
    # E=888.88, 其余增减项 None=0 → expected_n = 888.88
    assert check.expected_n == Decimal("888.88")
    assert check.actual_n == Decimal("888.88")
    assert check.is_balanced is True


# ─── 平衡公式边界 ────────────────────────────────────────────────────────────


def test_balance_formula_balanced():
    """N = E+F+G-H-I-J+L+M 恰好相等 → is_balanced True。"""
    row = _amounts(
        amount_e=Decimal("100.00"), amount_f=Decimal("50.00"), amount_g=Decimal("10.00"),
        amount_h=Decimal("20.00"), amount_i=Decimal("5.00"), amount_j=Decimal("3.00"),
        amount_l=Decimal("2.00"), amount_m=Decimal("1.00"),
        amount_n=Decimal("135.00"),  # 100+50+10-20-5-3+2+1 = 135
    )
    check = AutoSumEngine.validate_balance_formula(row)
    assert check.expected_n == Decimal("135.00")
    assert check.actual_n == Decimal("135.00")
    assert check.diff == Decimal("0.00")
    assert check.is_balanced is True


def test_balance_formula_unbalanced():
    """差额 >= 0.01 → is_balanced False。"""
    row = _amounts(
        amount_e=Decimal("100.00"),
        amount_n=Decimal("99.00"),  # expected 100, diff 1.00
    )
    check = AutoSumEngine.validate_balance_formula(row)
    assert check.expected_n == Decimal("100.00")
    assert check.actual_n == Decimal("99.00")
    assert check.diff == Decimal("1.00")
    assert check.is_balanced is False


def test_balance_formula_within_tolerance():
    """差额 < 0.01（如 0.00）仍视为平衡。"""
    row = _amounts(amount_e=Decimal("100.00"), amount_n=Decimal("100.00"))
    check = AutoSumEngine.validate_balance_formula(row)
    assert check.is_balanced is True


def test_balance_formula_all_none_is_zero_balanced():
    """全 None 行：expected=actual=0，视为平衡。"""
    row = _amounts()
    check = AutoSumEngine.validate_balance_formula(row)
    assert check.expected_n == Decimal("0.00")
    assert check.actual_n == Decimal("0.00")
    assert check.is_balanced is True
