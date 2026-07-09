"""M5 盈余公积 — 计提测试集成测试 (Task 7.2).

覆盖：
1. 法定10%计提计算纯函数
2. 计提差异
3. 50%上限判断
4. 完整M6→M5计提流程验证
5. _parse_num 安全数值解析

Spec: .kiro/specs/m5-surplus-reserve/ Task 7.2
Requirements: 4.1-4.7

科目：4101 盈余公积（**贷方/权益类！期末=期初+贷方-借方**）
法定盈余公积按净利润（弥补以前年度亏损后）10%计提
累计法定盈余公积达注册资本50%时可不再计提
"""

from __future__ import annotations

import pytest

from app.services.m5_surplus_reserve_service import _parse_num


# ─── 纯函数（与前端 useM5AccrualEngine 对齐的后端逻辑） ─────────────────────

def calc_statutory_accrual(base: float, rate: float = 0.1) -> float:
    """法定盈余公积应计提 = 计提基数 × 比例（默认10%）"""
    return base * rate


def calc_accrual_diff(estimated: float, booked: float) -> float:
    """计提差异 = 应计提 − 账面计提"""
    return estimated - booked


def is_ceiling_reached(accumulated: float, registered_capital: float) -> bool:
    """累计法定盈余公积是否达注册资本50%"""
    if registered_capital <= 0:
        return False
    return accumulated >= registered_capital * 0.5


def run_accrual_test(
    *,
    net_profit: float,
    prior_loss_offset: float = 0.0,
    statutory_rate: float = 0.1,
    discretionary_rate: float = 0.0,
    statutory_booked: float = 0.0,
    discretionary_booked: float = 0.0,
    accumulated_statutory: float = 0.0,
    registered_capital: float = 0.0,
) -> dict:
    """完整计提测试（与前端 useM5AccrualTest + 后端 accrual-test 端点对齐）"""
    accrual_base = net_profit - prior_loss_offset
    statutory_estimated = calc_statutory_accrual(accrual_base, statutory_rate)
    statutory_diff = calc_accrual_diff(statutory_estimated, statutory_booked)
    discretionary_estimated = calc_statutory_accrual(accrual_base, discretionary_rate)
    discretionary_diff = calc_accrual_diff(discretionary_estimated, discretionary_booked)
    total_estimated = statutory_estimated + discretionary_estimated
    total_diff = calc_accrual_diff(total_estimated, statutory_booked + discretionary_booked)
    ceiling_reached = is_ceiling_reached(accumulated_statutory, registered_capital)

    return {
        "accrual_base": accrual_base,
        "statutory_estimated": statutory_estimated,
        "statutory_diff": statutory_diff,
        "discretionary_estimated": discretionary_estimated,
        "discretionary_diff": discretionary_diff,
        "total_estimated": total_estimated,
        "total_diff": total_diff,
        "ceiling_reached": ceiling_reached,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: calc_statutory_accrual — 法定10%计提 (Req 4.3)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcStatutoryAccrual:
    """法定盈余公积应计提 = 计提基数 × 比例"""

    def test_standard_10_percent(self):
        """标准场景：基数1000万 × 10% = 100万"""
        assert calc_statutory_accrual(10000000, 0.1) == 1000000

    def test_custom_rate_5_percent(self):
        """任意计提：基数1000万 × 5% = 50万"""
        assert calc_statutory_accrual(10000000, 0.05) == 500000

    def test_zero_base(self):
        """基数=0 → 应计提=0"""
        assert calc_statutory_accrual(0, 0.1) == 0.0

    def test_negative_base(self):
        """亏损年度：基数为负 → 应计提为负（业务层判断不实际计提）"""
        result = calc_statutory_accrual(-500000, 0.1)
        assert result == -50000

    def test_default_rate(self):
        """默认比例=0.1（10%）"""
        assert calc_statutory_accrual(8000000) == 800000

    def test_large_amount(self):
        """大金额：基数10亿"""
        result = calc_statutory_accrual(1000000000, 0.1)
        assert result == 100000000


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: calc_accrual_diff — 计提差异 (Req 4.5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcAccrualDiff:
    """计提差异 = 应计提 − 账面已计提"""

    def test_positive_diff_underprovided(self):
        """少计提：应计提100万 - 账面95万 = +5万"""
        assert calc_accrual_diff(1000000, 950000) == 50000

    def test_negative_diff_overprovided(self):
        """多计提：应计提100万 - 账面105万 = -5万"""
        assert calc_accrual_diff(1000000, 1050000) == -50000

    def test_zero_diff_exact(self):
        """精确匹配：应计提 === 账面"""
        assert calc_accrual_diff(770000, 770000) == 0.0

    def test_both_zero(self):
        """两端=0"""
        assert calc_accrual_diff(0, 0) == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: is_ceiling_reached — 50%上限 (Req 4.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsCeilingReached:
    """累计法定盈余公积 ≥ 注册资本50% → 可不再计提"""

    def test_exactly_50_percent(self):
        """恰好50%: 累计500万 = 注册1000万×50% → True"""
        assert is_ceiling_reached(5000000, 10000000) is True

    def test_above_50_percent(self):
        """超过50%: 累计600万 > 注册1000万×50% → True"""
        assert is_ceiling_reached(6000000, 10000000) is True

    def test_below_50_percent(self):
        """未达50%: 累计499万 < 注册1000万×50% → False"""
        assert is_ceiling_reached(4990000, 10000000) is False

    def test_zero_registered_capital(self):
        """注册资本=0 → 不可能达上限 → False（防御性）"""
        assert is_ceiling_reached(5000000, 0) is False

    def test_negative_registered_capital(self):
        """注册资本<0 → 不可能达上限 → False（防御性）"""
        assert is_ceiling_reached(5000000, -1000) is False

    def test_zero_accumulated(self):
        """累计=0 → False"""
        assert is_ceiling_reached(0, 10000000) is False


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: run_accrual_test — 完整计提测试流程 (Req 4.1-4.7)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunAccrualTest:
    """run_accrual_test: 完整法定计提测试 + 50%上限"""

    def test_standard_scenario(self):
        """标准场景：净利润1000万-弥补亏损20万=基数980万"""
        result = run_accrual_test(
            net_profit=10000000,
            prior_loss_offset=200000,
            statutory_rate=0.1,
            discretionary_rate=0.05,
            statutory_booked=980000,
            discretionary_booked=490000,
            accumulated_statutory=4000000,
            registered_capital=10000000,
        )

        # 计提基数=10000000-200000=9800000
        assert result["accrual_base"] == 9800000
        # 法定应计提=9800000×10%=980000
        assert result["statutory_estimated"] == 980000
        # 法定差异=980000-980000=0
        assert result["statutory_diff"] == 0
        # 任意应计提=9800000×5%=490000
        assert result["discretionary_estimated"] == 490000
        # 任意差异=490000-490000=0
        assert result["discretionary_diff"] == 0
        # 合计应计提=980000+490000=1470000
        assert result["total_estimated"] == 1470000
        # 合计差异=0
        assert result["total_diff"] == 0
        # 50%上限：4000000 < 10000000×50% → False
        assert result["ceiling_reached"] is False

    def test_ceiling_reached(self):
        """累计已达注册资本50%"""
        result = run_accrual_test(
            net_profit=5000000,
            prior_loss_offset=0,
            accumulated_statutory=5000000,
            registered_capital=10000000,
        )

        assert result["ceiling_reached"] is True
        # 计算仍正常执行（上限是权利非义务）
        assert result["accrual_base"] == 5000000
        assert result["statutory_estimated"] == 500000

    def test_loss_year_negative_base(self):
        """亏损年度：净利润为负"""
        result = run_accrual_test(
            net_profit=-2000000,
            prior_loss_offset=0,
            statutory_rate=0.1,
        )

        assert result["accrual_base"] == -2000000
        assert result["statutory_estimated"] == -200000
        assert result["ceiling_reached"] is False

    def test_underprovision_diff_positive(self):
        """少计提场景：差异>0"""
        result = run_accrual_test(
            net_profit=8000000,
            prior_loss_offset=0,
            statutory_rate=0.1,
            statutory_booked=700000,  # 少提了100000
        )

        assert result["accrual_base"] == 8000000
        assert result["statutory_estimated"] == 800000
        assert result["statutory_diff"] == 100000  # 少提

    def test_overprovision_diff_negative(self):
        """多计提场景：差异<0"""
        result = run_accrual_test(
            net_profit=8000000,
            prior_loss_offset=0,
            statutory_rate=0.1,
            statutory_booked=900000,  # 多提了100000
        )

        assert result["statutory_diff"] == -100000  # 多提

    def test_all_zeros(self):
        """全零输入"""
        result = run_accrual_test(
            net_profit=0,
            prior_loss_offset=0,
        )

        assert result["accrual_base"] == 0
        assert result["statutory_estimated"] == 0
        assert result["statutory_diff"] == 0
        assert result["total_estimated"] == 0
        assert result["total_diff"] == 0
        assert result["ceiling_reached"] is False

    def test_m6_to_m5_full_chain(self):
        """M6→M5完整链：模拟从M6获取的数据执行计提测试

        ADR-3: M6未分配利润提供计提基数（净利润），M5计提盈余公积后回流影响M6可供分配利润。
        """
        # 模拟M6提供的数据
        m6_net_profit = 12000000
        m6_prior_loss_offset = 500000

        # M5执行计提测试
        result = run_accrual_test(
            net_profit=m6_net_profit,
            prior_loss_offset=m6_prior_loss_offset,
            statutory_rate=0.1,
            discretionary_rate=0.05,
            statutory_booked=1150000,
            discretionary_booked=575000,
            accumulated_statutory=3500000,
            registered_capital=10000000,
        )

        # 计提基数=12000000-500000=11500000
        assert result["accrual_base"] == 11500000
        # 法定应计提=11500000×10%=1150000
        assert result["statutory_estimated"] == 1150000
        # 法定差异=0（精确匹配）
        assert result["statutory_diff"] == 0
        # 任意应计提=11500000×5%=575000
        assert result["discretionary_estimated"] == 575000
        # 50%上限：3500000 < 10000000×50%=5000000 → False
        assert result["ceiling_reached"] is False

        # 验证M5→M6回流数据
        total_accrual = result["statutory_estimated"] + result["discretionary_estimated"]
        assert total_accrual == 1725000  # M5→M6：计提盈余公积1725000


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5: _parse_num 安全数值解析
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseNum:
    """_parse_num: 安全数值解析（None/空/NaN→0.0）"""

    def test_valid_number(self):
        assert _parse_num("12345.67") == 12345.67

    def test_integer_string(self):
        assert _parse_num("1000000") == 1000000.0

    def test_none(self):
        assert _parse_num(None) == 0.0

    def test_empty_string(self):
        assert _parse_num("") == 0.0

    def test_nan(self):
        assert _parse_num(float("nan")) == 0.0

    def test_numeric_value(self):
        assert _parse_num(500.5) == 500.5

    def test_invalid_string(self):
        assert _parse_num("abc") == 0.0

    def test_negative(self):
        assert _parse_num("-5000") == -5000.0
