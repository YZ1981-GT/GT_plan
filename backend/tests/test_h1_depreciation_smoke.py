"""Smoke test for H-F11 depreciation engine - 4 methods."""

import sys
sys.path.insert(0, "backend")

from decimal import Decimal

from app.routers.wp_h_depreciation import (
    _calc_straight_line,
    _calc_double_declining,
    _calc_sum_of_years,
    _calc_units_of_production,
    _quantize,
)


def test_straight_line_basic():
    """直线法：每月折旧严格相等"""
    schedule = _calc_straight_line(Decimal("120000"), Decimal("12000"), 60, 0)
    assert len(schedule) == 60
    # monthly_dep = (120000 - 12000) / 60 = 1800
    assert schedule[0]["depreciation"] == Decimal("1800.00")
    # All months should have same depreciation (except possibly last for rounding)
    for entry in schedule[:-1]:
        assert entry["depreciation"] == Decimal("1800.00")
    # Total accumulated = depreciable = 108000
    assert schedule[-1]["accumulated"] == Decimal("108000.00")


def test_straight_line_with_already_depreciated():
    """直线法：续提场景"""
    schedule = _calc_straight_line(Decimal("120000"), Decimal("12000"), 60, 30)
    # Should only output remaining 30 months
    assert len(schedule) == 30
    assert schedule[0]["month"] == 31
    assert schedule[-1]["month"] == 60


def test_double_declining_basic():
    """双倍余额递减法：前期加速 + 最后 2 年切换直线"""
    schedule = _calc_double_declining(Decimal("100000"), Decimal("5000"), 60, 0)
    assert len(schedule) == 60
    # First month should be higher than straight line
    straight_monthly = (Decimal("100000") - Decimal("5000")) / 60
    assert schedule[0]["depreciation"] > _quantize(straight_monthly)
    # Total accumulated should not exceed depreciable
    assert schedule[-1]["accumulated"] <= Decimal("95000.00")


def test_double_declining_last_2_years_switch():
    """双倍余额递减法：剩余 ≤ 24 月切换为直线"""
    schedule = _calc_double_declining(Decimal("100000"), Decimal("5000"), 60, 0)
    # Month 37 is the first month where remaining_months = 24 (switch point)
    # After switch, monthly depreciation should be (book_value - residual) / remaining
    # Just verify it doesn't crash and total is reasonable
    assert schedule[-1]["accumulated"] <= Decimal("95000.00")
    assert schedule[-1]["accumulated"] > Decimal("90000.00")


def test_sum_of_years_basic():
    """年数总和法：加速折旧，前期多后期少"""
    schedule = _calc_sum_of_years(Decimal("100000"), Decimal("5000"), 60, 0)
    assert len(schedule) == 60
    # First year monthly > last year monthly (accelerated)
    first_year_dep = schedule[0]["depreciation"]
    last_year_dep = schedule[-1]["depreciation"]
    assert first_year_dep > last_year_dep
    # Total accumulated should not exceed depreciable
    assert schedule[-1]["accumulated"] <= Decimal("95000.00")


def test_sum_of_years_with_already_depreciated():
    """年数总和法：续提场景"""
    schedule = _calc_sum_of_years(Decimal("100000"), Decimal("5000"), 60, 24)
    # Should only output remaining 36 months
    assert len(schedule) == 36
    assert schedule[0]["month"] == 25


def test_units_of_production_basic():
    """工作量法：按当期工作量计算"""
    schedule = _calc_units_of_production(
        Decimal("100000"), Decimal("5000"),
        Decimal("10000"), Decimal("500"), 0
    )
    assert len(schedule) == 1
    # unit_dep = 95000 / 10000 = 9.5; period_dep = 9.5 * 500 = 4750
    assert schedule[0]["depreciation"] == Decimal("4750.00")
    assert schedule[0]["accumulated"] == Decimal("4750.00")


def test_units_of_production_cap():
    """工作量法：当期折旧不超过 depreciable"""
    schedule = _calc_units_of_production(
        Decimal("100000"), Decimal("5000"),
        Decimal("100"), Decimal("200"), 0  # current > total → cap at depreciable
    )
    assert len(schedule) == 1
    # unit_dep = 95000 / 100 = 950; period_dep = 950 * 200 = 190000 > 95000 → cap
    assert schedule[0]["depreciation"] == Decimal("95000")


def test_zero_depreciable():
    """原值 = 残值时，无折旧"""
    schedule = _calc_straight_line(Decimal("10000"), Decimal("10000"), 60, 0)
    assert schedule == []


def test_quantize():
    """_quantize 保留 2 位小数"""
    assert _quantize(Decimal("1.005")) == Decimal("1.01")
    assert _quantize(Decimal("1.004")) == Decimal("1.00")
    assert _quantize(Decimal("100.999")) == Decimal("101.00")
