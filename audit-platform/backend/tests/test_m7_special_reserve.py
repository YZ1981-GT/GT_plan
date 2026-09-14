"""
集成测试 — M7 专项储备 计提引擎 + 公式验证

Spec: .kiro/specs/m7-special-reserve/ Task 7.2
Requirements: 4.1-4.6, 5.1

科目：4201 专项储备（贷方/权益类！期末=期初+贷方-借方）
"""
import pytest

from app.services.m7_special_reserve_service import (
    calc_accrual_by_output,
    calc_accrual_by_revenue,
    calc_accrual_diff,
    run_accrual_test,
)
from app.routers.wp_render_strategies._m7_special_reserve import validate_equity_formula


# ═══ calc_accrual_by_output ═══════════════════════════════════════════════════


class TestCalcAccrualByOutput:
    def test_empty_tiers(self):
        assert calc_accrual_by_output([]) == 0.0

    def test_single_tier(self):
        # 100万吨 × 5元/吨 = 500万
        assert calc_accrual_by_output([{"output": 1_000_000, "rate": 5}]) == 5_000_000

    def test_multiple_tiers(self):
        # 煤矿分档：100万吨×5 + 50万吨×4 = 500万+200万=700万
        tiers = [
            {"output": 1_000_000, "rate": 5},
            {"output": 500_000, "rate": 4},
        ]
        assert calc_accrual_by_output(tiers) == 7_000_000

    def test_zero_output_tier(self):
        tiers = [{"output": 0, "rate": 5}, {"output": 1000, "rate": 3}]
        assert calc_accrual_by_output(tiers) == 3000

    def test_zero_rate_tier(self):
        tiers = [{"output": 1000, "rate": 0}]
        assert calc_accrual_by_output(tiers) == 0


# ═══ calc_accrual_by_revenue ═══════════════════════════════════════════════════


class TestCalcAccrualByRevenue:
    def test_basic(self):
        # 1亿 × 1.5% = 150万
        assert calc_accrual_by_revenue(100_000_000, 0.015) == 1_500_000

    def test_zero_revenue(self):
        assert calc_accrual_by_revenue(0, 0.02) == 0

    def test_zero_rate(self):
        assert calc_accrual_by_revenue(100_000_000, 0) == 0

    def test_construction(self):
        # 建筑施工：5000万造价×2%=100万
        assert calc_accrual_by_revenue(50_000_000, 0.02) == 1_000_000


# ═══ calc_accrual_diff ════════════════════════════════════════════════════════


class TestCalcAccrualDiff:
    def test_underprovided_positive(self):
        # 应计150万 - 账面100万 = +50万 (少计提)
        diff = calc_accrual_diff(1_500_000, 1_000_000)
        assert diff == 500_000
        assert diff > 0  # 正差=少提=风险

    def test_overprovided_negative(self):
        # 应计100万 - 账面150万 = -50万 (多计提)
        diff = calc_accrual_diff(1_000_000, 1_500_000)
        assert diff == -500_000
        assert diff < 0  # 负差=多提

    def test_exact_match(self):
        assert calc_accrual_diff(2_000_000, 2_000_000) == 0

    def test_direction_est_minus_booked(self):
        assert calc_accrual_diff(500, 300) == 200


# ═══ run_accrual_test ═════════════════════════════════════════════════════════


class TestRunAccrualTest:
    def test_output_mode(self):
        params = {
            "method": "output",
            "tiers": [{"output": 1000, "rate": 5}, {"output": 500, "rate": 4}],
            "booked": 6000,
        }
        result = run_accrual_test(params)
        assert result["method"] == "output"
        assert result["estimated"] == 7000  # 1000×5+500×4
        assert result["booked"] == 6000
        assert result["diff"] == 1000  # 应计-账面=少提
        assert result["abs_diff"] == 1000

    def test_revenue_mode(self):
        params = {
            "method": "revenue",
            "revenue": 10_000_000,
            "rate": 0.015,
            "booked": 150_000,
        }
        result = run_accrual_test(params)
        assert result["method"] == "revenue"
        assert result["estimated"] == 150_000
        assert result["diff"] == 0

    def test_threshold_exceeded(self):
        params = {
            "method": "output",
            "tiers": [{"output": 1000, "rate": 10}],
            "booked": 5000,
            "threshold": 1000,
        }
        result = run_accrual_test(params)
        assert result["estimated"] == 10000
        assert result["diff"] == 5000
        assert result["exceed_threshold"] is True

    def test_threshold_not_exceeded(self):
        params = {
            "method": "output",
            "tiers": [{"output": 1000, "rate": 5}],
            "booked": 4500,
            "threshold": 1000,
        }
        result = run_accrual_test(params)
        assert result["diff"] == 500
        assert result["exceed_threshold"] is False


# ═══ validate_equity_formula ══════════════════════════════════════════════════


class TestValidateEquityFormula:
    def test_correct_rows_pass(self):
        """权益类贷方：期末=期初+贷方-借方"""
        rows = [
            {"row_key": "r1", "begin": 1000, "credit": 500, "debit": 200, "end_balance": 1300},
            {"row_key": "r2", "begin": 0, "credit": 100, "debit": 0, "end_balance": 100},
        ]
        errors = validate_equity_formula(rows)
        assert errors == []

    def test_incorrect_row_detected(self):
        """错误行：1000+500-200应=1300，但给了1500"""
        rows = [
            {"row_key": "r1", "begin": 1000, "credit": 500, "debit": 200, "end_balance": 1500},
        ]
        errors = validate_equity_formula(rows)
        assert len(errors) == 1
        assert errors[0]["row_key"] == "r1"
        assert errors[0]["expected_end"] == 1300
        assert errors[0]["actual_end"] == 1500

    def test_empty_rows(self):
        assert validate_equity_formula([]) == []

    def test_tolerance(self):
        """差异在0.01以内视为正确"""
        rows = [
            {"row_key": "r1", "begin": 1000, "credit": 500, "debit": 200, "end_balance": 1300.005},
        ]
        errors = validate_equity_formula(rows)
        assert errors == []
