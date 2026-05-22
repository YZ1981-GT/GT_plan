"""Comprehensive unit tests for I-F2 / Sprint 3 Task 3.3 摊销引擎 — 2 methods × boundary cases + write-back + RBAC.

Covers:
- straight_line: 每月摊销严格相等 / 续提场景 / 残值率=1（无摊销）
- units_of_production: 正常计算 / total_units=0→400 / 当期>总量cap / 缺字段→422
- Validation: original_cost > 1e15 / useful_life_months > 600 / already > useful / negative cost
- Write-back: _maybe_apply_amortization_to_workpaper callable + async + 数据结构
- RBAC: require_project_access("edit") enforced on both I1 + I4 endpoints
- Cross-method consistency: 累计不超过 depreciable / 月份单调递增 / 摊销 ≥ 0

对应 spec: workpaper-i-intangible-assets-cycle I-F2 (ADR-I5) / Sprint 3 Task 3.3
"""

import sys
sys.path.insert(0, "backend")

import inspect
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.routers.wp_i_amortization import (
    AmortizationCalcRequest,
    _maybe_apply_amortization_to_workpaper,
    _run_amortization,
    _validate_request,
    router_i1,
    router_i4,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. STRAIGHT LINE — 直线法 / 剩余年限法
# ═══════════════════════════════════════════════════════════════════════════════


class TestStraightLine:
    """直线法 boundary cases（I1 摊销 / I4 直线法摊销）"""

    def _payload(self, **kwargs):
        defaults = dict(
            method="straight_line",
            original_cost=Decimal("240000"),
            residual_rate=Decimal("0"),
            useful_life_months=120,
            start_month=1,
            already_amortized_months=0,
        )
        defaults.update(kwargs)
        return AmortizationCalcRequest(**defaults)

    def test_monthly_amortization_strictly_equal(self):
        """每月摊销严格相等（除最后一月差额调整）"""
        payload = self._payload()  # 240000 / 120 = 2000
        schedule, total, remaining = _run_amortization(payload)
        assert len(schedule) == 120
        # 除最后一月外每月相等
        for entry in schedule[:-1]:
            assert entry["amortization"] == Decimal("2000.00")
        # 累计 = 原值（残值率=0）
        assert total == Decimal("240000.00")
        assert remaining == Decimal("0.00")

    def test_continuation_scenario(self):
        """续提场景：已计提 50 月，剩余 70 月"""
        payload = self._payload(useful_life_months=120, already_amortized_months=50)
        schedule, total, _ = _run_amortization(payload)
        assert len(schedule) == 70
        assert schedule[0]["month"] == 51
        assert schedule[-1]["month"] == 120
        # 总累计仍等于原值（残值率=0）
        assert total == Decimal("240000.00")

    def test_residual_rate_one_no_amortization(self):
        """残值率=1 → residual=original_cost → depreciable=0 → 无摊销"""
        payload = self._payload(residual_rate=Decimal("1"))
        schedule, total, remaining = _run_amortization(payload)
        assert schedule == []
        assert total == Decimal("0")
        # remaining = original - residual - 0 = 0
        assert remaining == Decimal("0")

    def test_residual_rate_partial(self):
        """部分残值率（无形资产很少有，但 I4 可能用到）"""
        payload = self._payload(
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
        )
        schedule, total, remaining = _run_amortization(payload)
        # depreciable = 100000 - 5000 = 95000，月摊 = 95000/60 ≈ 1583.33
        assert len(schedule) == 60
        assert total == Decimal("95000.00")
        assert remaining == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. UNITS OF PRODUCTION — 工作量法
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnitsOfProduction:
    """工作量法 boundary cases（I4-7 / 部分 I1 用工作量法的）"""

    def _payload(self, **kwargs):
        defaults = dict(
            method="units_of_production",
            original_cost=Decimal("200000"),
            residual_rate=Decimal("0"),
            useful_life_months=120,
            start_month=1,
            already_amortized_months=0,
            total_units=Decimal("50000"),
            current_period_units=Decimal("2000"),
        )
        defaults.update(kwargs)
        return AmortizationCalcRequest(**defaults)

    def test_normal_calculation(self):
        """正常：unit_dep × current_period_units"""
        payload = self._payload()
        schedule, total, _ = _run_amortization(payload)
        # unit_dep = 200000 / 50000 = 4; period_dep = 4 * 2000 = 8000
        assert len(schedule) == 1
        assert schedule[0]["amortization"] == Decimal("8000.00")
        assert total == Decimal("8000.00")

    def test_total_units_zero_returns_400(self):
        """total_units=0 → 400"""
        payload = self._payload(total_units=Decimal("0"))
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400
        assert "零" in exc_info.value.detail

    def test_current_exceeds_total_cap(self):
        """当期工作量 > 总工作量 → cap 在 depreciable"""
        payload = self._payload(
            total_units=Decimal("100"),
            current_period_units=Decimal("500"),  # 5x 超量
        )
        schedule, total, _ = _run_amortization(payload)
        # unit_dep = 200000/100 = 2000; period_dep = 2000*500 = 1,000,000 > 200000 → cap
        assert len(schedule) == 1
        assert total == Decimal("200000")

    def test_missing_total_units_returns_422(self):
        """工作量法缺 total_units → 422"""
        payload = AmortizationCalcRequest(
            method="units_of_production",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
            total_units=None,
            current_period_units=Decimal("100"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 422

    def test_missing_current_period_units_returns_422(self):
        """工作量法缺 current_period_units → 422"""
        payload = AmortizationCalcRequest(
            method="units_of_production",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
            total_units=Decimal("1000"),
            current_period_units=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 422

    def test_negative_total_units_returns_400(self):
        """total_units < 0 → 400"""
        payload = self._payload(total_units=Decimal("-100"))
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 3. VALIDATION — _validate_request 边界校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidation:
    """输入参数校验 boundary cases"""

    def test_original_cost_exceeds_1e15_returns_400(self):
        """原值 > 1e15 → 400"""
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("2e15"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400
        assert "1e15" in exc_info.value.detail

    def test_useful_life_exceeds_600_returns_400(self):
        """使用年限 > 600 → 400"""
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=601,
            start_month=1,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400
        assert "600" in exc_info.value.detail

    def test_already_exceeds_useful_returns_400(self):
        """已计提 > 使用年限 → 400"""
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
            already_amortized_months=61,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400
        assert "已计提月数" in exc_info.value.detail

    def test_negative_original_cost_returns_400(self):
        """原值为负 → 400"""
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("-100"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400
        assert "负数" in exc_info.value.detail

    def test_boundary_original_cost_exactly_1e15(self):
        """原值恰好 = 1e15 → 不报错"""
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("1e15"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
        )
        _validate_request(payload)  # no raise

    def test_boundary_useful_life_exactly_600(self):
        """使用年限恰好 = 600 → 不报错"""
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=600,
            start_month=1,
        )
        _validate_request(payload)  # no raise

    def test_valid_straight_line_passes(self):
        """合法直线法不抛异常"""
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=120,
            start_month=6,
        )
        _validate_request(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. WRITE-BACK — _maybe_apply_amortization_to_workpaper
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """Write-back helper tests"""

    def test_writeback_helper_exists_and_callable(self):
        """写回辅助函数必须存在且可调用"""
        assert callable(_maybe_apply_amortization_to_workpaper)

    def test_writeback_helper_is_async(self):
        """写回函数必须是 async（需要 DB 操作）"""
        assert inspect.iscoroutinefunction(_maybe_apply_amortization_to_workpaper)

    def test_writeback_helper_signature(self):
        """写回函数签名包含必要参数"""
        sig = inspect.signature(_maybe_apply_amortization_to_workpaper)
        param_names = list(sig.parameters.keys())
        for required in (
            "db",
            "wp_id",
            "payload",
            "schedule",
            "total_amortization",
            "remaining_book_value",
            "wp_section",
        ):
            assert required in param_names, f"missing param: {required}"

    @pytest.mark.asyncio
    async def test_writeback_skipped_when_apply_to_sheet_none(self):
        """apply_to_sheet 为空时不写回，返回 None"""
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
            apply_to_sheet=None,
        )
        # 传 None db — 应该在第一个 if 分支直接返回 None
        result = await _maybe_apply_amortization_to_workpaper(
            db=None,  # type: ignore[arg-type]
            wp_id="00000000-0000-0000-0000-000000000000",
            payload=payload,
            schedule=[],
            total_amortization=Decimal("0"),
            remaining_book_value=Decimal("100000"),
            wp_section="I1",
        )
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. RBAC — require_project_access("edit") 强制校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC enforcement tests on both I1 + I4 endpoints"""

    def test_module_uses_require_project_access_edit(self):
        """摊销引擎 router 必须用 require_project_access('edit')"""
        import app.routers.wp_i_amortization as mod
        src = inspect.getsource(mod)
        assert 'require_project_access("edit")' in src, \
            "wp_i_amortization 必须用 require_project_access('edit')"

    def test_i1_endpoint_has_user_dependency(self):
        """I1 endpoint 函数签名包含 _user 参数（RBAC 注入）"""
        from app.routers.wp_i_amortization import i1_amortization_calc
        sig = inspect.signature(i1_amortization_calc)
        assert "_user" in sig.parameters

    def test_i4_endpoint_has_user_dependency(self):
        """I4 endpoint 函数签名包含 _user 参数（RBAC 注入）"""
        from app.routers.wp_i_amortization import i4_amortization_calc
        sig = inspect.signature(i4_amortization_calc)
        assert "_user" in sig.parameters

    def test_i1_router_prefix_contains_project_id(self):
        """I1 路由前缀包含 {project_id}（RBAC 上下文）"""
        assert "{project_id}" in router_i1.prefix
        assert "/i1" in router_i1.prefix

    def test_i4_router_prefix_contains_project_id(self):
        """I4 路由前缀包含 {project_id}"""
        assert "{project_id}" in router_i4.prefix
        assert "/i4" in router_i4.prefix

    def test_endpoints_registered_in_router_registry(self):
        """两个 router 必须被 register_all_routers 注册"""
        from app.router_registry import cycle_engines
        src = inspect.getsource(cycle_engines)
        assert "wp_i_amortization" in src, "wp_i_amortization 必须在 router_registry 中注册"
        assert "router_i1" in src
        assert "router_i4" in src


# ═══════════════════════════════════════════════════════════════════════════════
# 6. INTEGRATION — 跨方法一致性
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossMethodConsistency:
    """跨方法一致性验证"""

    def test_both_methods_respect_depreciable_cap(self):
        """两种方法的累计摊销都不超过 depreciable"""
        original = Decimal("100000")
        depreciable = original  # residual_rate=0

        sl_payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=original,
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
        )
        up_payload = AmortizationCalcRequest(
            method="units_of_production",
            original_cost=original,
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
            total_units=Decimal("10000"),
            current_period_units=Decimal("500"),
        )

        sl_schedule, _, _ = _run_amortization(sl_payload)
        up_schedule, _, _ = _run_amortization(up_payload)

        for schedule in [sl_schedule, up_schedule]:
            if schedule:
                assert schedule[-1]["accumulated"] <= depreciable

    def test_straight_line_total_equals_depreciable(self):
        """直线法总摊销精确等于 depreciable"""
        original = Decimal("120000")
        residual = original * Decimal("0.05")
        depreciable = original - residual
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=original,
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=1,
        )
        schedule, total, _ = _run_amortization(payload)
        # 容许 ≤ 0.01 误差（quantize 四舍五入）
        assert abs(total - depreciable) <= Decimal("0.01")
        assert schedule[-1]["accumulated"] == total

    def test_month_numbering_monotonic(self):
        """两种方法的 month 编号严格递增"""
        sl_payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
        )
        sl_schedule, _, _ = _run_amortization(sl_payload)
        months = [s["month"] for s in sl_schedule]
        for i in range(1, len(months)):
            assert months[i] > months[i - 1]

    def test_amortization_non_negative(self):
        """两种方法的每月摊销 ≥ 0"""
        sl_payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
        )
        up_payload = AmortizationCalcRequest(
            method="units_of_production",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
            total_units=Decimal("10000"),
            current_period_units=Decimal("500"),
        )
        for payload in [sl_payload, up_payload]:
            schedule, _, _ = _run_amortization(payload)
            for entry in schedule:
                assert entry["amortization"] >= Decimal("0")

    def test_accumulated_monotonically_increasing(self):
        """直线法 accumulated 单调递增"""
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
        )
        schedule, _, _ = _run_amortization(payload)
        for i in range(1, len(schedule)):
            assert schedule[i]["accumulated"] >= schedule[i - 1]["accumulated"]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. RESPONSE STRUCTURE — _run_amortization 返回值
# ═══════════════════════════════════════════════════════════════════════════════


class TestResponseStructure:
    """计算返回值结构验证"""

    def test_run_amortization_returns_tuple_of_three(self):
        """_run_amortization 返回 (schedule, total, remaining) 三元组"""
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0"),
            useful_life_months=60,
            start_month=1,
        )
        result = _run_amortization(payload)
        assert isinstance(result, tuple)
        assert len(result) == 3
        schedule, total, remaining = result
        assert isinstance(schedule, list)
        assert isinstance(total, Decimal)
        assert isinstance(remaining, Decimal)

    def test_remaining_book_value_never_negative(self):
        """remaining_book_value 永不为负（cap 在 0）"""
        # 即使 total > depreciable（极端情况），remaining 也应 cap 在 0
        payload = AmortizationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=1,
        )
        _, _, remaining = _run_amortization(payload)
        assert remaining >= Decimal("0")
