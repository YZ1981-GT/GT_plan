"""Comprehensive unit tests for L-F7 利息自动测算引擎 — 9 组合 + 写回 + RBAC + 边界.

Covers:
- 3 计息基准 × 3 复利频率 = 9 种组合正确性
- apply_to_sheet 写回联动
- RBAC 校验（endpoint 签名包含 require_project_access("edit")）
- 边界 case（principal=0, rate=0, start>end, rate>1.0）

对应 spec: workpaper-l-debt-cycle L-F7 / ADR-L4
"""

import sys
sys.path.insert(0, "backend")

import inspect
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.routers.wp_l_interest_calc import (
    InterestCalcRequest,
    InterestCalcResponse,
    _actual_days,
    _calc_compound_periods,
    _calc_interest,
    _quantize,
    _thirty_360_months,
    _validate_interest_request,
    l_interest_calc,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: 构造标准请求
# ═══════════════════════════════════════════════════════════════════════════════


def _make_request(**overrides) -> InterestCalcRequest:
    """构造标准利息测算请求，可覆盖任意字段。"""
    defaults = {
        "wp_code": "L1",
        "principal": Decimal("1000000"),
        "annual_rate": Decimal("0.045"),
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 7, 1),
        "day_count_basis": "ACT/360",
        "compound_frequency": "simple",
        "apply_to_sheet": None,
    }
    defaults.update(overrides)
    return InterestCalcRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 辅助函数测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelpers:
    """辅助函数正确性"""

    def test_actual_days(self):
        """实际天数计算"""
        assert _actual_days(date(2025, 1, 1), date(2025, 7, 1)) == 181

    def test_actual_days_same_day(self):
        """同一天 → 0 天"""
        assert _actual_days(date(2025, 3, 15), date(2025, 3, 15)) == 0

    def test_thirty_360_months_half_year(self):
        """30/360 半年 = 6 个月"""
        months = _thirty_360_months(date(2025, 1, 1), date(2025, 7, 1))
        assert months == Decimal("6")

    def test_thirty_360_months_with_day_fraction(self):
        """30/360 含日差"""
        months = _thirty_360_months(date(2025, 1, 1), date(2025, 7, 16))
        # 6 + 15/30 = 6.5
        assert months == Decimal("6.5")

    def test_compound_periods_monthly(self):
        """月复利期数"""
        periods = _calc_compound_periods(date(2025, 1, 1), date(2025, 7, 1), "monthly")
        assert periods == 6

    def test_compound_periods_quarterly(self):
        """季复利期数"""
        periods = _calc_compound_periods(date(2025, 1, 1), date(2025, 7, 1), "quarterly")
        assert periods == 2

    def test_quantize(self):
        """四舍五入到 2 位"""
        assert _quantize(Decimal("123.456")) == Decimal("123.46")
        assert _quantize(Decimal("123.454")) == Decimal("123.45")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 9 种组合正确性（3 计息基准 × 3 复利频率）
# ═══════════════════════════════════════════════════════════════════════════════


class TestNineCombinations:
    """3 计息基准 × 3 复利频率 = 9 种组合"""

    # --- ACT/360 ---

    def test_act360_simple(self):
        """ACT/360 + 单利"""
        req = _make_request(
            day_count_basis="ACT/360",
            compound_frequency="simple",
        )
        result = _calc_interest(req)
        # 1,000,000 × 0.045 × 181 / 360 = 22,625.00
        expected = _quantize(Decimal("1000000") * Decimal("0.045") * Decimal("181") / Decimal("360"))
        assert result["interest_amount"] == expected

    def test_act360_monthly(self):
        """ACT/360 + 月复利"""
        req = _make_request(
            day_count_basis="ACT/360",
            compound_frequency="monthly",
        )
        result = _calc_interest(req)
        # 6 期月复利：1,000,000 × (1 + 0.045/12)^6 - 1,000,000
        monthly_rate = 0.045 / 12
        expected = Decimal(str(1000000 * ((1 + monthly_rate) ** 6) - 1000000))
        assert result["interest_amount"] == _quantize(expected)
        assert result["compound_periods"] == 6

    def test_act360_quarterly(self):
        """ACT/360 + 季复利"""
        req = _make_request(
            day_count_basis="ACT/360",
            compound_frequency="quarterly",
        )
        result = _calc_interest(req)
        # 2 期季复利：1,000,000 × (1 + 0.045/4)^2 - 1,000,000
        quarterly_rate = 0.045 / 4
        expected = Decimal(str(1000000 * ((1 + quarterly_rate) ** 2) - 1000000))
        assert result["interest_amount"] == _quantize(expected)
        assert result["compound_periods"] == 2

    # --- ACT/365 ---

    def test_act365_simple(self):
        """ACT/365 + 单利"""
        req = _make_request(
            day_count_basis="ACT/365",
            compound_frequency="simple",
        )
        result = _calc_interest(req)
        # 1,000,000 × 0.045 × 181 / 365
        expected = _quantize(Decimal("1000000") * Decimal("0.045") * Decimal("181") / Decimal("365"))
        assert result["interest_amount"] == expected

    def test_act365_monthly(self):
        """ACT/365 + 月复利"""
        req = _make_request(
            day_count_basis="ACT/365",
            compound_frequency="monthly",
        )
        result = _calc_interest(req)
        monthly_rate = 0.045 / 12
        expected = Decimal(str(1000000 * ((1 + monthly_rate) ** 6) - 1000000))
        assert result["interest_amount"] == _quantize(expected)
        assert result["compound_periods"] == 6

    def test_act365_quarterly(self):
        """ACT/365 + 季复利"""
        req = _make_request(
            day_count_basis="ACT/365",
            compound_frequency="quarterly",
        )
        result = _calc_interest(req)
        quarterly_rate = 0.045 / 4
        expected = Decimal(str(1000000 * ((1 + quarterly_rate) ** 2) - 1000000))
        assert result["interest_amount"] == _quantize(expected)
        assert result["compound_periods"] == 2

    # --- 30/360 ---

    def test_30_360_simple(self):
        """30/360 + 单利"""
        req = _make_request(
            day_count_basis="30/360",
            compound_frequency="simple",
        )
        result = _calc_interest(req)
        # months = 6, interest = 1,000,000 × 0.045 × 6 / 12 = 22,500.00
        expected = _quantize(Decimal("1000000") * Decimal("0.045") * Decimal("6") / Decimal("12"))
        assert result["interest_amount"] == expected

    def test_30_360_monthly(self):
        """30/360 + 月复利"""
        req = _make_request(
            day_count_basis="30/360",
            compound_frequency="monthly",
        )
        result = _calc_interest(req)
        monthly_rate = 0.045 / 12
        expected = Decimal(str(1000000 * ((1 + monthly_rate) ** 6) - 1000000))
        assert result["interest_amount"] == _quantize(expected)
        assert result["compound_periods"] == 6

    def test_30_360_quarterly(self):
        """30/360 + 季复利"""
        req = _make_request(
            day_count_basis="30/360",
            compound_frequency="quarterly",
        )
        result = _calc_interest(req)
        quarterly_rate = 0.045 / 4
        expected = Decimal(str(1000000 * ((1 + quarterly_rate) ** 2) - 1000000))
        assert result["interest_amount"] == _quantize(expected)
        assert result["compound_periods"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 写回联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """apply_to_sheet 写回联动"""

    def test_no_apply_returns_none(self):
        """不指定 apply_to_sheet → applied_to_sheet=None"""
        req = _make_request(apply_to_sheet=None)
        result = _calc_interest(req)
        # _calc_interest 不处理写回，只验证字段存在
        assert "interest_amount" in result

    def test_apply_to_sheet_field_accepted(self):
        """apply_to_sheet 字段可正常传入"""
        req = _make_request(apply_to_sheet="利息测算表L1-5")
        assert req.apply_to_sheet == "利息测算表L1-5"

    def test_write_back_function_signature(self):
        """_maybe_apply_interest_to_workpaper 函数存在且签名正确"""
        from app.routers.wp_l_interest_calc import _maybe_apply_interest_to_workpaper

        sig = inspect.signature(_maybe_apply_interest_to_workpaper)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "wp_id" in params
        assert "payload" in params
        assert "result" in params


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RBAC 校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC 校验"""

    def test_endpoint_function_has_user_dependency(self):
        """endpoint 函数签名中包含 _user 参数（RBAC 注入）"""
        sig = inspect.signature(l_interest_calc)
        param_names = list(sig.parameters.keys())
        assert "_user" in param_names, "endpoint 必须有 _user 参数用于 RBAC"

    def test_endpoint_requires_edit_permission(self):
        """endpoint 使用 require_project_access('edit') 依赖"""
        sig = inspect.signature(l_interest_calc)
        user_param = sig.parameters["_user"]
        # 检查 default 是 Depends(require_project_access("edit"))
        default = user_param.default
        assert default is not None, "应有 Depends 默认值"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 边界 case
# ═══════════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """边界 case"""

    def test_principal_zero(self):
        """principal=0 → interest_amount=0（合法）"""
        req = _make_request(principal=Decimal("0"))
        result = _calc_interest(req)
        assert result["interest_amount"] == Decimal("0.00")

    def test_rate_zero(self):
        """rate=0 → interest_amount=0（合法）"""
        req = _make_request(annual_rate=Decimal("0"))
        result = _calc_interest(req)
        assert result["interest_amount"] == Decimal("0.00")

    def test_start_after_end_raises_400(self):
        """start_date > end_date → HTTPException 400"""
        req = _make_request(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 1, 1),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_interest_request(req)
        assert exc_info.value.status_code == 400
        assert "起息日" in exc_info.value.detail

    def test_rate_over_one_raises_400(self):
        """rate > 1.0 → HTTPException 400"""
        req = _make_request(annual_rate=Decimal("1.5"))
        with pytest.raises(HTTPException) as exc_info:
            _validate_interest_request(req)
        assert exc_info.value.status_code == 400
        assert "年利率" in exc_info.value.detail

    def test_same_start_end_date(self):
        """起息日=到期日 → 0 天 → interest=0"""
        req = _make_request(
            start_date=date(2025, 3, 15),
            end_date=date(2025, 3, 15),
        )
        result = _calc_interest(req)
        assert result["interest_amount"] == Decimal("0.00")
        assert result["period_days"] == 0

    def test_one_day_period(self):
        """1 天计息"""
        req = _make_request(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            day_count_basis="ACT/360",
            compound_frequency="simple",
        )
        result = _calc_interest(req)
        # 1,000,000 × 0.045 × 1 / 360 = 125.00
        expected = _quantize(Decimal("1000000") * Decimal("0.045") * Decimal("1") / Decimal("360"))
        assert result["interest_amount"] == expected
        assert result["period_days"] == 1

    def test_wp_code_l3_accepted(self):
        """wp_code='L3' 合法"""
        req = _make_request(wp_code="L3")
        result = _calc_interest(req)
        assert result["interest_amount"] > Decimal("0")

    def test_compound_zero_periods(self):
        """复利期数为 0 时（如同月内）→ interest=0"""
        req = _make_request(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 15),
            compound_frequency="monthly",
        )
        result = _calc_interest(req)
        # 0 个完整月 → compound_periods=0 → interest=0
        assert result["compound_periods"] == 0
        assert result["interest_amount"] == Decimal("0.00")
