"""财务比率计算单元测试"""

from decimal import Decimal

from app.services.financial_ratio_service import FinancialRatioService


def test_ratio_calculation():
    """基本比率计算正确"""
    r = FinancialRatioService._ratio("流动比率", Decimal("200"), Decimal("100"), "倍")
    assert r["value"] == Decimal("2.00")
    assert r["abnormal"] is False


def test_ratio_zero_denominator():
    """分母为零返回 None"""
    r = FinancialRatioService._ratio("速动比率", Decimal("100"), Decimal("0"), "倍")
    assert r["value"] is None
    assert r["note"] == "分母为零"


def test_ratio_pct():
    """百分比计算"""
    r = FinancialRatioService._ratio("资产负债率", Decimal("80"), Decimal("100"), "%", pct=True)
    assert r["value"] == Decimal("80.00")
    assert r["abnormal"] is True  # >70%


def test_ratio_current_below_one():
    """流动比率<1 标异常"""
    r = FinancialRatioService._ratio("流动比率", Decimal("50"), Decimal("100"), "倍")
    assert r["value"] == Decimal("0.50")
    assert r["abnormal"] is True
