"""A15 持续经营财务指标 Resolver 单元测试."""
from decimal import Decimal

import pytest

from app.services.auto_data_resolvers._going_concern import (
    assess_going_concern_risk,
    compute_ratios,
)


class TestComputeRatios:
    """纯函数 compute_ratios 测试。"""

    def test_normal_company(self):
        r = compute_ratios(
            current_assets=Decimal("500000"),
            current_liabilities=Decimal("300000"),
            inventory=Decimal("100000"),
            total_assets=Decimal("1000000"),
            total_liabilities=Decimal("600000"),
            retained_earnings=Decimal("150000"),
        )
        assert r["current_ratio"] == pytest.approx(1.6667, abs=0.001)
        assert r["quick_ratio"] == pytest.approx(1.3333, abs=0.001)
        assert r["debt_ratio"] == pytest.approx(0.6, abs=0.001)
        assert r["net_assets"] == 400000.0
        assert r["retained_earnings"] == 150000.0

    def test_zero_liabilities(self):
        r = compute_ratios(
            current_assets=Decimal("100000"),
            current_liabilities=Decimal("0"),
            inventory=Decimal("0"),
            total_assets=Decimal("100000"),
            total_liabilities=Decimal("0"),
            retained_earnings=Decimal("50000"),
        )
        assert r["current_ratio"] is None
        assert r["quick_ratio"] is None
        assert r["debt_ratio"] == 0.0

    def test_zero_assets(self):
        r = compute_ratios(
            current_assets=Decimal("0"),
            current_liabilities=Decimal("100000"),
            inventory=Decimal("0"),
            total_assets=Decimal("0"),
            total_liabilities=Decimal("100000"),
            retained_earnings=Decimal("-50000"),
        )
        assert r["current_ratio"] == 0.0
        assert r["debt_ratio"] is None
        assert r["net_assets"] == -100000.0


class TestAssessGoingConcernRisk:
    """风险等级评估纯函数测试。"""

    def test_low_risk(self):
        r = compute_ratios(
            current_assets=Decimal("500000"),
            current_liabilities=Decimal("300000"),
            inventory=Decimal("100000"),
            total_assets=Decimal("1000000"),
            total_liabilities=Decimal("600000"),
            retained_earnings=Decimal("150000"),
        )
        assert assess_going_concern_risk(r) == "low"

    def test_medium_risk_low_current_ratio(self):
        r = compute_ratios(
            current_assets=Decimal("200000"),
            current_liabilities=Decimal("300000"),
            inventory=Decimal("50000"),
            total_assets=Decimal("800000"),
            total_liabilities=Decimal("500000"),
            retained_earnings=Decimal("100000"),
        )
        # current_ratio = 0.67 < 1.0 → medium
        assert assess_going_concern_risk(r) == "medium"

    def test_high_risk_negative_net_assets(self):
        r = compute_ratios(
            current_assets=Decimal("100000"),
            current_liabilities=Decimal("500000"),
            inventory=Decimal("50000"),
            total_assets=Decimal("200000"),
            total_liabilities=Decimal("600000"),
            retained_earnings=Decimal("-300000"),
        )
        assert assess_going_concern_risk(r) == "high"

    def test_high_risk_very_low_cr(self):
        r = compute_ratios(
            current_assets=Decimal("100000"),
            current_liabilities=Decimal("300000"),
            inventory=Decimal("0"),
            total_assets=Decimal("500000"),
            total_liabilities=Decimal("400000"),
            retained_earnings=Decimal("10000"),
        )
        # current_ratio = 0.33 < 0.5 → high
        assert assess_going_concern_risk(r) == "high"

    def test_undetermined_when_no_liabilities(self):
        r = compute_ratios(
            current_assets=Decimal("100000"),
            current_liabilities=Decimal("0"),
            inventory=Decimal("0"),
            total_assets=Decimal("100000"),
            total_liabilities=Decimal("0"),
            retained_earnings=Decimal("50000"),
        )
        # current_ratio is None → undetermined
        assert assess_going_concern_risk(r) == "undetermined"
