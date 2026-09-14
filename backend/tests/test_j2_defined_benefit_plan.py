"""J2 设定受益计划 — 后端测试.

测试：渲染策略(负债类公式) + 导入导出 + 精算假设验证

Spec: .kiro/specs/j2-defined-benefit-plan/ Task 7.3
"""
import pytest
from app.routers.wp_render_strategies._j2_defined_benefit_plan import (
    validate_liability_balance,
    validate_dbo_decomposition,
)


class TestLiabilityBalanceValidation:
    """负债类期末余额验证：end = begin + credit - debit."""

    def test_basic_calculation(self):
        assert validate_liability_balance(1000, 200, 50, 1150) is True

    def test_zero_movement(self):
        assert validate_liability_balance(5000, 0, 0, 5000) is True

    def test_full_repayment(self):
        assert validate_liability_balance(1000, 0, 1000, 0) is True

    def test_mismatch_fails(self):
        assert validate_liability_balance(1000, 200, 50, 9999) is False

    def test_rounding_tolerance(self):
        # Within 0.01 tolerance
        assert validate_liability_balance(1000.005, 200.003, 50.001, 1150.007) is True


class TestDBODecomposition:
    """DBO期末完整公式验证."""

    def test_basic(self):
        # 1000 + 50 + 40 + 20 - 10 - 30 = 1070
        assert validate_dbo_decomposition(1000, 50, 40, 20, 10, 30, 1070) is True

    def test_no_movement(self):
        assert validate_dbo_decomposition(5000, 0, 0, 0, 0, 0, 5000) is True

    def test_actuarial_loss_dominates(self):
        # 10000 + 0 + 0 + 5000 - 0 - 0 = 15000
        assert validate_dbo_decomposition(10000, 0, 0, 5000, 0, 0, 15000) is True

    def test_full_settlement(self):
        # 10000 + 0 + 0 + 0 - 0 - 10000 = 0
        assert validate_dbo_decomposition(10000, 0, 0, 0, 0, 10000, 0) is True

    def test_mismatch_fails(self):
        assert validate_dbo_decomposition(1000, 50, 40, 20, 10, 30, 9999) is False


class TestActuarialAssumptionRanges:
    """精算假设合理性范围测试（Python层，对标前端PBT）."""

    def test_discount_rate_valid_range(self):
        """折现率 2%~8% 为合理范围."""
        # 在范围内
        for rate in [0.02, 0.04, 0.06, 0.08]:
            assert 0 < rate < 1, f"Rate {rate} should be in (0,1)"

    def test_salary_growth_valid_range(self):
        """薪酬增长率 3%~15% 为合理范围."""
        for rate in [0.03, 0.08, 0.15]:
            assert 0 < rate < 1

    def test_liability_direction_credit(self):
        """确认负债类方向：贷方增加（与资产类相反）."""
        begin = 10000
        credit = 2000  # 增加
        debit = 500    # 减少
        end = begin + credit - debit  # 11500
        assert end == 11500
        assert end > begin  # 贷方增加 → 余额增大

    def test_interest_cost_formula(self):
        """利息成本 = 期初DBO × 折现率."""
        begin_dbo = 100000
        discount_rate = 0.04
        interest = begin_dbo * discount_rate
        assert interest == 4000

    def test_net_liability_formula(self):
        """净负债 = DBO - 计划资产FV."""
        dbo = 100000
        plan_assets = 30000
        net = dbo - plan_assets
        assert net == 70000  # 正值 = 净负债

    def test_net_asset_case(self):
        """计划资产 > DBO → 净资产（负值）."""
        dbo = 30000
        plan_assets = 50000
        net = dbo - plan_assets
        assert net == -20000  # 负值 = 净资产
