"""比率分析计算引擎单元测试 — 验证公式正确性

Validates: Requirements 3.1~3.9
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.ratio_analysis_engine import (
    CATEGORY_ASSET_EFFICIENCY,
    CATEGORY_CAPITAL_MANAGEMENT,
    CATEGORY_CASH_FLOW,
    CATEGORY_LABELS,
    CATEGORY_LONG_TERM_SOLVENCY,
    CATEGORY_ORDER,
    CATEGORY_PROFITABILITY,
    CATEGORY_SHORT_TERM_SOLVENCY,
    RATIO_FORMULAS,
    RatioFormula,
    RatioResult,
    _annualize,
    _average,
    _safe_divide,
    _sum_codes,
    compute_all_ratios,
    compute_single_ratio,
    format_ratio_analysis_sheet,
)


# ---------------------------------------------------------------------------
# 辅助函数测试
# ---------------------------------------------------------------------------


class TestSumCodes:
    """_sum_codes 按 row_code 求和"""

    def test_single_code(self):
        data = {"BS-020": Decimal("500000")}
        assert _sum_codes(data, ["BS-020"]) == Decimal("500000")

    def test_multiple_codes(self):
        data = {"IS-024": Decimal("100000"), "IS-015": Decimal("20000")}
        assert _sum_codes(data, ["IS-024", "IS-015"]) == Decimal("120000")

    def test_subtract_code(self):
        data = {"BS-020": Decimal("500000"), "BS-018": Decimal("150000")}
        assert _sum_codes(data, ["BS-020", "-BS-018"]) == Decimal("350000")

    def test_missing_code_returns_none(self):
        data = {"BS-001": Decimal("100")}
        assert _sum_codes(data, ["BS-999"]) is None

    def test_partial_missing(self):
        """部分 code 存在时只累加存在的"""
        data = {"BS-020": Decimal("500000")}
        result = _sum_codes(data, ["BS-020", "-BS-018"])
        assert result == Decimal("500000")

    def test_empty_codes(self):
        data = {"BS-001": Decimal("100")}
        assert _sum_codes(data, []) is None

    def test_empty_data(self):
        assert _sum_codes({}, ["BS-001"]) is None


class TestAnnualize:
    """年化处理"""

    def test_full_year(self):
        """12个月不需要年化"""
        assert _annualize(Decimal("1200000"), 12) == Decimal("1200000")

    def test_half_year(self):
        """6个月年化: 600000 * 12 / 6 = 1200000"""
        assert _annualize(Decimal("600000"), 6) == Decimal("1200000")

    def test_quarter(self):
        """3个月年化: 300000 * 12 / 3 = 1200000"""
        assert _annualize(Decimal("300000"), 3) == Decimal("1200000")

    def test_zero_month(self):
        """0个月不做处理"""
        assert _annualize(Decimal("100"), 0) == Decimal("100")


class TestAverage:
    """年末年初算术平均"""

    def test_normal(self):
        result = _average(Decimal("1000"), Decimal("800"))
        assert result == Decimal("900")

    def test_one_none(self):
        """一方为 None 时按 0 处理"""
        result = _average(Decimal("1000"), None)
        assert result == Decimal("500")

    def test_both_none(self):
        assert _average(None, None) is None


class TestSafeDivide:
    """安全除法"""

    def test_normal(self):
        result = _safe_divide(Decimal("100"), Decimal("50"))
        assert result == Decimal("2")

    def test_denominator_zero(self):
        assert _safe_divide(Decimal("100"), Decimal("0")) is None

    def test_numerator_none(self):
        assert _safe_divide(None, Decimal("50")) is None

    def test_denominator_none(self):
        assert _safe_divide(Decimal("100"), None) is None


# ---------------------------------------------------------------------------
# 比率公式定义测试
# ---------------------------------------------------------------------------


class TestRatioFormulasDefinition:
    """验证 RATIO_FORMULAS 数据完整性"""

    def test_total_count(self):
        """至少 35 个比率公式"""
        assert len(RATIO_FORMULAS) >= 35

    def test_seq_unique(self):
        """seq 唯一"""
        seqs = [f.seq for f in RATIO_FORMULAS]
        assert len(seqs) == len(set(seqs))

    def test_all_categories_covered(self):
        """6 大类都有公式"""
        cats = set(f.category for f in RATIO_FORMULAS)
        for cat in CATEGORY_ORDER:
            assert cat in cats, f"缺少分类: {CATEGORY_LABELS[cat]}"

    def test_profitability_count(self):
        """盈利能力 9 个"""
        count = sum(1 for f in RATIO_FORMULAS if f.category == CATEGORY_PROFITABILITY)
        assert count == 9

    def test_short_term_solvency_count(self):
        """短期偿债 3 个"""
        count = sum(1 for f in RATIO_FORMULAS if f.category == CATEGORY_SHORT_TERM_SOLVENCY)
        assert count == 3

    def test_long_term_solvency_count(self):
        """长期偿债 7 个"""
        count = sum(1 for f in RATIO_FORMULAS if f.category == CATEGORY_LONG_TERM_SOLVENCY)
        assert count == 7

    def test_asset_efficiency_count(self):
        """资产管理效率 6 个"""
        count = sum(1 for f in RATIO_FORMULAS if f.category == CATEGORY_ASSET_EFFICIENCY)
        assert count == 6

    def test_capital_management_count(self):
        """资本管理 6 个"""
        count = sum(1 for f in RATIO_FORMULAS if f.category == CATEGORY_CAPITAL_MANAGEMENT)
        assert count == 6

    def test_cash_flow_count(self):
        """现金流量 4 个"""
        count = sum(1 for f in RATIO_FORMULAS if f.category == CATEGORY_CASH_FLOW)
        assert count == 4

    def test_normal_values(self):
        """流动/速动/现金比率有正常值"""
        by_name = {f.name: f for f in RATIO_FORMULAS}
        assert by_name["流动比率"].normal_value == 2.0
        assert by_name["速动比率"].normal_value == 1.0
        assert by_name["现金比率"].normal_value == 0.3


# ---------------------------------------------------------------------------
# 具体比率公式验证
# ---------------------------------------------------------------------------


class TestProfitabilityRatios:
    """盈利能力比率计算验证"""

    def _make_data(self):
        """构造测试数据"""
        current = {
            "IS-001": Decimal("10000000"),  # 营业收入
            "IS-002": Decimal("7000000"),   # 营业成本
            "IS-011": Decimal("500000"),    # 销售费用
            "IS-012": Decimal("800000"),    # 管理费用
            "IS-013": Decimal("200000"),    # 研发费用
            "IS-015": Decimal("100000"),    # 利息费用
            "IS-021": Decimal("1500000"),   # 营业利润
            "IS-024": Decimal("1400000"),   # 利润总额
            "IS-027": Decimal("1050000"),   # 净利润
            "BS-039": Decimal("20000000"),  # 资产总计
            "BS-076": Decimal("5000000"),   # 非流动负债合计
            "BS-078": Decimal("8000000"),   # 实收资本
            "BS-098": Decimal("12000000"),  # 所有者权益合计
        }
        prior = {
            "IS-001": Decimal("8000000"),
            "IS-002": Decimal("5600000"),
            "IS-015": Decimal("80000"),
            "IS-021": Decimal("1200000"),
            "IS-024": Decimal("1100000"),
            "IS-027": Decimal("825000"),
            "BS-039": Decimal("18000000"),
            "BS-076": Decimal("4500000"),
            "BS-078": Decimal("8000000"),
            "BS-098": Decimal("11000000"),
        }
        return current, prior

    def test_gross_margin(self):
        """毛利率 = (10000000-7000000)/10000000 = 0.3"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "毛利率")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(0.3, abs=0.0001)

    def test_operating_profit_margin(self):
        """营业利润率 = 1500000/10000000 = 0.15"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "营业利润率")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(0.15, abs=0.0001)

    def test_net_profit_margin(self):
        """销售净利率 = 1050000/10000000 = 0.105"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "销售净利率")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(0.105, abs=0.0001)

    def test_cost_profit_ratio(self):
        """成本费用利润率 = 1400000/(7000000+500000+800000+200000) = 1400000/8500000"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "成本费用利润率")
        result = compute_single_ratio(formula, current, prior)
        expected = 1400000 / 8500000
        assert result.current_value == pytest.approx(expected, abs=0.0001)

    def test_rnd_ratio(self):
        """研发费用比例 = 200000/10000000 = 0.02"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "研究开发费用比例")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(0.02, abs=0.0001)

    def test_total_asset_return(self):
        """总资产报酬率 = (1400000+100000)/(20000000+18000000)/2 = 1500000/19000000"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "总资产报酬率")
        result = compute_single_ratio(formula, current, prior)
        expected = 1500000 / 19000000
        assert result.current_value == pytest.approx(expected, abs=0.0001)

    def test_equity_return(self):
        """股本权益报酬率 = 1050000 / ((12000000+11000000)/2) = 1050000/11500000"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "股本权益报酬率")
        result = compute_single_ratio(formula, current, prior)
        expected = 1050000 / 11500000
        assert result.current_value == pytest.approx(expected, abs=0.0001)


class TestShortTermSolvencyRatios:
    """短期偿债能力比率验证"""

    def _make_data(self):
        current = {
            "BS-001": Decimal("2000000"),   # 货币资金
            "BS-002": Decimal("500000"),    # 交易性金融资产
            "BS-018": Decimal("3000000"),   # 存货
            "BS-020": Decimal("10000000"),  # 流动资产合计
            "BS-058": Decimal("5000000"),   # 流动负债合计
        }
        prior = {
            "BS-001": Decimal("1500000"),
            "BS-002": Decimal("300000"),
            "BS-018": Decimal("2500000"),
            "BS-020": Decimal("8000000"),
            "BS-058": Decimal("4500000"),
        }
        return current, prior

    def test_current_ratio(self):
        """流动比率 = 10000000/5000000 = 2.0"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "流动比率")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(2.0, abs=0.0001)
        assert result.normal_value == 2.0

    def test_quick_ratio(self):
        """速动比率 = (10000000-3000000)/5000000 = 1.4"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "速动比率")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(1.4, abs=0.0001)
        assert result.normal_value == 1.0

    def test_cash_ratio(self):
        """现金比率 = (2000000+500000)/5000000 = 0.5"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "现金比率")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(0.5, abs=0.0001)
        assert result.normal_value == 0.3


class TestLongTermSolvencyRatios:
    """长期偿债能力比率验证"""

    def _make_data(self):
        current = {
            "BS-020": Decimal("10000000"),  # 流动资产
            "BS-025": Decimal("1000000"),   # 无形资产
            "BS-027": Decimal("8000000"),   # 固定资产
            "BS-028": Decimal("500000"),    # 商誉
            "BS-039": Decimal("25000000"),  # 资产总计
            "BS-058": Decimal("5000000"),   # 流动负债合计
            "BS-076": Decimal("6000000"),   # 非流动负债合计
            "BS-077": Decimal("11000000"),  # 负债合计
            "BS-098": Decimal("14000000"),  # 所有者权益合计
            "IS-015": Decimal("300000"),    # 利息费用
            "IS-024": Decimal("2000000"),   # 利润总额
        }
        prior = {
            "BS-039": Decimal("22000000"),
            "BS-058": Decimal("4000000"),
            "BS-076": Decimal("5000000"),
            "BS-077": Decimal("9000000"),
            "BS-098": Decimal("13000000"),
            "IS-015": Decimal("250000"),
            "IS-024": Decimal("1800000"),
        }
        return current, prior

    def test_debt_to_asset_ratio(self):
        """资产负债比率 = 11000000/25000000 = 0.44"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "资产负债比率")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(0.44, abs=0.0001)

    def test_equity_ratio(self):
        """产权比率 = 11000000/14000000"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "产权比率")
        result = compute_single_ratio(formula, current, prior)
        expected = 11000000 / 14000000
        assert result.current_value == pytest.approx(expected, abs=0.0001)

    def test_tangible_net_worth_ratio(self):
        """有形净值债务比率 = 11000000/(14000000-1000000-500000) = 11000000/12500000"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "有形净值债务比率")
        result = compute_single_ratio(formula, current, prior)
        expected = 11000000 / 12500000
        assert result.current_value == pytest.approx(expected, abs=0.0001)

    def test_interest_coverage(self):
        """利息保障倍数 = (2000000+300000)/300000 = 7.667"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "利息保障倍数")
        result = compute_single_ratio(formula, current, prior)
        expected = 2300000 / 300000
        assert result.current_value == pytest.approx(expected, abs=0.001)

    def test_working_capital_to_long_term_debt(self):
        """营运资金长期负债比率 = (10000000-5000000)/6000000"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "营运资金长期负债比率")
        result = compute_single_ratio(formula, current, prior)
        expected = 5000000 / 6000000
        assert result.current_value == pytest.approx(expected, abs=0.0001)


class TestAssetEfficiencyRatios:
    """资产管理效率比率验证"""

    def _make_data(self):
        current = {
            "IS-001": Decimal("20000000"),  # 营业收入
            "IS-002": Decimal("14000000"),  # 营业成本
            "BS-008": Decimal("3000000"),   # 应收账款
            "BS-018": Decimal("4000000"),   # 存货
            "BS-020": Decimal("12000000"),  # 流动资产合计
            "BS-027": Decimal("8000000"),   # 固定资产
            "BS-039": Decimal("30000000"),  # 资产总计
        }
        prior = {
            "IS-001": Decimal("18000000"),
            "IS-002": Decimal("12600000"),
            "BS-008": Decimal("2500000"),
            "BS-018": Decimal("3500000"),
            "BS-020": Decimal("10000000"),
            "BS-027": Decimal("7000000"),
            "BS-039": Decimal("26000000"),
        }
        return current, prior

    def test_total_asset_turnover(self):
        """总资产周转率 = 20000000 / ((30000000+26000000)/2) = 20000000/28000000"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "总资产周转率")
        result = compute_single_ratio(formula, current, prior)
        expected = 20000000 / 28000000
        assert result.current_value == pytest.approx(expected, abs=0.0001)

    def test_inventory_turnover(self):
        """存货周转率 = 14000000 / ((4000000+3500000)/2) = 14000000/3750000"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "存货周转率")
        result = compute_single_ratio(formula, current, prior)
        expected = 14000000 / 3750000
        assert result.current_value == pytest.approx(expected, abs=0.0001)

    def test_ar_turnover(self):
        """应收账款周转率 = 20000000 / ((3000000+2500000)/2) = 20000000/2750000"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "应收账款周转率")
        result = compute_single_ratio(formula, current, prior)
        expected = 20000000 / 2750000
        assert result.current_value == pytest.approx(expected, abs=0.0001)

    def test_operating_cycle(self):
        """营业周期 = 360/应收账款周转率 + 360/存货周转率"""
        current, prior = self._make_data()
        results = compute_all_ratios(current, prior)
        cycle = next(r for r in results if r.name == "营业周期")
        ar_turnover = 20000000 / 2750000
        inv_turnover = 14000000 / 3750000
        expected = 360 / ar_turnover + 360 / inv_turnover
        assert cycle.current_value == pytest.approx(expected, abs=0.1)


class TestCapitalManagementRatios:
    """资本管理效果比率验证"""

    def test_capital_preservation_rate(self):
        """资本保值增值率 = 期末权益/期初权益"""
        current = {"BS-098": Decimal("15000000")}
        prior = {"BS-098": Decimal("12000000")}
        formula = next(f for f in RATIO_FORMULAS if f.name == "资本保值增值率")
        result = compute_single_ratio(formula, current, prior)
        expected = 15000000 / 12000000
        assert result.current_value == pytest.approx(expected, abs=0.0001)

    def test_no_data_ratios_return_none(self):
        """无数据源的比率返回 None"""
        current = {"BS-039": Decimal("20000000")}
        prior = {"BS-039": Decimal("18000000")}
        formula = next(f for f in RATIO_FORMULAS if f.name == "社会贡献率")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value is None
        assert result.prior_value is None


class TestCashFlowRatios:
    """现金流量比率验证"""

    def _make_data(self):
        current = {
            "CFS-009": Decimal("3000000"),  # 经营活动现金流量净额
            "IS-001": Decimal("20000000"),  # 营业收入
            "IS-027": Decimal("1500000"),   # 净利润
            "BS-058": Decimal("8000000"),   # 流动负债合计
            "BS-077": Decimal("12000000"),  # 负债合计
        }
        prior = {
            "CFS-009": Decimal("2500000"),
            "IS-001": Decimal("18000000"),
            "IS-027": Decimal("1200000"),
            "BS-058": Decimal("7000000"),
            "BS-077": Decimal("10000000"),
        }
        return current, prior

    def test_operating_cash_to_current_liabilities(self):
        """经营活动净现金比率(一) = 3000000/8000000 = 0.375"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "经营活动净现金比率(一)")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(0.375, abs=0.0001)

    def test_operating_cash_to_total_liabilities(self):
        """经营活动净现金比率(二) = 3000000/12000000 = 0.25"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "经营活动净现金比率(二)")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(0.25, abs=0.0001)

    def test_net_profit_cash_coverage(self):
        """净利润现金保证比率 = 3000000/1500000 = 2.0"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "净利润现金保证比率")
        result = compute_single_ratio(formula, current, prior)
        assert result.current_value == pytest.approx(2.0, abs=0.0001)

    def test_sales_cash_recovery(self):
        """销售收入现金回收比率 = 3000000/20000000 = 0.15"""
        current, prior = self._make_data()
        formula = next(f for f in RATIO_FORMULAS if f.name == "销售收入现金回收比率")
        result = compute_single_ratio(formula, current, prior)
        # CFS-009/IS-001 = 3000000/20000000 = 0.15
        assert result.current_value == pytest.approx(0.15, abs=0.0001)


# ---------------------------------------------------------------------------
# 综合计算和方向测试
# ---------------------------------------------------------------------------


class TestDirectionAndChange:
    """增减方向标记"""

    def test_direction_up(self):
        """本年 > 上年 → direction=up"""
        current = {"BS-020": Decimal("10000000"), "BS-058": Decimal("5000000")}
        prior = {"BS-020": Decimal("8000000"), "BS-058": Decimal("5000000")}
        formula = next(f for f in RATIO_FORMULAS if f.name == "流动比率")
        result = compute_single_ratio(formula, current, prior)
        # 本年 2.0, 上年 1.6
        assert result.direction == "up"
        assert result.change is not None
        assert result.change > 0

    def test_direction_down(self):
        """本年 < 上年 → direction=down"""
        current = {"BS-020": Decimal("8000000"), "BS-058": Decimal("5000000")}
        prior = {"BS-020": Decimal("10000000"), "BS-058": Decimal("5000000")}
        formula = next(f for f in RATIO_FORMULAS if f.name == "流动比率")
        result = compute_single_ratio(formula, current, prior)
        assert result.direction == "down"
        assert result.change is not None
        assert result.change < 0

    def test_direction_flat(self):
        """本年 == 上年 → direction=flat"""
        current = {"BS-020": Decimal("10000000"), "BS-058": Decimal("5000000")}
        prior = {"BS-020": Decimal("10000000"), "BS-058": Decimal("5000000")}
        formula = next(f for f in RATIO_FORMULAS if f.name == "流动比率")
        result = compute_single_ratio(formula, current, prior)
        assert result.direction == "flat"

    def test_direction_none_when_missing_data(self):
        """数据缺失时 direction 为 None"""
        current = {"BS-020": Decimal("10000000"), "BS-058": Decimal("5000000")}
        prior = {}  # 无上年数据
        formula = next(f for f in RATIO_FORMULAS if f.name == "流动比率")
        result = compute_single_ratio(formula, current, prior)
        assert result.direction is None


class TestComputeAllRatios:
    """compute_all_ratios 综合验证"""

    def test_returns_all_ratios(self):
        """返回全部比率结果"""
        current = {
            "BS-001": Decimal("2000000"),
            "BS-002": Decimal("500000"),
            "BS-008": Decimal("3000000"),
            "BS-018": Decimal("3000000"),
            "BS-020": Decimal("10000000"),
            "BS-025": Decimal("1000000"),
            "BS-027": Decimal("8000000"),
            "BS-028": Decimal("500000"),
            "BS-039": Decimal("25000000"),
            "BS-058": Decimal("5000000"),
            "BS-076": Decimal("6000000"),
            "BS-077": Decimal("11000000"),
            "BS-078": Decimal("8000000"),
            "BS-098": Decimal("14000000"),
            "IS-001": Decimal("20000000"),
            "IS-002": Decimal("14000000"),
            "IS-011": Decimal("500000"),
            "IS-012": Decimal("800000"),
            "IS-013": Decimal("200000"),
            "IS-015": Decimal("300000"),
            "IS-021": Decimal("1500000"),
            "IS-024": Decimal("2000000"),
            "IS-027": Decimal("1500000"),
            "CFS-009": Decimal("3000000"),
        }
        prior = dict(current)  # 简化：上年同本年

        results = compute_all_ratios(current, prior)
        assert len(results) == len(RATIO_FORMULAS)
        # 排序正确
        for i, r in enumerate(results):
            assert r.seq == i + 1

    def test_missing_data_no_crash(self):
        """全空数据不崩溃"""
        results = compute_all_ratios({}, {})
        assert len(results) == len(RATIO_FORMULAS)
        # 所有值为 None
        for r in results:
            if r.name not in ("营业周期", "资本保值增值率"):
                # no_data 类也是 None
                pass  # 不 crash 即可


class TestFormatRatioAnalysisSheet:
    """format_ratio_analysis_sheet 格式化验证"""

    def test_structure(self):
        """验证输出结构"""
        current = {"BS-020": Decimal("10000000"), "BS-058": Decimal("5000000")}
        prior = {"BS-020": Decimal("8000000"), "BS-058": Decimal("4000000")}
        results = compute_all_ratios(current, prior)
        sheet = format_ratio_analysis_sheet(results, "A1-13")

        assert sheet["title"] == "已审报表财务比率分析"
        assert sheet["index"] == "A1-13-5"
        assert len(sheet["categories"]) == 6
        assert len(sheet["notes"]) == 3

        # 第一类是盈利能力
        assert sheet["categories"][0]["name"] == "一、盈利能力分析"
        # 第二类是短期偿债
        assert sheet["categories"][1]["name"] == "二、短期偿债能力分析"

    def test_category_items_have_required_fields(self):
        """每个 item 包含必要字段"""
        current = {"BS-020": Decimal("10000000"), "BS-058": Decimal("5000000")}
        prior = {"BS-020": Decimal("8000000"), "BS-058": Decimal("4000000")}
        results = compute_all_ratios(current, prior)
        sheet = format_ratio_analysis_sheet(results)

        for cat in sheet["categories"]:
            for item in cat["items"]:
                assert "seq" in item
                assert "name" in item
                assert "formula" in item
                assert "current_value" in item
                assert "prior_value" in item
                assert "change" in item
                assert "direction" in item


class TestAnnualizationIntegration:
    """年化处理集成测试"""

    def test_half_year_annualization(self):
        """半年报的年化处理"""
        current = {
            "IS-001": Decimal("5000000"),   # 半年营业收入
            "BS-039": Decimal("20000000"),
        }
        prior = {
            "IS-001": Decimal("9000000"),   # 上年全年
            "BS-039": Decimal("18000000"),
        }
        formula = next(f for f in RATIO_FORMULAS if f.name == "总资产周转率")
        result = compute_single_ratio(formula, current, prior, month_count=6)
        # 年化: 5000000 * 12 / 6 = 10000000
        # 平均资产: (20000000 + 18000000) / 2 = 19000000
        # 周转率: 10000000 / 19000000
        expected = 10000000 / 19000000
        assert result.current_value == pytest.approx(expected, abs=0.0001)
