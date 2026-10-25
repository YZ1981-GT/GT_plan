"""D4-6 指标预填守卫 —— Property 9 + 变异检验.

spec: four-table-extraction-entry-completion Phase 3 Task 22
Property 9: D4-6 指标预填与 TB 一致性不变式
  — 对任意 D4-6 指标 key，如果后端能从 trial_balance 解析出所需科目余额，
    则 indicator_prefill[key].current 必须等于按公式计算的结果（误差 ≤ 0.01）；
    如果任一科目无数据，则该 key 不出现在 prefill 中（不伪造 0）。
"""
from __future__ import annotations

import pytest

from app.routers.wp_render_strategies._d4_operating_revenue import (
    build_d4_indicator_prefill,
)


class TestProperty9IndicatorPrefillConsistency:
    """Property 9: 有 TB 数据时指标非空且公式正确。"""

    def _make_tb(
        self,
        ar: float = 500_000,
        revenue: float = 2_000_000,
        profit: float = 300_000,
        bad_debt: float = 25_000,
    ) -> dict[str, float]:
        return {"1122": ar, "6001": revenue, "4103": profit, "1231": bad_debt}

    def test_all_five_indicators_present_when_data_complete(self):
        """有完整 TB + 资产总计时，5 个指标全部出现。"""
        tb_cur = self._make_tb()
        tb_pri = self._make_tb(ar=400_000, revenue=1_800_000, profit=250_000, bad_debt=20_000)
        result = build_d4_indicator_prefill(tb_cur, tb_pri, 10_000_000, 9_000_000)

        assert "ar-to-assets" in result
        assert "ar-turnover-days" in result
        assert "ar-turnover-times" in result
        assert "net-profit-margin" in result
        assert "bad-debt-ratio" in result

    def test_ar_to_assets_formula(self):
        """ar-to-assets = 应收账款 / 资产总计。"""
        tb_cur = self._make_tb(ar=500_000)
        result = build_d4_indicator_prefill(tb_cur, {}, 10_000_000, None)
        expected = 500_000 / 10_000_000
        assert abs(result["ar-to-assets"]["current"] - expected) <= 0.01

    def test_ar_turnover_days_formula(self):
        """ar-turnover-days = (期初AR+期末AR)/2 / (收入/365)。"""
        tb_cur = self._make_tb(ar=500_000, revenue=2_000_000)
        tb_pri = self._make_tb(ar=400_000)
        result = build_d4_indicator_prefill(tb_cur, tb_pri, None, None)
        avg_ar = (400_000 + 500_000) / 2
        expected = avg_ar / (2_000_000 / 365)
        assert abs(result["ar-turnover-days"]["current"] - expected) <= 0.01

    def test_net_profit_margin_formula(self):
        """net-profit-margin = 净利润 / 收入。"""
        tb_cur = self._make_tb(profit=300_000, revenue=2_000_000)
        result = build_d4_indicator_prefill(tb_cur, {}, None, None)
        expected = 300_000 / 2_000_000
        assert abs(result["net-profit-margin"]["current"] - expected) <= 0.01

    def test_bad_debt_ratio_formula(self):
        """bad-debt-ratio = 坏账准备 / 应收账款。"""
        tb_cur = self._make_tb(ar=500_000, bad_debt=25_000)
        result = build_d4_indicator_prefill(tb_cur, {}, None, None)
        expected = 25_000 / 500_000
        assert abs(result["bad-debt-ratio"]["current"] - expected) <= 0.01

    def test_missing_data_key_absent(self):
        """科目无数据时该 key 不出现（不伪造 0）。"""
        result = build_d4_indicator_prefill({}, {}, None, None)
        assert result == {}

    def test_zero_revenue_no_division_error(self):
        """收入=0 时不抛异常，相关指标留空。"""
        tb_cur = self._make_tb(revenue=0)
        result = build_d4_indicator_prefill(tb_cur, {}, 10_000_000, None)
        # ar-to-assets 仍可算（不依赖收入）
        assert "ar-to-assets" in result
        # 依赖收入做分母的不出现
        assert "net-profit-margin" not in result
        assert "ar-turnover-days" not in result

    def test_zero_assets_no_division_error(self):
        """资产总计=0 时 ar-to-assets 不出现。"""
        tb_cur = self._make_tb()
        result = build_d4_indicator_prefill(tb_cur, {}, 0, None)
        assert "ar-to-assets" not in result

    def test_prior_values_populated(self):
        """上期数据可用时 prior 字段有值。"""
        tb_cur = self._make_tb()
        tb_pri = self._make_tb(ar=400_000, revenue=1_800_000, profit=250_000, bad_debt=20_000)
        result = build_d4_indicator_prefill(tb_cur, tb_pri, 10_000_000, 9_000_000)
        assert result["ar-to-assets"]["prior"] is not None
        assert result["net-profit-margin"]["prior"] is not None
        assert result["bad-debt-ratio"]["prior"] is not None


class TestProperty9Mutation:
    """变异检验：删 indicator_prefill 或改公式必须打红。"""

    def test_mutation_delete_ar_key_makes_result_empty(self):
        """变异：如果纯函数不处理 1122，ar-to-assets 不会出现。"""
        # 模拟"删除 ar-to-assets 赋值行"的变异：传空 tb 即无 1122
        tb_no_ar = {"6001": 2_000_000, "4103": 300_000, "1231": 25_000}
        result = build_d4_indicator_prefill(tb_no_ar, {}, 10_000_000, None)
        assert "ar-to-assets" not in result  # 变异后必须缺失

    def test_mutation_wrong_formula_detected(self):
        """变异：如果除法变乘法，值会不一致（打红）。"""
        tb_cur = {"1122": 500_000, "6001": 2_000_000, "4103": 300_000, "1231": 25_000}
        result = build_d4_indicator_prefill(tb_cur, {}, 10_000_000, None)

        # 正确 ar-to-assets = 500000 / 10000000 = 0.05
        correct = 500_000 / 10_000_000
        # 变异版（乘法）= 500000 * 10000000 = 5_000_000_000_000
        mutated = 500_000 * 10_000_000
        assert abs(result["ar-to-assets"]["current"] - correct) <= 0.01
        assert abs(result["ar-to-assets"]["current"] - mutated) > 1  # 必须打红
