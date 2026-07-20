"""equity_method_service — CAS2 §44 超额亏损与 G7-16 容量口径对齐"""
from decimal import Decimal

from app.services.equity_method_service import (
    EquityMethodInput,
    calc_cas2_excess_loss,
    calc_long_term_interest_capacity,
    calculate_equity_method,
)


def test_capacity_includes_lt_receivable():
    assert calc_long_term_interest_capacity(
        Decimal("100"), Decimal("30"), Decimal("10"), Decimal("5"),
    ) == Decimal("145.00")


def test_cas2_excess_aligns_with_g716_waterfall():
    out = calc_cas2_excess_loss(
        cumulative_loss=Decimal("200"),
        investment_book=Decimal("50"),
        long_term_receivable=Decimal("30"),
        other_long_term_equity=Decimal("10"),
        estimated_liability=Decimal("0"),
    )
    assert out["capacity"] == Decimal("90.00")
    assert out["excess_loss"] == Decimal("110.00")
    assert out["reduce_investment"] == Decimal("50.00")
    assert out["reduce_long_term_receivable"] == Decimal("30.00")
    assert out["reduce_other_equity"] == Decimal("10.00")
    assert out["unrecognized_loss"] == Decimal("20.00")


def test_calculate_equity_method_absorbs_via_lt_receivable():
    # 账面 40 + 长应收 60 = 容量 100；份额亏损 150 → 确认损失 100，未确认 50
    result = calculate_equity_method(EquityMethodInput(
        subsidiary_code="A1",
        subsidiary_name="联营甲",
        parent_share_ratio=Decimal("0.5"),
        initial_investment_cost=Decimal("40"),
        opening_book_value=Decimal("40"),
        sub_net_profit=Decimal("-300"),  # 份额 -150
        long_term_receivable=Decimal("60"),
        g716_unrecognized_loss=Decimal("50"),
    ))
    assert result.is_excess_loss is True
    assert result.long_term_interest_capacity == Decimal("100.00")
    assert result.investment_income == Decimal("-100.00")
    assert result.excess_loss == Decimal("50.00")
    assert result.g716_unrecognized_loss == Decimal("50")


def test_legacy_without_lt_fields_unchanged_capacity_is_book_only():
    result = calculate_equity_method(EquityMethodInput(
        subsidiary_code="B1",
        subsidiary_name="联营乙",
        parent_share_ratio=Decimal("1"),
        initial_investment_cost=Decimal("80"),
        opening_book_value=Decimal("80"),
        sub_net_profit=Decimal("-100"),
    ))
    assert result.is_excess_loss is True
    assert result.excess_loss == Decimal("20.00")
    assert result.investment_income == Decimal("-80.00")
