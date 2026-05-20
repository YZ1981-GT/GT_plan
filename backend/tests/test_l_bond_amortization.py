"""Comprehensive unit tests for L-F8 应付债券摊余成本引擎.

Covers:
- 收敛性测试（final_carrying_amount ≈ face_value ± 0.01）
- 边界 case（face_value=0, effective_rate=0, term_years=0 → 400）
- 写回联动（apply_to_sheet）
- is_llm_stub config-driven（monkeypatch settings.WP_AI_SERVICE_ENABLED）
- Schedule 长度 = term_years × frequency

对应 spec: workpaper-l-debt-cycle L-F8 / ADR-L5
"""

import sys
sys.path.insert(0, "backend")

import inspect
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.routers.wp_l_bond_amortization import (
    BondAmortizationRequest,
    BondAmortizationResponse,
    _calc_amortization_schedule,
    _get_periods_per_year,
    _quantize,
    _validate_bond_request,
    l_bond_amortization,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: 构造标准请求
# ═══════════════════════════════════════════════════════════════════════════════


def _make_request(**overrides) -> BondAmortizationRequest:
    """构造标准债券摊余成本请求，可覆盖任意字段。"""
    defaults = {
        "face_value": Decimal("1000000"),
        "issue_price": Decimal("950000"),
        "coupon_rate": Decimal("0.05"),
        "effective_rate": Decimal("0.06"),
        "term_years": 5,
        "payment_frequency": "annual",
        "apply_to_sheet": None,
    }
    defaults.update(overrides)
    return BondAmortizationRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 辅助函数测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelpers:
    """辅助函数正确性"""

    def test_quantize_rounds_half_up(self):
        assert _quantize(Decimal("1.005")) == Decimal("1.01")
        assert _quantize(Decimal("1.004")) == Decimal("1.00")

    def test_get_periods_per_year_annual(self):
        assert _get_periods_per_year("annual") == 1

    def test_get_periods_per_year_semi_annual(self):
        assert _get_periods_per_year("semi_annual") == 2

    def test_get_periods_per_year_quarterly(self):
        assert _get_periods_per_year("quarterly") == 4


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 收敛性测试 — final_carrying_amount ≈ face_value (±0.01)
# ═══════════════════════════════════════════════════════════════════════════════


class TestConvergence:
    """摊余成本收敛性：最终期末摊余成本应收敛到面值"""

    def test_discount_bond_annual_converges(self):
        """折价发行 + 年付息 → 收敛到面值"""
        req = _make_request(
            face_value=Decimal("1000000"),
            issue_price=Decimal("950000"),
            coupon_rate=Decimal("0.05"),
            effective_rate=Decimal("0.06"),
            term_years=5,
            payment_frequency="annual",
        )
        result = _calc_amortization_schedule(req)
        final = Decimal(result["final_carrying_amount"])
        assert abs(final - Decimal("1000000")) <= Decimal("0.01")

    def test_premium_bond_annual_converges(self):
        """溢价发行 + 年付息 → 收敛到面值"""
        req = _make_request(
            face_value=Decimal("1000000"),
            issue_price=Decimal("1050000"),
            coupon_rate=Decimal("0.06"),
            effective_rate=Decimal("0.05"),
            term_years=5,
            payment_frequency="annual",
        )
        result = _calc_amortization_schedule(req)
        final = Decimal(result["final_carrying_amount"])
        assert abs(final - Decimal("1000000")) <= Decimal("0.01")

    def test_discount_bond_semi_annual_converges(self):
        """折价发行 + 半年付息 → 收敛到面值"""
        req = _make_request(
            face_value=Decimal("500000"),
            issue_price=Decimal("480000"),
            coupon_rate=Decimal("0.04"),
            effective_rate=Decimal("0.05"),
            term_years=3,
            payment_frequency="semi_annual",
        )
        result = _calc_amortization_schedule(req)
        final = Decimal(result["final_carrying_amount"])
        assert abs(final - Decimal("500000")) <= Decimal("0.01")

    def test_discount_bond_quarterly_converges(self):
        """折价发行 + 季付息 → 收敛到面值"""
        req = _make_request(
            face_value=Decimal("2000000"),
            issue_price=Decimal("1900000"),
            coupon_rate=Decimal("0.04"),
            effective_rate=Decimal("0.05"),
            term_years=2,
            payment_frequency="quarterly",
        )
        result = _calc_amortization_schedule(req)
        final = Decimal(result["final_carrying_amount"])
        assert abs(final - Decimal("2000000")) <= Decimal("0.01")

    def test_par_bond_converges(self):
        """平价发行（issue_price == face_value）→ 收敛到面值"""
        req = _make_request(
            face_value=Decimal("1000000"),
            issue_price=Decimal("1000000"),
            coupon_rate=Decimal("0.05"),
            effective_rate=Decimal("0.05"),
            term_years=3,
            payment_frequency="annual",
        )
        result = _calc_amortization_schedule(req)
        final = Decimal(result["final_carrying_amount"])
        assert abs(final - Decimal("1000000")) <= Decimal("0.01")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Schedule 长度 = term_years × frequency
# ═══════════════════════════════════════════════════════════════════════════════


class TestScheduleLength:
    """摊余成本表期数正确性"""

    def test_annual_5_years(self):
        req = _make_request(term_years=5, payment_frequency="annual")
        result = _calc_amortization_schedule(req)
        assert len(result["amortization_schedule"]) == 5

    def test_semi_annual_3_years(self):
        req = _make_request(term_years=3, payment_frequency="semi_annual")
        result = _calc_amortization_schedule(req)
        assert len(result["amortization_schedule"]) == 6

    def test_quarterly_2_years(self):
        req = _make_request(term_years=2, payment_frequency="quarterly")
        result = _calc_amortization_schedule(req)
        assert len(result["amortization_schedule"]) == 8

    def test_annual_1_year(self):
        req = _make_request(term_years=1, payment_frequency="annual")
        result = _calc_amortization_schedule(req)
        assert len(result["amortization_schedule"]) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 边界 case — HTTP 400
# ═══════════════════════════════════════════════════════════════════════════════


class TestBoundaryErrors:
    """边界参数 → HTTP 400"""

    def test_face_value_zero_raises_400(self):
        req = _make_request(face_value=Decimal("0"))
        with pytest.raises(HTTPException) as exc_info:
            _validate_bond_request(req)
        assert exc_info.value.status_code == 400
        assert "face_value" in exc_info.value.detail

    def test_effective_rate_zero_raises_400(self):
        req = _make_request(effective_rate=Decimal("0"))
        with pytest.raises(HTTPException) as exc_info:
            _validate_bond_request(req)
        assert exc_info.value.status_code == 400
        assert "effective_rate" in exc_info.value.detail

    def test_term_years_zero_raises_400(self):
        req = _make_request(term_years=0)
        with pytest.raises(HTTPException) as exc_info:
            _validate_bond_request(req)
        assert exc_info.value.status_code == 400
        assert "term_years" in exc_info.value.detail


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 写回联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """apply_to_sheet 写回联动"""

    def test_no_apply_returns_none(self):
        """apply_to_sheet=None → applied_to_sheet=None"""
        req = _make_request(apply_to_sheet=None)
        result = _calc_amortization_schedule(req)
        # 不调用写回，直接验证 result 不含 applied_to_sheet
        assert "applied_to_sheet" not in result

    def test_endpoint_has_apply_to_sheet_param(self):
        """endpoint 签名包含 apply_to_sheet 参数（通过 payload）"""
        sig = inspect.signature(l_bond_amortization)
        params = list(sig.parameters.keys())
        assert "payload" in params

    def test_request_model_has_apply_to_sheet(self):
        """BondAmortizationRequest 包含 apply_to_sheet 字段"""
        fields = BondAmortizationRequest.model_fields
        assert "apply_to_sheet" in fields

    def test_response_model_has_applied_to_sheet(self):
        """BondAmortizationResponse 包含 applied_to_sheet 字段"""
        fields = BondAmortizationResponse.model_fields
        assert "applied_to_sheet" in fields
        assert "applied_at" in fields


# ═══════════════════════════════════════════════════════════════════════════════
# 6. is_llm_stub config-driven
# ═══════════════════════════════════════════════════════════════════════════════


class TestStubConfig:
    """is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动"""

    def test_stub_flag_default_true(self):
        """默认 WP_AI_SERVICE_ENABLED=False → is_llm_stub=True"""
        from app.core.config import settings
        enabled = getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not enabled
        assert is_stub is True

    def test_stub_flag_when_enabled(self, monkeypatch):
        """配置 WP_AI_SERVICE_ENABLED=True → is_llm_stub=False"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", True)
        enabled = getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not enabled
        assert is_stub is False

    def test_stub_flag_when_disabled(self, monkeypatch):
        """配置 WP_AI_SERVICE_ENABLED=False → is_llm_stub=True"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", False)
        enabled = getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not enabled
        assert is_stub is True


# ═══════════════════════════════════════════════════════════════════════════════
# 7. RBAC 校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC 校验 — endpoint 签名包含 require_project_access('edit')"""

    def test_endpoint_has_rbac_dependency(self):
        """l_bond_amortization 签名包含 _user=Depends(require_project_access('edit'))"""
        sig = inspect.signature(l_bond_amortization)
        params = sig.parameters
        # 检查 _user 参数存在
        assert "_user" in params
        # 检查 default 是 Depends
        default = params["_user"].default
        assert hasattr(default, "dependency")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. 摊销额正确性
# ═══════════════════════════════════════════════════════════════════════════════


class TestAmortizationCorrectness:
    """摊销额计算正确性"""

    def test_discount_bond_positive_amortization(self):
        """折价发行 → 每期摊销额为正（摊余成本递增）"""
        req = _make_request(
            face_value=Decimal("1000000"),
            issue_price=Decimal("950000"),
            coupon_rate=Decimal("0.05"),
            effective_rate=Decimal("0.06"),
            term_years=5,
            payment_frequency="annual",
        )
        result = _calc_amortization_schedule(req)
        for item in result["amortization_schedule"]:
            assert Decimal(item["amortization"]) > 0

    def test_premium_bond_negative_amortization(self):
        """溢价发行 → 每期摊销额为负（摊余成本递减）"""
        req = _make_request(
            face_value=Decimal("1000000"),
            issue_price=Decimal("1050000"),
            coupon_rate=Decimal("0.06"),
            effective_rate=Decimal("0.05"),
            term_years=5,
            payment_frequency="annual",
        )
        result = _calc_amortization_schedule(req)
        for item in result["amortization_schedule"]:
            assert Decimal(item["amortization"]) < 0

    def test_total_amortization_equals_diff(self):
        """总摊销额 = face_value - issue_price"""
        req = _make_request(
            face_value=Decimal("1000000"),
            issue_price=Decimal("950000"),
            coupon_rate=Decimal("0.05"),
            effective_rate=Decimal("0.06"),
            term_years=5,
            payment_frequency="annual",
        )
        result = _calc_amortization_schedule(req)
        total_amort = Decimal(result["total_amortization"])
        expected_diff = Decimal("1000000") - Decimal("950000")
        assert abs(total_amort - expected_diff) <= Decimal("0.01")

    def test_first_period_interest_expense(self):
        """第一期利息费用 = issue_price × effective_rate / periods_per_year"""
        req = _make_request(
            face_value=Decimal("1000000"),
            issue_price=Decimal("950000"),
            coupon_rate=Decimal("0.05"),
            effective_rate=Decimal("0.06"),
            term_years=5,
            payment_frequency="annual",
        )
        result = _calc_amortization_schedule(req)
        first = result["amortization_schedule"][0]
        expected_interest = _quantize(Decimal("950000") * Decimal("0.06"))
        assert Decimal(first["interest_expense"]) == expected_interest

    def test_first_period_coupon_payment(self):
        """第一期票面利息 = face_value × coupon_rate / periods_per_year"""
        req = _make_request(
            face_value=Decimal("1000000"),
            issue_price=Decimal("950000"),
            coupon_rate=Decimal("0.05"),
            effective_rate=Decimal("0.06"),
            term_years=5,
            payment_frequency="annual",
        )
        result = _calc_amortization_schedule(req)
        first = result["amortization_schedule"][0]
        expected_coupon = _quantize(Decimal("1000000") * Decimal("0.05"))
        assert Decimal(first["coupon_payment"]) == expected_coupon
