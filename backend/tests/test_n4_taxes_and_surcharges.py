"""N4 税金及附加 — 集成测试：损益类取数 + N2对应 + 跨底稿联动.

Spec: .kiro/specs/n4-taxes-and-surcharges/ Task 7.2
Validates: Requirements 2.5-2.6, 6.1-6.5, 7.1-7.4

覆盖：
1. 纯函数测试（无DB）：
   - calc_period_amount: 损益类本期发生额=借方发生-贷方发生（6403借方科目）
   - calc_audited_amount: 审定数=未审+AJE+RJE
   - calc_yoy_change: 同比变动=(本期-上期)/上期，上期为0返回None
   - calculate_surtax: 城建税及附加=(增值税+消费税)×税率
   - calculate_property_tax_by_value: 房产税从价=原值×(1-扣除比例)×1.2%
   - calculate_stamp_tax: 印花税=计税金额×适用税率
   - calculate_land_use_tax: 土地使用税=占地面积×单位税额
   - verify_expense_vs_accrual: N4费用确认 vs N2计提额交叉验证

2. 交叉验证逻辑测试（纯函数，无DB）：
   - verify_expense_vs_accrual_all_match: 所有税种匹配
   - verify_expense_vs_accrual_with_diff: 部分税种有差异

3. 方向校验测试：
   - N4使用借方-贷方（非贷方-借方，与K10相反）
   - 6403为借方科目正确处理
"""

from __future__ import annotations

import pytest

from app.services.n4_taxes_and_surcharges_service import (
    calc_audited_amount,
    calc_period_amount,
    calc_subtotal,
    calc_yoy_change,
    calculate_land_use_tax,
    calculate_property_tax_by_value,
    calculate_surtax,
    calculate_stamp_tax,
    verify_expense_vs_accrual,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 损益类公式引擎 (Requirements 7.1, 7.3, 7.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcPeriodAmount:
    """损益类本期发生额=借方发生-贷方发生（6403费用类借方科目！）

    Validates: Requirements 7.1, 7.4
    """

    def test_calc_period_amount_debit_minus_credit(self):
        """借方发生-贷方发生：1000-300=700"""
        assert calc_period_amount(1000, 300) == 700

    def test_calc_period_amount_zero(self):
        """全零"""
        assert calc_period_amount(0, 0) == 0

    def test_calc_period_amount_only_debit(self):
        """仅借方（常见：纯费用发生）: 5000-0=5000"""
        assert calc_period_amount(5000, 0) == 5000

    def test_calc_period_amount_credit_exceeds_debit(self):
        """贷方>借方（冲回超过发生，罕见）: 200-500=-300"""
        assert calc_period_amount(200, 500) == -300

    def test_calc_period_amount_large_numbers(self):
        """大数：1e9-3e8=7e8"""
        assert calc_period_amount(1e9, 3e8) == 7e8

    def test_calc_period_amount_direction_not_credit_minus_debit(self):
        """确保不是K10方向（贷方-借方）: N4是借方-贷方！"""
        debit, credit = 8000, 2000
        result = calc_period_amount(debit, credit)
        # N4损益类借方科目：借方-贷方=6000（正确）
        assert result == 6000
        # K10/K12营业收入方向：贷方-借方=负数（错误对N4而言）
        assert result != (credit - debit)


class TestCalcAuditedAmount:
    """审定数=未审+AJE+RJE

    Validates: Requirements 7.3
    """

    def test_calc_audited_amount(self):
        """基础: 1000+50+(-20)=1030"""
        assert calc_audited_amount(1000, 50, -20) == 1030

    def test_calc_audited_amount_all_zero(self):
        """全零"""
        assert calc_audited_amount(0, 0, 0) == 0

    def test_calc_audited_amount_no_adjustments(self):
        """无调整: 5000+0+0=5000"""
        assert calc_audited_amount(5000, 0, 0) == 5000

    def test_calc_audited_amount_negative_aje(self):
        """调减: 10000+(-2000)+0=8000"""
        assert calc_audited_amount(10000, -2000, 0) == 8000

    def test_calc_audited_amount_both_adjustments(self):
        """双调整: 5000+1000+(-500)=5500"""
        assert calc_audited_amount(5000, 1000, -500) == 5500


class TestCalcYoyChange:
    """同比变动=(本期-上期)/上期，上期为0返回None

    Validates: Requirements 6.5
    """

    def test_calc_yoy_change_normal(self):
        """正常增长: (1200-1000)/1000=0.2"""
        result = calc_yoy_change(1200, 1000)
        assert result == pytest.approx(0.2, abs=1e-6)

    def test_calc_yoy_change_decrease(self):
        """下降: (800-1000)/1000=-0.2"""
        result = calc_yoy_change(800, 1000)
        assert result == pytest.approx(-0.2, abs=1e-6)

    def test_calc_yoy_change_zero_prior(self):
        """上期为0返回None（避免除零）"""
        result = calc_yoy_change(1000, 0)
        assert result is None

    def test_calc_yoy_change_same(self):
        """无变动: (1000-1000)/1000=0"""
        result = calc_yoy_change(1000, 1000)
        assert result == pytest.approx(0, abs=1e-6)

    def test_calc_yoy_change_double(self):
        """翻倍: (2000-1000)/1000=1.0"""
        result = calc_yoy_change(2000, 1000)
        assert result == pytest.approx(1.0, abs=1e-6)


class TestCalcSubtotal:
    """合计行=Σ各项金额

    Validates: Requirements 6.3
    """

    def test_calc_subtotal_normal(self):
        """正常合计"""
        assert calc_subtotal([100, 200, 300]) == 600

    def test_calc_subtotal_empty(self):
        """空列表"""
        assert calc_subtotal([]) == 0

    def test_calc_subtotal_single(self):
        """单项"""
        assert calc_subtotal([500]) == 500


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 多税种测算引擎 (Requirements 4.1-4.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalculateSurtax:
    """城建税及附加=(增值税+消费税)×税率

    Validates: Requirements 4.1
    """

    def test_calculate_surtax(self):
        """城建税市区7%: (100000+0)×0.07=7000"""
        assert calculate_surtax(100000, 0, 0.07) == pytest.approx(7000, abs=0.01)

    def test_calculate_surtax_with_consumption_tax(self):
        """含消费税: (100000+20000)×0.07=8400"""
        assert calculate_surtax(100000, 20000, 0.07) == pytest.approx(8400, abs=0.01)

    def test_calculate_surtax_education_3_percent(self):
        """教育费附加3%: (50000+0)×0.03=1500"""
        assert calculate_surtax(50000, 0, 0.03) == pytest.approx(1500, abs=0.01)

    def test_calculate_surtax_local_education_2_percent(self):
        """地方教育附加2%: (50000+0)×0.02=1000"""
        assert calculate_surtax(50000, 0, 0.02) == pytest.approx(1000, abs=0.01)

    def test_calculate_surtax_zero_tax(self):
        """零增值税"""
        assert calculate_surtax(0, 0, 0.07) == 0


class TestCalculatePropertyTaxByValue:
    """房产税从价=原值×(1-扣除比例)×1.2%

    Validates: Requirements 4.2
    """

    def test_calculate_property_tax_by_value(self):
        """标准30%扣除: 10000000×(1-0.3)×0.012=84000"""
        result = calculate_property_tax_by_value(10000000, 0.3)
        assert result == pytest.approx(84000, abs=0.01)

    def test_calculate_property_tax_by_value_20_deduct(self):
        """20%扣除: 10000000×(1-0.2)×0.012=96000"""
        result = calculate_property_tax_by_value(10000000, 0.2)
        assert result == pytest.approx(96000, abs=0.01)

    def test_calculate_property_tax_by_value_zero_original(self):
        """零原值"""
        assert calculate_property_tax_by_value(0, 0.3) == 0

    def test_calculate_property_tax_by_value_zero_deduct(self):
        """零扣除: 1000000×1×0.012=12000"""
        result = calculate_property_tax_by_value(1000000, 0)
        assert result == pytest.approx(12000, abs=0.01)


class TestCalculateStampTax:
    """印花税=计税金额×适用税率

    Validates: Requirements 4.3
    """

    def test_calculate_stamp_tax(self):
        """购销合同0.3‰: 10000000×0.0003=3000"""
        result = calculate_stamp_tax(10000000, 0.0003)
        assert result == pytest.approx(3000, abs=0.01)

    def test_calculate_stamp_tax_lease(self):
        """租赁合同1‰: 500000×0.001=500"""
        result = calculate_stamp_tax(500000, 0.001)
        assert result == pytest.approx(500, abs=0.01)

    def test_calculate_stamp_tax_loan(self):
        """借款合同0.05‰: 20000000×0.00005=1000"""
        result = calculate_stamp_tax(20000000, 0.00005)
        assert result == pytest.approx(1000, abs=0.01)

    def test_calculate_stamp_tax_zero_amount(self):
        """零金额"""
        assert calculate_stamp_tax(0, 0.0003) == 0

    def test_calculate_stamp_tax_zero_rate(self):
        """零税率"""
        assert calculate_stamp_tax(10000000, 0) == 0


class TestCalculateLandUseTax:
    """土地使用税=占地面积×单位税额

    Validates: Requirements 4.4
    """

    def test_calculate_land_use_tax(self):
        """常见: 5000㎡×10元/㎡=50000"""
        assert calculate_land_use_tax(5000, 10) == 50000

    def test_calculate_land_use_tax_small_area(self):
        """小面积: 100㎡×30元/㎡=3000"""
        assert calculate_land_use_tax(100, 30) == 3000

    def test_calculate_land_use_tax_zero_area(self):
        """零面积"""
        assert calculate_land_use_tax(0, 10) == 0

    def test_calculate_land_use_tax_zero_unit(self):
        """零单位税额"""
        assert calculate_land_use_tax(5000, 0) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. N2计提对应交叉验证 (Requirements 6.1, 6.3, 6.5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestVerifyExpenseVsAccrual:
    """费用确认(N4) vs 计提额(N2)交叉验证

    Validates: Requirements 6.1, 6.3, 6.5
    """

    def test_verify_expense_vs_accrual(self):
        """基本匹配和不匹配场景"""
        n4_expenses = {"城建税": 7000.0, "教育费附加": 3000.0}
        n2_accruals = {"城建税": 7000.0, "教育费附加": 3000.0}
        results = verify_expense_vs_accrual(n4_expenses, n2_accruals)

        assert len(results) == 2
        for r in results:
            assert r["is_matched"] is True
            assert abs(r["difference"]) <= 0.01

    def test_verify_expense_vs_accrual_all_match(self):
        """所有税种完全匹配"""
        n4_expenses = {
            "消费税": 5000.0,
            "城建税": 7000.0,
            "教育费附加": 3000.0,
            "地方教育附加": 2000.0,
            "房产税": 84000.0,
            "土地使用税": 50000.0,
            "印花税": 3000.0,
        }
        n2_accruals = {
            "消费税": 5000.0,
            "城建税": 7000.0,
            "教育费附加": 3000.0,
            "地方教育附加": 2000.0,
            "房产税": 84000.0,
            "土地使用税": 50000.0,
            "印花税": 3000.0,
        }
        results = verify_expense_vs_accrual(n4_expenses, n2_accruals)

        assert len(results) == 7
        assert all(r["is_matched"] for r in results)
        assert all(abs(r["difference"]) <= 0.01 for r in results)

    def test_verify_expense_vs_accrual_with_diff(self):
        """部分税种有差异"""
        n4_expenses = {
            "城建税": 7500.0,    # 多500
            "教育费附加": 3000.0,
            "房产税": 80000.0,   # 少4000
        }
        n2_accruals = {
            "城建税": 7000.0,
            "教育费附加": 3000.0,
            "房产税": 84000.0,
        }
        results = verify_expense_vs_accrual(n4_expenses, n2_accruals)

        results_by_tax = {r["tax_type"]: r for r in results}

        # 城建税有差异
        assert results_by_tax["城建税"]["is_matched"] is False
        assert results_by_tax["城建税"]["difference"] == pytest.approx(500, abs=0.01)

        # 教育费附加匹配
        assert results_by_tax["教育费附加"]["is_matched"] is True

        # 房产税有差异
        assert results_by_tax["房产税"]["is_matched"] is False
        assert results_by_tax["房产税"]["difference"] == pytest.approx(-4000, abs=0.01)

    def test_verify_expense_vs_accrual_n4_has_extra(self):
        """N4有税种但N2无（例如N2未编制某税种）"""
        n4_expenses = {"车船税": 1200.0}
        n2_accruals = {}
        results = verify_expense_vs_accrual(n4_expenses, n2_accruals)

        assert len(results) == 1
        assert results[0]["tax_type"] == "车船税"
        assert results[0]["n4_expense"] == 1200.0
        assert results[0]["n2_accrual"] == 0.0
        assert results[0]["is_matched"] is False

    def test_verify_expense_vs_accrual_tolerance(self):
        """差异≤0.01视为匹配（浮点容差）"""
        n4_expenses = {"印花税": 3000.005}
        n2_accruals = {"印花税": 3000.0}
        results = verify_expense_vs_accrual(n4_expenses, n2_accruals)

        assert results[0]["is_matched"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 方向校验 (Requirements 7.1, 7.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDirectionValidation:
    """确保N4正确使用借方-贷方方向（6403为借方科目）

    Validates: Requirements 7.1, 7.4
    """

    def test_n4_debit_minus_credit_direction(self):
        """N4使用借方-贷方（非贷方-借方如K10）"""
        debit, credit = 120000, 20000
        n4_result = calc_period_amount(debit, credit)
        # 6403损益类借方科目：借方-贷方=100000
        assert n4_result == 100000
        # 不能是贷方-借方=-100000
        assert n4_result != (credit - debit)

    def test_6403_is_borrowing_account(self):
        """6403是借方科目：借方登记费用增加，贷方登记冲回"""
        # 场景：本期发生费用8万，冲回1万
        debit_occur = 80000  # 借方=费用增加
        credit_occur = 10000  # 贷方=冲回
        net = calc_period_amount(debit_occur, credit_occur)
        # 净费用=7万（正数=净费用，符合预期）
        assert net == 70000
        assert net > 0  # 正常情况下净发生额为正

    def test_n4_vs_k10_direction_opposite(self):
        """N4(6403借方)与K10(6117贷方)方向相反"""
        debit, credit = 50000, 10000
        # N4: 借方-贷方 = 40000 (费用净增)
        n4_net = calc_period_amount(debit, credit)
        assert n4_net == 40000
        # K10营业外收入(6117): 贷方-借方 = -40000 (N4方向反转)
        # 这里只是验证N4确实是借方-贷方方向
        k10_would_be = credit - debit
        assert k10_would_be == -40000
        assert n4_net != k10_would_be

    def test_n4_direction_with_pure_cost(self):
        """纯费用发生（无冲回）: 借方发生=全部费用"""
        # 全部是费用增加
        net = calc_period_amount(150000, 0)
        assert net == 150000

    def test_n4_direction_with_full_reversal(self):
        """全额冲回（极端情况）"""
        net = calc_period_amount(0, 50000)
        assert net == -50000  # 纯冲回=负数


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 跨底稿联动端到端 (Requirements 6.1-6.5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossWorkpaperIntegration:
    """N4-1→N4-2 / N4→A利润表勾稽 / N2对应

    Validates: Requirements 2.5-2.6, 6.1-6.5
    """

    def test_n4_1_to_n4_2_subtotal_check(self):
        """N4-1审定表合计应等于N4-2明细合计"""
        # 模拟N4-2明细各税种发生额
        detail_amounts = [
            5000,   # 消费税
            7000,   # 城建税
            3000,   # 教育费附加
            2000,   # 地方教育附加
            84000,  # 房产税
            50000,  # 土地使用税
            1200,   # 车船税
            3000,   # 印花税
            0,      # 资源税
        ]
        detail_total = calc_subtotal(detail_amounts)

        # N4-1审定表的审定发生额总计应等于明细合计
        assert detail_total == 155200

    def test_n4_to_income_statement_amount(self):
        """N4审定发生额→A类利润表税金及附加行"""
        # 模拟审定过程
        unadjusted = 150000  # 未审发生额（从tb_ledger取）
        aje = 5000           # 审计调整
        rje = 200            # 重分类
        audited = calc_audited_amount(unadjusted, aje, rje)

        # 这个审定额就是A利润表税金及附加行的金额
        assert audited == 155200

    def test_n2_accrual_chain_to_n4(self):
        """N2各税种计提额→N4费用确认交叉验证完整链"""
        # 模拟N2计提各税种
        vat = 100000  # 增值税应交额
        ct = 0        # 消费税

        n2_accruals = {
            "城建税": calculate_surtax(vat, ct, 0.07),          # 7000
            "教育费附加": calculate_surtax(vat, ct, 0.03),       # 3000
            "地方教育附加": calculate_surtax(vat, ct, 0.02),     # 2000
            "房产税": calculate_property_tax_by_value(10e6, 0.3),  # 84000
            "印花税": calculate_stamp_tax(10e6, 0.0003),          # 3000
            "土地使用税": calculate_land_use_tax(5000, 10),       # 50000
        }

        # N4费用确认应等于N2计提（理想情况）
        n4_expenses = n2_accruals.copy()

        results = verify_expense_vs_accrual(n4_expenses, n2_accruals)
        assert all(r["is_matched"] for r in results)

    def test_full_n4_calculation_flow(self):
        """完整N4计算流程：tb_ledger取数→公式计算→审定→验证"""
        # Step 1: 从tb_ledger取本期发生额（模拟）
        debit_occur = 160000  # 借方发生
        credit_occur = 5000   # 贷方发生（冲回）
        period_amount = calc_period_amount(debit_occur, credit_occur)
        assert period_amount == 155000

        # Step 2: 审定数计算
        unadjusted = period_amount  # 未审数=本期发生额
        aje = 200                   # 审计调整
        rje = 0
        audited = calc_audited_amount(unadjusted, aje, rje)
        assert audited == 155200

        # Step 3: 同比变动
        prior_year = 140000
        yoy = calc_yoy_change(audited, prior_year)
        assert yoy == pytest.approx((155200 - 140000) / 140000, abs=1e-6)

        # Step 4: 验证合计
        tax_details = [7000, 3000, 2000, 84000, 3000, 50000, 1200, 5000, 0]
        detail_total = calc_subtotal(tax_details)
        assert detail_total == 155200
        assert detail_total == audited  # N4-1与N4-2勾稽
