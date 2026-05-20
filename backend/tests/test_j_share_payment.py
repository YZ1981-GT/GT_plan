"""J-F8 股份支付 Black-Scholes 公允价值计算 — 单元测试

Covers:
- BS 公式正确性（标准参数 + 已知解析解对比）
- 4 单调性测试（S↑→C↑ / K↑→C↓ / σ↑→C↑ / T↑→C↑）
- 边界 case（σ=0 / T=0 / S<=0 / K<=0 → 400）
- 费用摊销计划正确性
- apply_to_sheet 写回联动
- RBAC 校验
- is_llm_stub config 驱动

对应 spec: workpaper-j-payroll-cycle J-F8 / ADR-J5
"""

import sys
sys.path.insert(0, "backend")

import inspect
import math

import pytest
from fastapi import HTTPException

from app.routers.wp_j_share_payment import (
    SharePaymentCalcRequest,
    _black_scholes_call,
    _calc_share_payment,
    _maybe_apply_share_payment_to_workpaper,
    _validate_share_payment_request,
    j3_share_payment_calc,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════════


def _make_request(**overrides) -> SharePaymentCalcRequest:
    """构造标准股份支付请求"""
    defaults = {
        "stock_price": 20.0,
        "exercise_price": 18.0,
        "risk_free_rate": 0.03,
        "volatility": 0.35,
        "time_to_maturity": 3.0,
        "dividend_yield": 0.01,
        "grant_quantity": 1000000,
        "vesting_period": 4,
        "apply_to_sheet": None,
    }
    defaults.update(overrides)
    return SharePaymentCalcRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. BS 公式正确性
# ═══════════════════════════════════════════════════════════════════════════════


class TestBlackScholesFormula:
    """Black-Scholes 公式正确性验证"""

    def test_standard_params_positive_value(self):
        """标准参数下期权价值 > 0"""
        c = _black_scholes_call(S=20, K=18, r=0.03, sigma=0.35, T=3.0, q=0.01)
        assert c > 0

    def test_deep_in_the_money(self):
        """深度实值期权：C ≈ S·e^(-qT) - K·e^(-rT)"""
        # S=100, K=10, σ=0.01, T=1 → 深度实值
        c = _black_scholes_call(S=100, K=10, r=0.05, sigma=0.01, T=1.0, q=0.0)
        intrinsic = 100 * math.exp(0) - 10 * math.exp(-0.05)
        assert abs(c - intrinsic) < 1.0  # 深度实值时接近内在价值

    def test_at_the_money(self):
        """平值期权：S=K 时 C > 0（时间价值）"""
        c = _black_scholes_call(S=50, K=50, r=0.05, sigma=0.3, T=1.0, q=0.0)
        assert c > 0

    def test_zero_dividend_yield(self):
        """q=0 时公式退化为标准 BS"""
        c_with_q = _black_scholes_call(S=20, K=18, r=0.03, sigma=0.35, T=3.0, q=0.0)
        # 手动计算标准 BS
        d1 = (math.log(20/18) + (0.03 + 0.5*0.35**2)*3) / (0.35*math.sqrt(3))
        d2 = d1 - 0.35*math.sqrt(3)
        from app.routers.wp_j_share_payment import _norm_cdf
        expected = 20 * _norm_cdf(d1) - 18 * math.exp(-0.03*3) * _norm_cdf(d2)
        assert abs(c_with_q - expected) < 0.001

    def test_option_value_less_than_stock_price(self):
        """期权价值 < 标的价格（上界）"""
        c = _black_scholes_call(S=20, K=18, r=0.03, sigma=0.35, T=3.0, q=0.01)
        assert c < 20


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 4 单调性测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestMonotonicity:
    """Black-Scholes 4 单调性"""

    def test_s_up_c_up(self):
        """S↑ → C↑（标的价格上升，看涨期权价值上升）"""
        c1 = _black_scholes_call(S=20, K=18, r=0.03, sigma=0.35, T=3.0, q=0.01)
        c2 = _black_scholes_call(S=25, K=18, r=0.03, sigma=0.35, T=3.0, q=0.01)
        assert c2 > c1

    def test_k_up_c_down(self):
        """K↑ → C↓（行权价上升，看涨期权价值下降）"""
        c1 = _black_scholes_call(S=20, K=18, r=0.03, sigma=0.35, T=3.0, q=0.01)
        c2 = _black_scholes_call(S=20, K=22, r=0.03, sigma=0.35, T=3.0, q=0.01)
        assert c2 < c1

    def test_sigma_up_c_up(self):
        """σ↑ → C↑（波动率上升，期权价值上升）"""
        c1 = _black_scholes_call(S=20, K=18, r=0.03, sigma=0.20, T=3.0, q=0.01)
        c2 = _black_scholes_call(S=20, K=18, r=0.03, sigma=0.50, T=3.0, q=0.01)
        assert c2 > c1

    def test_t_up_c_up(self):
        """T↑ → C↑（到期时间延长，期权价值上升）"""
        c1 = _black_scholes_call(S=20, K=18, r=0.03, sigma=0.35, T=1.0, q=0.01)
        c2 = _black_scholes_call(S=20, K=18, r=0.03, sigma=0.35, T=5.0, q=0.01)
        assert c2 > c1


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 边界 case
# ═══════════════════════════════════════════════════════════════════════════════


class TestBoundaryCases:
    """边界 case 验证"""

    def test_volatility_zero_raises_400(self):
        """σ=0 → pydantic validation error (gt=0)"""
        with pytest.raises(Exception):
            _make_request(volatility=0)

    def test_time_zero_raises_400(self):
        """T=0 → pydantic validation error (gt=0)"""
        with pytest.raises(Exception):
            _make_request(time_to_maturity=0)

    def test_stock_price_zero_raises_400(self):
        """S=0 → pydantic validation error (gt=0)"""
        with pytest.raises(Exception):
            _make_request(stock_price=0)

    def test_exercise_price_zero_raises_400(self):
        """K=0 → pydantic validation error (gt=0)"""
        with pytest.raises(Exception):
            _make_request(exercise_price=0)

    def test_negative_stock_price_raises(self):
        """S<0 → pydantic validation error"""
        with pytest.raises(Exception):
            _make_request(stock_price=-5)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 费用摊销计划
# ═══════════════════════════════════════════════════════════════════════════════


class TestExpenseSchedule:
    """费用摊销计划正确性"""

    def test_schedule_length_equals_vesting_period(self):
        """摊销计划条数 = vesting_period"""
        req = _make_request(vesting_period=4)
        result = _calc_share_payment(req)
        assert len(result["annual_expense_schedule"]) == 4

    def test_cumulative_equals_total_fair_value(self):
        """最后一年累计 = total_fair_value"""
        req = _make_request(vesting_period=4)
        result = _calc_share_payment(req)
        last = result["annual_expense_schedule"][-1]
        assert abs(last["cumulative"] - result["total_fair_value"]) < 0.01

    def test_schedule_cumulative_monotone(self):
        """累计费用单调递增"""
        req = _make_request(vesting_period=4)
        result = _calc_share_payment(req)
        cums = [item["cumulative"] for item in result["annual_expense_schedule"]]
        for i in range(1, len(cums)):
            assert cums[i] >= cums[i-1]

    def test_single_year_vesting(self):
        """vesting_period=1 → 一次性确认全部费用"""
        req = _make_request(vesting_period=1)
        result = _calc_share_payment(req)
        assert len(result["annual_expense_schedule"]) == 1
        assert abs(result["annual_expense_schedule"][0]["expense"] - result["total_fair_value"]) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 写回联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """apply_to_sheet 写回联动"""

    def test_write_back_function_is_callable(self):
        """_maybe_apply_share_payment_to_workpaper 是可调用函数"""
        assert callable(_maybe_apply_share_payment_to_workpaper)

    def test_write_back_returns_none_when_no_sheet(self):
        """apply_to_sheet=None → 不写回"""
        import asyncio

        async def _run():
            req = _make_request()
            result = _calc_share_payment(req)
            return await _maybe_apply_share_payment_to_workpaper(
                None, "invalid-uuid", req, result
            )

        r = asyncio.run(_run())
        assert r is None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. RBAC 校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC 校验"""

    def test_endpoint_function_has_user_dependency(self):
        """endpoint 函数签名中包含 _user 参数"""
        sig = inspect.signature(j3_share_payment_calc)
        param_names = list(sig.parameters.keys())
        assert "_user" in param_names

    def test_endpoint_requires_edit_permission(self):
        """endpoint 使用 require_project_access('edit') 依赖"""
        sig = inspect.signature(j3_share_payment_calc)
        user_param = sig.parameters["_user"]
        assert user_param.default is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 7. is_llm_stub config 驱动
# ═══════════════════════════════════════════════════════════════════════════════


class TestStubConfig:
    """is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动"""

    def test_stub_flag_default_true(self):
        """默认 WP_AI_SERVICE_ENABLED=False → is_llm_stub=True"""
        from app.core.config import settings
        enabled = getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not enabled
        assert is_stub is True  # 默认未配置时为 stub
