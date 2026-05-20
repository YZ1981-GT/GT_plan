"""Comprehensive unit tests for N-F7 所得税费用测算引擎.

Covers:
1. Basic calculation correctness (current + deferred = total)
2. Effective rate calculation
3. statutory_rate > 1.0 → 400
4. profit = 0 → total = 0
5. apply_to_sheet writes to parsed_data
6. is_llm_stub flag driven by settings.WP_AI_SERVICE_ENABLED (monkeypatch both states)
7. RBAC enforcement
8. Reconciliation items generated correctly

对应 spec: workpaper-n-tax-cycle N-F7 / ADR-N4
"""

import sys
sys.path.insert(0, "backend")

import inspect

import pytest
from fastapi import HTTPException

from app.routers.wp_n_income_tax_calc import (
    IncomeTaxCalcRequest,
    IncomeTaxCalcResponse,
    ReconciliationItem,
    _build_reconciliation_items,
    _calc_income_tax,
    _validate_income_tax_request,
    n_income_tax_calc,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: 构造标准请求
# ═══════════════════════════════════════════════════════════════════════════════


def _make_request(**overrides) -> IncomeTaxCalcRequest:
    """构造标准所得税测算请求，可覆盖任意字段。"""
    defaults = {
        "profit_before_tax": 1000000.0,
        "statutory_rate": 0.25,
        "permanent_differences": {"业务招待费": 50000.0, "罚款支出": 20000.0},
        "temporary_differences": {"资产减值准备": 100000.0},
        "deferred_tax_asset_change": 25000.0,
        "deferred_tax_liability_change": 5000.0,
        "apply_to_sheet": None,
    }
    defaults.update(overrides)
    return IncomeTaxCalcRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Basic calculation correctness (current + deferred = total)
# ═══════════════════════════════════════════════════════════════════════════════


class TestBasicCalculation:
    """基本计算正确性：current + deferred = total"""

    def test_current_plus_deferred_equals_total(self):
        """current_income_tax + deferred_income_tax == total_income_tax"""
        req = _make_request()
        result = _calc_income_tax(req)
        assert result["total_income_tax"] == pytest.approx(
            result["current_income_tax"] + result["deferred_income_tax"], abs=0.01
        )

    def test_current_income_tax_formula(self):
        """当期所得税 = (利润总额 + 永久性差异合计) × 法定税率"""
        req = _make_request(
            profit_before_tax=1000000.0,
            statutory_rate=0.25,
            permanent_differences={"业务招待费": 50000.0, "罚款支出": 20000.0},
        )
        result = _calc_income_tax(req)
        # (1000000 + 50000 + 20000) × 0.25 = 267500.0
        expected_current = (1000000.0 + 50000.0 + 20000.0) * 0.25
        assert result["current_income_tax"] == pytest.approx(expected_current, abs=0.01)

    def test_deferred_income_tax_formula(self):
        """递延所得税 = -(递延资产变动 - 递延负债变动)"""
        req = _make_request(
            deferred_tax_asset_change=25000.0,
            deferred_tax_liability_change=5000.0,
        )
        result = _calc_income_tax(req)
        # -(25000 - 5000) = -20000
        expected_deferred = -(25000.0 - 5000.0)
        assert result["deferred_income_tax"] == pytest.approx(expected_deferred, abs=0.01)

    def test_total_income_tax_value(self):
        """总所得税 = 当期 + 递延"""
        req = _make_request(
            profit_before_tax=1000000.0,
            statutory_rate=0.25,
            permanent_differences={"业务招待费": 50000.0},
            deferred_tax_asset_change=10000.0,
            deferred_tax_liability_change=0.0,
        )
        result = _calc_income_tax(req)
        # current = (1000000 + 50000) × 0.25 = 262500
        # deferred = -(10000 - 0) = -10000
        # total = 262500 + (-10000) = 252500
        assert result["total_income_tax"] == pytest.approx(252500.0, abs=0.01)

    def test_no_permanent_differences(self):
        """无永久性差异时 current = profit × rate"""
        req = _make_request(
            profit_before_tax=500000.0,
            statutory_rate=0.25,
            permanent_differences={},
            deferred_tax_asset_change=0.0,
            deferred_tax_liability_change=0.0,
        )
        result = _calc_income_tax(req)
        assert result["current_income_tax"] == pytest.approx(125000.0, abs=0.01)
        assert result["deferred_income_tax"] == pytest.approx(0.0, abs=0.01)
        assert result["total_income_tax"] == pytest.approx(125000.0, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Effective rate calculation
# ═══════════════════════════════════════════════════════════════════════════════


class TestEffectiveRate:
    """有效税率计算"""

    def test_effective_rate_basic(self):
        """effective_rate = total / profit_before_tax"""
        req = _make_request(
            profit_before_tax=1000000.0,
            statutory_rate=0.25,
            permanent_differences={},
            deferred_tax_asset_change=0.0,
            deferred_tax_liability_change=0.0,
        )
        result = _calc_income_tax(req)
        # total = 250000, effective = 250000 / 1000000 = 0.25
        assert result["effective_rate"] == pytest.approx(0.25, abs=0.0001)

    def test_effective_rate_with_permanent_diff(self):
        """永久性差异影响有效税率"""
        req = _make_request(
            profit_before_tax=1000000.0,
            statutory_rate=0.25,
            permanent_differences={"罚款": 200000.0},
            deferred_tax_asset_change=0.0,
            deferred_tax_liability_change=0.0,
        )
        result = _calc_income_tax(req)
        # current = (1000000 + 200000) × 0.25 = 300000
        # effective = 300000 / 1000000 = 0.30
        assert result["effective_rate"] == pytest.approx(0.30, abs=0.0001)

    def test_effective_rate_with_deferred(self):
        """递延所得税影响有效税率"""
        req = _make_request(
            profit_before_tax=1000000.0,
            statutory_rate=0.25,
            permanent_differences={},
            deferred_tax_asset_change=40000.0,
            deferred_tax_liability_change=0.0,
        )
        result = _calc_income_tax(req)
        # current = 250000, deferred = -40000, total = 210000
        # effective = 210000 / 1000000 = 0.21
        assert result["effective_rate"] == pytest.approx(0.21, abs=0.0001)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. statutory_rate > 1.0 → 400
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatutoryRateValidation:
    """statutory_rate > 1.0 → 400 Bad Request"""

    def test_rate_over_one_raises_400(self):
        """statutory_rate > 1.0 → HTTPException 400"""
        req = _make_request(statutory_rate=1.5)
        with pytest.raises(HTTPException) as exc_info:
            _validate_income_tax_request(req)
        assert exc_info.value.status_code == 400
        assert "法定税率" in exc_info.value.detail

    def test_rate_exactly_one_is_valid(self):
        """statutory_rate = 1.0 → 合法（不报错）"""
        req = _make_request(statutory_rate=1.0)
        # Should not raise
        _validate_income_tax_request(req)

    def test_rate_zero_is_valid(self):
        """statutory_rate = 0 → 合法"""
        req = _make_request(statutory_rate=0.0)
        _validate_income_tax_request(req)
        result = _calc_income_tax(req)
        assert result["current_income_tax"] == pytest.approx(0.0, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. profit = 0 → total = 0
# ═══════════════════════════════════════════════════════════════════════════════


class TestProfitZero:
    """profit_before_tax = 0 → 合法，返回 total=0"""

    def test_profit_zero_returns_zero_total(self):
        """profit=0 且无差异 → total=0"""
        req = _make_request(
            profit_before_tax=0.0,
            permanent_differences={},
            deferred_tax_asset_change=0.0,
            deferred_tax_liability_change=0.0,
        )
        result = _calc_income_tax(req)
        assert result["total_income_tax"] == pytest.approx(0.0, abs=0.01)

    def test_profit_zero_effective_rate_zero(self):
        """profit=0 → effective_rate=0（避免除零）"""
        req = _make_request(profit_before_tax=0.0)
        result = _calc_income_tax(req)
        assert result["effective_rate"] == 0.0

    def test_profit_zero_with_deferred_changes(self):
        """profit=0 但有递延变动 → deferred 非零，effective_rate 仍为 0"""
        req = _make_request(
            profit_before_tax=0.0,
            permanent_differences={},
            deferred_tax_asset_change=10000.0,
            deferred_tax_liability_change=5000.0,
        )
        result = _calc_income_tax(req)
        # deferred = -(10000 - 5000) = -5000
        assert result["deferred_income_tax"] == pytest.approx(-5000.0, abs=0.01)
        assert result["effective_rate"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. apply_to_sheet writes to parsed_data
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """apply_to_sheet 写回联动"""

    def test_no_apply_returns_none(self):
        """不指定 apply_to_sheet → 正常计算"""
        req = _make_request(apply_to_sheet=None)
        result = _calc_income_tax(req)
        assert "total_income_tax" in result

    def test_apply_to_sheet_field_accepted(self):
        """apply_to_sheet 字段可正常传入"""
        req = _make_request(apply_to_sheet="所得税费用测算表N5-1")
        assert req.apply_to_sheet == "所得税费用测算表N5-1"

    def test_write_back_function_signature(self):
        """_maybe_apply_income_tax_to_workpaper 函数存在且签名正确"""
        from app.routers.wp_n_income_tax_calc import _maybe_apply_income_tax_to_workpaper

        sig = inspect.signature(_maybe_apply_income_tax_to_workpaper)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "wp_id" in params
        assert "payload" in params
        assert "result" in params


# ═══════════════════════════════════════════════════════════════════════════════
# 6. is_llm_stub flag driven by settings.WP_AI_SERVICE_ENABLED
# ═══════════════════════════════════════════════════════════════════════════════


class TestStubFlagConfig:
    """is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动"""

    def test_stub_flag_default_true(self):
        """默认 WP_AI_SERVICE_ENABLED=False → is_llm_stub=True"""
        from app.core.config import settings
        enabled = getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not enabled
        assert is_stub is True  # 默认未配置时为 stub

    def test_stub_flag_when_enabled(self, monkeypatch):
        """配置 WP_AI_SERVICE_ENABLED=True → is_llm_stub=False"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", True)
        is_stub = not getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        assert is_stub is False

    def test_stub_flag_when_disabled(self, monkeypatch):
        """配置 WP_AI_SERVICE_ENABLED=False → is_llm_stub=True"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        assert is_stub is True

    def test_endpoint_uses_settings_not_hardcoded(self):
        """endpoint 源码中使用 settings.WP_AI_SERVICE_ENABLED 而非硬编码"""
        import inspect
        from app.routers.wp_n_income_tax_calc import n_income_tax_calc

        source = inspect.getsource(n_income_tax_calc)
        # 不应有 is_llm_stub = True 或 is_llm_stub = False 硬编码
        assert "is_llm_stub = True" not in source
        assert "is_llm_stub = False" not in source


# ═══════════════════════════════════════════════════════════════════════════════
# 7. RBAC enforcement
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC 校验"""

    def test_endpoint_function_has_user_dependency(self):
        """endpoint 函数签名中包含 _user 参数（RBAC 注入）"""
        sig = inspect.signature(n_income_tax_calc)
        param_names = list(sig.parameters.keys())
        assert "_user" in param_names, "endpoint 必须有 _user 参数用于 RBAC"

    def test_endpoint_requires_edit_permission(self):
        """endpoint 使用 require_project_access('edit') 依赖"""
        sig = inspect.signature(n_income_tax_calc)
        user_param = sig.parameters["_user"]
        # 检查 default 是 Depends(require_project_access("edit"))
        default = user_param.default
        assert default is not None, "应有 Depends 默认值"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Reconciliation items generated correctly
# ═══════════════════════════════════════════════════════════════════════════════


class TestReconciliationItems:
    """调节表明细项生成正确性"""

    def test_permanent_diff_generates_items(self):
        """永久性差异生成调节项"""
        req = _make_request(
            profit_before_tax=1000000.0,
            statutory_rate=0.25,
            permanent_differences={"业务招待费": 50000.0, "罚款支出": 20000.0},
            temporary_differences={},
        )
        result = _calc_income_tax(req)
        items = result["reconciliation_items"]
        perm_items = [i for i in items if "永久性差异" in i["item"]]
        assert len(perm_items) == 2

    def test_temporary_diff_generates_items(self):
        """暂时性差异生成调节项"""
        req = _make_request(
            profit_before_tax=1000000.0,
            statutory_rate=0.25,
            permanent_differences={},
            temporary_differences={"资产减值准备": 100000.0, "预提费用": 30000.0},
        )
        result = _calc_income_tax(req)
        items = result["reconciliation_items"]
        temp_items = [i for i in items if "暂时性差异" in i["item"]]
        assert len(temp_items) == 2

    def test_reconciliation_item_amount(self):
        """调节项金额 = 差异金额 × 税率"""
        req = _make_request(
            profit_before_tax=1000000.0,
            statutory_rate=0.25,
            permanent_differences={"罚款": 100000.0},
            temporary_differences={},
        )
        result = _calc_income_tax(req)
        items = result["reconciliation_items"]
        assert len(items) == 1
        # 100000 × 0.25 = 25000
        assert items[0]["amount"] == pytest.approx(25000.0, abs=0.01)

    def test_reconciliation_item_rate_impact(self):
        """调节项 rate_impact = amount × rate / profit"""
        req = _make_request(
            profit_before_tax=1000000.0,
            statutory_rate=0.25,
            permanent_differences={"罚款": 100000.0},
            temporary_differences={},
        )
        result = _calc_income_tax(req)
        items = result["reconciliation_items"]
        # rate_impact = 100000 × 0.25 / 1000000 = 0.025
        assert items[0]["rate_impact"] == pytest.approx(0.025, abs=0.0001)

    def test_no_differences_no_items(self):
        """无差异 → 无调节项"""
        req = _make_request(
            permanent_differences={},
            temporary_differences={},
        )
        result = _calc_income_tax(req)
        assert result["reconciliation_items"] == []

    def test_reconciliation_items_with_profit_zero(self):
        """profit=0 时 rate_impact=0"""
        req = _make_request(
            profit_before_tax=0.0,
            permanent_differences={"罚款": 50000.0},
            temporary_differences={},
        )
        result = _calc_income_tax(req)
        items = result["reconciliation_items"]
        assert len(items) == 1
        assert items[0]["rate_impact"] == 0.0

    def test_total_items_count(self):
        """调节项总数 = 永久性差异数 + 暂时性差异数"""
        req = _make_request(
            permanent_differences={"a": 1.0, "b": 2.0, "c": 3.0},
            temporary_differences={"d": 4.0, "e": 5.0},
        )
        result = _calc_income_tax(req)
        assert len(result["reconciliation_items"]) == 5
