"""H9 租赁负债 — 集成测试：H8-H9联动 + 摊销表验证 + 公式方向校验

Spec: .kiro/specs/h9-lease-liabilities/ Task 7.2
Validates: Requirements 4.5-4.8, 8.1-8.4

覆盖：
1. H8-H9联动校验（一致 / 不一致 / 容差边界）
2. 摊销表生成（实际利率法 + 利率为0 + 末期≈0 + 验证函数）
3. 公式方向校验（负债贷方正确 / 资产方向错误应失败）
4. 现值计算（已知年金公式 / 不等额 / 利率为0）
"""

from __future__ import annotations

import pytest

from app.services.h9_lease_liabilities_service import (
    calc_present_value,
    calc_annuity_pv,
    calc_ibr,
    generate_amortization_schedule,
    validate_amortization,
    validate_h8_linkage,
    validate_formula_direction,
    LINKAGE_TOLERANCE,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. H8-H9联动校验
# Validates: Requirements 8.1-8.4
# ═══════════════════════════════════════════════════════════════════════════════


class TestH8H9Linkage:
    """H8-H9联动一致性校验 (CAS21第16条配对)"""

    def test_h8_h9_linkage_consistent(self):
        """H8=500000, direct_cost=5000, incentive=2000 → H9=497000 一致"""
        # H9 = H8 - direct_cost + incentive = 500000 - 5000 + 2000 = 497000
        result = validate_h8_linkage(
            h9_initial=497000, h8_initial=500000, direct_cost=5000, incentive=2000
        )
        assert result["is_consistent"] is True
        assert result["expected_h9"] == 497000.0
        assert result["actual_h9"] == 497000.0
        assert result["diff"] == 0.0

    def test_h8_h9_linkage_inconsistent(self):
        """H9实际490000 vs 期望497000 → 差额-7000 不一致"""
        result = validate_h8_linkage(
            h9_initial=490000, h8_initial=500000, direct_cost=5000, incentive=2000
        )
        assert result["is_consistent"] is False
        assert result["diff"] == -7000.0

    def test_h8_h9_linkage_within_tolerance(self):
        """差额±1元以内仍视为一致"""
        # expected = 500000 - 5000 + 2000 = 497000
        # actual = 497000.5 → diff = 0.5 ≤ 1.0 → 一致
        result = validate_h8_linkage(
            h9_initial=497000.5, h8_initial=500000, direct_cost=5000, incentive=2000
        )
        assert result["is_consistent"] is True
        assert abs(result["diff"]) <= LINKAGE_TOLERANCE

    def test_h8_h9_linkage_exactly_at_tolerance(self):
        """差额恰好±1元仍视为一致"""
        # expected = 497000, actual = 497001 → diff = 1.0
        result = validate_h8_linkage(
            h9_initial=497001, h8_initial=500000, direct_cost=5000, incentive=2000
        )
        assert result["is_consistent"] is True

    def test_h8_h9_linkage_just_over_tolerance(self):
        """差额刚超1元视为不一致"""
        # expected = 497000, actual = 497001.01 → diff = 1.01 > 1.0
        result = validate_h8_linkage(
            h9_initial=497001.01, h8_initial=500000, direct_cost=5000, incentive=2000
        )
        assert result["is_consistent"] is False

    def test_h8_h9_linkage_zero_costs(self):
        """无直接费用/激励时 H9应等于H8"""
        result = validate_h8_linkage(
            h9_initial=1000000, h8_initial=1000000, direct_cost=0, incentive=0
        )
        assert result["is_consistent"] is True
        assert result["diff"] == 0.0

    def test_h8_h9_linkage_large_amounts(self):
        """大额合同联动验证"""
        # H9 = 50000000 - 200000 + 100000 = 49900000
        result = validate_h8_linkage(
            h9_initial=49900000, h8_initial=50000000, direct_cost=200000, incentive=100000
        )
        assert result["is_consistent"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 摊销表生成 + 验证
# Validates: Requirements 4.5-4.8, 7.1-7.5
# ═══════════════════════════════════════════════════════════════════════════════


class TestAmortizationSchedule:
    """摊销表生成与验证（实际利率法）"""

    def test_amortization_generates_correct_schedule(self):
        """标准摊销：初始100000, 每期12000, 利率5%, 12期"""
        schedule = generate_amortization_schedule(100000, 12000, 0.05, 12)
        assert len(schedule) == 12
        assert schedule[0]["begin_balance"] == 100000
        # 最后一期期末余额精确为0（尾差调整）
        assert schedule[-1]["end_balance"] == 0

    def test_amortization_rate_zero(self):
        """利率为0：利息全部为0，纯本金偿还"""
        schedule = generate_amortization_schedule(30000, 10000, 0, 3)
        assert len(schedule) == 3
        assert all(row["interest"] == 0 for row in schedule)
        # 最后一期期末余额为0
        assert schedule[-1]["end_balance"] == 0

    def test_amortization_validation_passes(self):
        """验证函数：正确摊销表应is_valid=True, tail_diff=0"""
        schedule = generate_amortization_schedule(200000, 25000, 0.04, 10)
        result = validate_amortization(schedule)
        assert result["is_valid"] is True
        assert result["tail_diff"] == 0

    def test_amortization_first_period_interest(self):
        """首期利息 = 期初余额 × 利率"""
        schedule = generate_amortization_schedule(100000, 12000, 0.05, 12)
        expected_interest = round(100000 * 0.05, 2)
        assert schedule[0]["interest"] == expected_interest

    def test_amortization_balance_continuity(self):
        """相邻期次余额连续：本期期末 = 下期期初"""
        schedule = generate_amortization_schedule(500000, 60000, 0.06, 10)
        for i in range(len(schedule) - 1):
            assert schedule[i]["end_balance"] == schedule[i + 1]["begin_balance"]

    def test_amortization_principal_equals_payment_minus_interest(self):
        """每期本金 = 付款 - 利息（除最后一期尾差调整）"""
        schedule = generate_amortization_schedule(100000, 12000, 0.05, 12)
        # 非最后一期
        for row in schedule[:-1]:
            expected_principal = round(row["payment"] - row["interest"], 2)
            assert row["principal"] == expected_principal

    def test_amortization_total_principal_equals_initial(self):
        """总本金偿还 ≈ 初始余额"""
        initial = 200000
        schedule = generate_amortization_schedule(initial, 25000, 0.04, 10)
        total_principal = sum(row["principal"] for row in schedule)
        assert abs(total_principal - initial) < 1.0

    def test_amortization_empty_periods(self):
        """期数为0时返回空列表"""
        schedule = generate_amortization_schedule(100000, 12000, 0.05, 0)
        assert schedule == []

    def test_amortization_single_period(self):
        """单期摊销：本金=初始余额"""
        schedule = generate_amortization_schedule(50000, 55000, 0.1, 1)
        assert len(schedule) == 1
        assert schedule[0]["begin_balance"] == 50000
        assert schedule[0]["end_balance"] == 0
        # 利息=50000*0.1=5000, 本金=50000(尾差调整)
        assert schedule[0]["interest"] == 5000
        assert schedule[0]["principal"] == 50000

    def test_validate_amortization_empty(self):
        """空摊销表验证通过"""
        result = validate_amortization([])
        assert result["is_valid"] is True
        assert result["tail_diff"] == 0.0
        assert result["total_interest"] == 0.0
        assert result["total_principal"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 公式方向校验（负债类贷方 vs 资产类借方）
# Validates: Requirements 2.4
# ═══════════════════════════════════════════════════════════════════════════════


class TestFormulaDirection:
    """公式方向校验：负债类贷方 期末=期初+贷方-借方"""

    def test_liability_direction_correct(self):
        """负债贷方正确：期末=100000+20000-15000=105000"""
        result = validate_formula_direction(
            begin=100000, credit=20000, debit=15000, expected_end=105000
        )
        assert result["is_valid"] is True
        assert result["calculated_end"] == 105000.0

    def test_liability_direction_wrong(self):
        """若用资产方向(期初+借方-贷方=95000)则校验失败"""
        # 资产方向: 100000+15000-20000=95000 (错误！)
        # 正确负债方向: 100000+20000-15000=105000
        result = validate_formula_direction(
            begin=100000, credit=20000, debit=15000, expected_end=95000
        )
        assert result["is_valid"] is False
        # diff = 105000 - 95000 = 10000
        assert result["diff"] == 10000.0

    def test_liability_direction_zero_movements(self):
        """无发生额时期末=期初"""
        result = validate_formula_direction(
            begin=500000, credit=0, debit=0, expected_end=500000
        )
        assert result["is_valid"] is True

    def test_liability_direction_only_credit(self):
        """纯贷方增加（如新租赁确认）"""
        result = validate_formula_direction(
            begin=100000, credit=50000, debit=0, expected_end=150000
        )
        assert result["is_valid"] is True

    def test_liability_direction_only_debit(self):
        """纯借方减少（如偿还本金）"""
        result = validate_formula_direction(
            begin=100000, credit=0, debit=30000, expected_end=70000
        )
        assert result["is_valid"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 现值计算（PV Engine）
# Validates: Requirements 6.1-6.4
# ═══════════════════════════════════════════════════════════════════════════════


class TestPresentValueCalculations:
    """现值计算引擎验证"""

    def test_present_value_known_annuity(self):
        """等额年金现值：50000/年×10年@5% ≈ 386086.75"""
        pv = calc_present_value([50000] * 10, 0.05)
        expected = 50000 * (1 - (1.05) ** (-10)) / 0.05  # ~386086.75
        assert abs(pv - expected) < 1

    def test_annuity_pv_matches_manual(self):
        """年金公式：calc_annuity_pv vs 手动计算"""
        pv = calc_annuity_pv(50000, 0.05, 10)
        expected = 50000 * (1 - (1.05) ** (-10)) / 0.05
        assert abs(pv - expected) < 1

    def test_pv_rate_zero(self):
        """利率为0时PV = 付款之和"""
        payments = [10000, 20000, 30000]
        pv = calc_present_value(payments, 0)
        assert pv == 60000.0

    def test_annuity_pv_rate_zero(self):
        """年金PV利率为0时 = payment × periods"""
        pv = calc_annuity_pv(50000, 0, 10)
        assert pv == 500000.0

    def test_pv_empty_payments(self):
        """空付款列表PV=0"""
        pv = calc_present_value([], 0.05)
        assert pv == 0.0

    def test_annuity_pv_zero_periods(self):
        """期数为0时PV=0"""
        pv = calc_annuity_pv(50000, 0.05, 0)
        assert pv == 0.0

    def test_pv_single_payment(self):
        """单期付款折现：100000/(1.05)^1 ≈ 95238.10"""
        pv = calc_present_value([100000], 0.05)
        expected = round(100000 / 1.05, 2)
        assert abs(pv - expected) < 1

    def test_pv_vs_annuity_pv_consistency(self):
        """等额付款：calc_present_value 与 calc_annuity_pv 结果应一致"""
        payments = [50000] * 10
        pv_list = calc_present_value(payments, 0.05)
        pv_annuity = calc_annuity_pv(50000, 0.05, 10)
        assert abs(pv_list - pv_annuity) < 1

    def test_ibr_calculation(self):
        """IBR = market_rate + credit_spread + term_adjust"""
        ibr = calc_ibr(0.04, 0.015, 0.005)
        assert ibr == pytest.approx(0.06)

    def test_ibr_zero_spread(self):
        """无信用利差/期限调整时IBR=市场利率"""
        ibr = calc_ibr(0.04, 0, 0)
        assert ibr == pytest.approx(0.04)
