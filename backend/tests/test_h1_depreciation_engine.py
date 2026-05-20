"""Comprehensive unit tests for H-F11 depreciation engine — 4 methods × boundary cases + write-back + RBAC.

Covers:
- straight_line: 每月折旧严格相等 / 续提场景 / 原值=残值(无折旧) / very small cost / max useful_life
- double_declining: 前期加速 / 剩余≤2年切换直线 / 累计不超过depreciable / 短期(≤24月)
- sum_of_years: 加速折旧(前期>后期) / 续提场景 / 累计不超过depreciable / 不足整年
- units_of_production: 正常计算 / total_units=0→400 / 当期>总量时cap / missing fields→422
- Validation: original_cost > 1e15 / useful_life_months > 600 / already > useful / negative cost
- Write-back: _maybe_apply_depreciation_to_workpaper callable + data structure
- RBAC: require_project_access("edit") enforced on endpoint

对应 spec: workpaper-h-fixed-assets-cycle H-F11
"""

import sys
sys.path.insert(0, "backend")

import inspect
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.routers.wp_h_depreciation import (
    DepreciationCalcRequest,
    _calc_double_declining,
    _calc_straight_line,
    _calc_sum_of_years,
    _calc_units_of_production,
    _maybe_apply_depreciation_to_workpaper,
    _quantize,
    _validate_request,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. STRAIGHT LINE — 直线法
# ═══════════════════════════════════════════════════════════════════════════════


class TestStraightLine:
    """直线法 boundary cases"""

    def test_monthly_depreciation_strictly_equal(self):
        """每月折旧严格相等（除最后一月差额调整）"""
        schedule = _calc_straight_line(Decimal("240000"), Decimal("24000"), 120, 0)
        assert len(schedule) == 120
        # monthly = (240000 - 24000) / 120 = 1800
        expected_monthly = Decimal("1800.00")
        # All months except last should be exactly equal
        for entry in schedule[:-1]:
            assert entry["depreciation"] == expected_monthly
        # Last month: accumulated should equal depreciable exactly
        assert schedule[-1]["accumulated"] == Decimal("216000.00")

    def test_continuation_scenario(self):
        """续提场景：已计提 50 月，剩余 10 月"""
        schedule = _calc_straight_line(Decimal("120000"), Decimal("12000"), 60, 50)
        assert len(schedule) == 10
        assert schedule[0]["month"] == 51
        assert schedule[-1]["month"] == 60
        # Each month still = (120000-12000)/60 = 1800
        for entry in schedule[:-1]:
            assert entry["depreciation"] == Decimal("1800.00")

    def test_original_equals_residual_no_depreciation(self):
        """原值=残值 → depreciable=0 → 无折旧"""
        schedule = _calc_straight_line(Decimal("50000"), Decimal("50000"), 60, 0)
        assert schedule == []

    def test_very_small_original_cost(self):
        """极小原值（1.00）仍能正确计算"""
        schedule = _calc_straight_line(Decimal("1.00"), Decimal("0.05"), 12, 0)
        assert len(schedule) == 12
        # depreciable = 0.95, monthly = 0.95/12 ≈ 0.08
        assert all(entry["depreciation"] >= Decimal("0") for entry in schedule)
        # Total accumulated should equal depreciable
        assert schedule[-1]["accumulated"] == Decimal("0.95")

    def test_max_useful_life_600_months(self):
        """最大使用年限 600 月（50 年）"""
        schedule = _calc_straight_line(Decimal("6000000"), Decimal("600000"), 600, 0)
        assert len(schedule) == 600
        # monthly = 5400000 / 600 = 9000
        assert schedule[0]["depreciation"] == Decimal("9000.00")
        assert schedule[-1]["accumulated"] == Decimal("5400000.00")

    def test_residual_rate_zero(self):
        """残值率=0 → 全额折旧"""
        schedule = _calc_straight_line(Decimal("100000"), Decimal("0"), 60, 0)
        assert len(schedule) == 60
        # monthly = 100000 / 60 ≈ 1666.67
        assert schedule[0]["depreciation"] == Decimal("1666.67")
        assert schedule[-1]["accumulated"] == Decimal("100000.00")

    def test_residual_rate_one_full_residual(self):
        """残值率=1 → residual=original_cost → depreciable=0 → 无折旧"""
        residual = _quantize(Decimal("100000") * Decimal("1"))
        schedule = _calc_straight_line(Decimal("100000"), residual, 60, 0)
        assert schedule == []

    def test_already_depreciated_equals_useful_life(self):
        """已计提月数=使用年限 → 无剩余月份"""
        schedule = _calc_straight_line(Decimal("120000"), Decimal("12000"), 60, 60)
        assert schedule == []


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DOUBLE DECLINING — 双倍余额递减法
# ═══════════════════════════════════════════════════════════════════════════════


class TestDoubleDeclining:
    """双倍余额递减法 boundary cases"""

    def test_accelerated_front_loading(self):
        """前期折旧 > 后期折旧（加速特性）"""
        schedule = _calc_double_declining(Decimal("100000"), Decimal("5000"), 60, 0)
        assert len(schedule) == 60
        # First month depreciation > last month depreciation
        assert schedule[0]["depreciation"] > schedule[-1]["depreciation"]
        # First year average > last year average
        first_year_total = sum(s["depreciation"] for s in schedule[:12])
        last_year_total = sum(s["depreciation"] for s in schedule[-12:])
        assert first_year_total > last_year_total

    def test_switch_to_straight_line_at_24_months(self):
        """剩余≤24月切换为直线法验证"""
        schedule = _calc_double_declining(Decimal("100000"), Decimal("5000"), 60, 0)
        # Month 37 is the switch point (remaining = 24)
        # After switch, monthly depreciation should be more uniform
        last_24 = schedule[-24:]
        # In the straight-line phase, depreciation should be relatively uniform
        # (decreasing slightly as book_value decreases each month)
        deps_last_24 = [s["depreciation"] for s in last_24]
        # The variation in the last 24 months should be much less than first 36
        first_36_deps = [s["depreciation"] for s in schedule[:36]]
        first_36_range = max(first_36_deps) - min(first_36_deps)
        last_24_range = max(deps_last_24) - min(deps_last_24)
        assert last_24_range < first_36_range

    def test_accumulated_never_exceeds_depreciable(self):
        """累计折旧不超过 depreciable = original_cost - residual"""
        schedule = _calc_double_declining(Decimal("200000"), Decimal("10000"), 120, 0)
        depreciable = Decimal("190000")
        for entry in schedule:
            assert entry["accumulated"] <= depreciable

    def test_short_useful_life_24_months(self):
        """使用年限=24月 → 全程走直线法分支"""
        schedule = _calc_double_declining(Decimal("50000"), Decimal("2500"), 24, 0)
        assert len(schedule) == 24
        # All months are in the "remaining <= 24" branch
        assert schedule[-1]["accumulated"] <= Decimal("47500")

    def test_very_short_useful_life_12_months(self):
        """使用年限=12月 → 全程走直线法分支"""
        schedule = _calc_double_declining(Decimal("12000"), Decimal("1200"), 12, 0)
        assert len(schedule) == 12
        assert schedule[-1]["accumulated"] <= Decimal("10800")
        assert schedule[-1]["accumulated"] > Decimal("0")

    def test_continuation_skips_already_depreciated(self):
        """续提场景：已计提 30 月，输出从第 31 月开始"""
        schedule = _calc_double_declining(Decimal("100000"), Decimal("5000"), 60, 30)
        assert schedule[0]["month"] == 31
        assert len(schedule) == 30
        # Accumulated at end should still not exceed depreciable
        assert schedule[-1]["accumulated"] <= Decimal("95000")

    def test_zero_depreciable(self):
        """depreciable=0 → 空 schedule"""
        schedule = _calc_double_declining(Decimal("10000"), Decimal("10000"), 60, 0)
        assert schedule == []


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SUM OF YEARS — 年数总和法
# ═══════════════════════════════════════════════════════════════════════════════


class TestSumOfYears:
    """年数总和法 boundary cases"""

    def test_accelerated_depreciation_front_heavy(self):
        """加速折旧：第 1 年月折旧 > 最后 1 年月折旧"""
        schedule = _calc_sum_of_years(Decimal("100000"), Decimal("5000"), 60, 0)
        assert len(schedule) == 60
        first_month_dep = schedule[0]["depreciation"]
        last_month_dep = schedule[-1]["depreciation"]
        assert first_month_dep > last_month_dep

    def test_year_by_year_decreasing(self):
        """逐年递减：每年折旧总额严格递减"""
        schedule = _calc_sum_of_years(Decimal("100000"), Decimal("5000"), 60, 0)
        year_totals = []
        for y in range(5):
            year_dep = sum(s["depreciation"] for s in schedule[y * 12:(y + 1) * 12])
            year_totals.append(year_dep)
        # Each year should be less than the previous
        for i in range(1, len(year_totals)):
            assert year_totals[i] < year_totals[i - 1]

    def test_continuation_scenario(self):
        """续提场景：已计提 24 月"""
        schedule = _calc_sum_of_years(Decimal("100000"), Decimal("5000"), 60, 24)
        assert len(schedule) == 36
        assert schedule[0]["month"] == 25

    def test_accumulated_never_exceeds_depreciable(self):
        """累计折旧不超过 depreciable"""
        schedule = _calc_sum_of_years(Decimal("500000"), Decimal("25000"), 120, 0)
        depreciable = Decimal("475000")
        for entry in schedule:
            assert entry["accumulated"] <= depreciable

    def test_less_than_12_months(self):
        """不足 12 月（useful_life_years 向下取整为 1）"""
        schedule = _calc_sum_of_years(Decimal("10000"), Decimal("1000"), 6, 0)
        assert len(schedule) == 6
        # useful_life_years = 6//12 = 0 → clamped to 1
        # sum_of_years = 1*(1+1)/2 = 1
        # year_dep = 9000 * 1/1 = 9000; monthly = 9000/12 = 750
        assert schedule[0]["depreciation"] == Decimal("750.00")

    def test_zero_depreciable(self):
        """depreciable=0 → 空 schedule"""
        schedule = _calc_sum_of_years(Decimal("10000"), Decimal("10000"), 60, 0)
        assert schedule == []

    def test_total_equals_depreciable(self):
        """总折旧应等于 depreciable（允许四舍五入误差 ≤ 0.01）"""
        schedule = _calc_sum_of_years(Decimal("100000"), Decimal("5000"), 60, 0)
        depreciable = Decimal("95000")
        total = schedule[-1]["accumulated"]
        assert abs(total - depreciable) <= Decimal("0.01")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. UNITS OF PRODUCTION — 工作量法
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnitsOfProduction:
    """工作量法 boundary cases"""

    def test_normal_calculation(self):
        """正常计算：unit_dep × current_period_units"""
        schedule = _calc_units_of_production(
            Decimal("200000"), Decimal("10000"),
            Decimal("50000"), Decimal("2000"), 0
        )
        assert len(schedule) == 1
        # unit_dep = 190000 / 50000 = 3.8; period_dep = 3.8 * 2000 = 7600
        assert schedule[0]["depreciation"] == Decimal("7600.00")
        assert schedule[0]["accumulated"] == Decimal("7600.00")
        assert schedule[0]["month"] == 1

    def test_current_exceeds_total_cap(self):
        """当期工作量 > 总工作量 → cap at depreciable"""
        schedule = _calc_units_of_production(
            Decimal("100000"), Decimal("5000"),
            Decimal("100"), Decimal("500"), 0  # 500 > 100
        )
        assert len(schedule) == 1
        # unit_dep = 95000/100 = 950; period_dep = 950*500 = 475000 > 95000 → cap
        assert schedule[0]["depreciation"] == Decimal("95000")

    def test_zero_current_period_units(self):
        """当期工作量=0 → 折旧=0"""
        schedule = _calc_units_of_production(
            Decimal("100000"), Decimal("5000"),
            Decimal("10000"), Decimal("0"), 0
        )
        assert len(schedule) == 1
        assert schedule[0]["depreciation"] == Decimal("0.00")

    def test_with_already_depreciated_months(self):
        """续提场景：month 编号正确"""
        schedule = _calc_units_of_production(
            Decimal("100000"), Decimal("5000"),
            Decimal("10000"), Decimal("1000"), 12
        )
        assert schedule[0]["month"] == 13

    def test_very_large_total_units(self):
        """极大总工作量 → 极小单位折旧"""
        schedule = _calc_units_of_production(
            Decimal("100000"), Decimal("5000"),
            Decimal("1000000000"), Decimal("100"), 0
        )
        assert len(schedule) == 1
        # unit_dep = 95000 / 1e9 = 0.000095; period_dep = 0.000095 * 100 = 0.0095 → 0.01
        assert schedule[0]["depreciation"] == Decimal("0.01")

    def test_depreciable_zero(self):
        """depreciable=0 → 空 schedule"""
        schedule = _calc_units_of_production(
            Decimal("10000"), Decimal("10000"),
            Decimal("5000"), Decimal("100"), 0
        )
        assert schedule == []


# ═══════════════════════════════════════════════════════════════════════════════
# 5. VALIDATION — _validate_request 边界校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidation:
    """输入参数校验 boundary cases"""

    def test_original_cost_exceeds_1e15_returns_400(self):
        """原值 > 1e15 → 400"""
        payload = DepreciationCalcRequest(
            method="straight_line",
            original_cost=Decimal("2e15"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=1,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400
        assert "1e15" in exc_info.value.detail

    def test_useful_life_months_exceeds_600_returns_400(self):
        """使用年限 > 600 → 400"""
        payload = DepreciationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0.05"),
            useful_life_months=601,
            start_month=1,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400
        assert "600" in exc_info.value.detail

    def test_already_depreciated_exceeds_useful_life_returns_400(self):
        """已计提月数 > 使用年限 → 400"""
        payload = DepreciationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=1,
            already_depreciated_months=61,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400
        assert "已计提月数" in exc_info.value.detail

    def test_negative_original_cost_returns_400(self):
        """原值为负 → 400"""
        payload = DepreciationCalcRequest(
            method="straight_line",
            original_cost=Decimal("-100"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=1,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400
        assert "负数" in exc_info.value.detail

    def test_units_of_production_total_units_zero_returns_400(self):
        """工作量法 total_units=0 → 400"""
        payload = DepreciationCalcRequest(
            method="units_of_production",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=1,
            total_units=Decimal("0"),
            current_period_units=Decimal("100"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400
        assert "零" in exc_info.value.detail

    def test_units_of_production_missing_total_units_returns_422(self):
        """工作量法缺少 total_units → 422"""
        payload = DepreciationCalcRequest(
            method="units_of_production",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=1,
            total_units=None,
            current_period_units=Decimal("100"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 422

    def test_units_of_production_missing_current_period_units_returns_422(self):
        """工作量法缺少 current_period_units → 422"""
        payload = DepreciationCalcRequest(
            method="units_of_production",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=1,
            total_units=Decimal("1000"),
            current_period_units=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 422

    def test_units_of_production_negative_total_units_returns_400(self):
        """工作量法 total_units < 0 → 400"""
        payload = DepreciationCalcRequest(
            method="units_of_production",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=1,
            total_units=Decimal("-100"),
            current_period_units=Decimal("50"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_request(payload)
        assert exc_info.value.status_code == 400

    def test_valid_straight_line_passes(self):
        """合法直线法参数不抛异常"""
        payload = DepreciationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=6,
        )
        # Should not raise
        _validate_request(payload)

    def test_boundary_original_cost_exactly_1e15(self):
        """原值恰好 = 1e15 → 不报错（边界值）"""
        payload = DepreciationCalcRequest(
            method="straight_line",
            original_cost=Decimal("1e15"),
            residual_rate=Decimal("0.05"),
            useful_life_months=60,
            start_month=1,
        )
        # Should not raise
        _validate_request(payload)

    def test_boundary_useful_life_exactly_600(self):
        """使用年限恰好 = 600 → 不报错（边界值）"""
        payload = DepreciationCalcRequest(
            method="straight_line",
            original_cost=Decimal("100000"),
            residual_rate=Decimal("0.05"),
            useful_life_months=600,
            start_month=1,
        )
        # Should not raise
        _validate_request(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. WRITE-BACK — apply_to_sheet 写回
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """Write-back helper tests"""

    def test_writeback_helper_exists_and_callable(self):
        """_maybe_apply_depreciation_to_workpaper 写回辅助函数必须存在且可调用"""
        assert callable(_maybe_apply_depreciation_to_workpaper)

    def test_writeback_helper_is_async(self):
        """写回函数必须是 async（需要 DB 操作）"""
        assert inspect.iscoroutinefunction(_maybe_apply_depreciation_to_workpaper)

    def test_writeback_helper_signature(self):
        """写回函数签名包含必要参数"""
        sig = inspect.signature(_maybe_apply_depreciation_to_workpaper)
        param_names = list(sig.parameters.keys())
        assert "db" in param_names
        assert "wp_id" in param_names
        assert "payload" in param_names
        assert "schedule" in param_names
        assert "total_depreciation" in param_names
        assert "remaining_book_value" in param_names


# ═══════════════════════════════════════════════════════════════════════════════
# 7. RBAC — require_project_access("edit") 强制校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC enforcement tests"""

    def test_route_uses_require_project_access_edit(self):
        """折旧引擎路由必须用 require_project_access('edit')，不能裸用 get_current_user"""
        import app.routers.wp_h_depreciation as mod
        src = inspect.getsource(mod)
        assert 'require_project_access("edit")' in src, \
            "wp_h_depreciation 必须用 require_project_access('edit')"

    def test_endpoint_function_has_user_dependency(self):
        """endpoint 函数签名中包含 _user 参数（RBAC 注入）"""
        from app.routers.wp_h_depreciation import h1_depreciation_calc
        sig = inspect.signature(h1_depreciation_calc)
        param_names = list(sig.parameters.keys())
        assert "_user" in param_names, "endpoint 必须有 _user 参数用于 RBAC"

    def test_router_prefix_contains_project_id(self):
        """路由前缀包含 {project_id}（RBAC 需要 project 上下文）"""
        from app.routers.wp_h_depreciation import router
        assert "{project_id}" in router.prefix


# ═══════════════════════════════════════════════════════════════════════════════
# 8. INTEGRATION — 跨方法一致性验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossMethodConsistency:
    """跨方法一致性验证"""

    def test_all_methods_respect_depreciable_cap(self):
        """所有方法的累计折旧都不超过 depreciable"""
        original = Decimal("100000")
        residual = Decimal("5000")
        depreciable = original - residual

        sl = _calc_straight_line(original, residual, 60, 0)
        dd = _calc_double_declining(original, residual, 60, 0)
        sy = _calc_sum_of_years(original, residual, 60, 0)

        for schedule in [sl, dd, sy]:
            if schedule:
                assert schedule[-1]["accumulated"] <= depreciable

    def test_straight_line_total_equals_depreciable(self):
        """直线法总折旧精确等于 depreciable"""
        original = Decimal("120000")
        residual = Decimal("12000")
        depreciable = original - residual
        schedule = _calc_straight_line(original, residual, 60, 0)
        assert schedule[-1]["accumulated"] == depreciable

    def test_double_declining_total_close_to_depreciable(self):
        """双倍余额递减法总折旧接近 depreciable（允许 ≤ 1.00 误差）"""
        original = Decimal("100000")
        residual = Decimal("5000")
        depreciable = original - residual
        schedule = _calc_double_declining(original, residual, 60, 0)
        assert abs(schedule[-1]["accumulated"] - depreciable) <= Decimal("1.00")

    def test_month_numbering_monotonic(self):
        """所有方法的 month 编号严格递增"""
        schedules = [
            _calc_straight_line(Decimal("100000"), Decimal("5000"), 60, 0),
            _calc_double_declining(Decimal("100000"), Decimal("5000"), 60, 0),
            _calc_sum_of_years(Decimal("100000"), Decimal("5000"), 60, 0),
        ]
        for schedule in schedules:
            months = [s["month"] for s in schedule]
            for i in range(1, len(months)):
                assert months[i] > months[i - 1]

    def test_accumulated_monotonically_increasing(self):
        """所有方法的 accumulated 单调递增"""
        schedules = [
            _calc_straight_line(Decimal("100000"), Decimal("5000"), 60, 0),
            _calc_double_declining(Decimal("100000"), Decimal("5000"), 60, 0),
            _calc_sum_of_years(Decimal("100000"), Decimal("5000"), 60, 0),
        ]
        for schedule in schedules:
            for i in range(1, len(schedule)):
                assert schedule[i]["accumulated"] >= schedule[i - 1]["accumulated"]

    def test_depreciation_non_negative(self):
        """所有方法的每月折旧 ≥ 0"""
        schedules = [
            _calc_straight_line(Decimal("100000"), Decimal("5000"), 60, 0),
            _calc_double_declining(Decimal("100000"), Decimal("5000"), 60, 0),
            _calc_sum_of_years(Decimal("100000"), Decimal("5000"), 60, 0),
            _calc_units_of_production(
                Decimal("100000"), Decimal("5000"),
                Decimal("10000"), Decimal("500"), 0
            ),
        ]
        for schedule in schedules:
            for entry in schedule:
                assert entry["depreciation"] >= Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. TERM PARAMETER — 跨 spec 复用术语统一（Sprint 4 Task 4.8）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTermParameter:
    """验证 H-F11 引擎 term 参数支持（depreciation/amortization 切换）

    跨 spec 复用约定：
    - H-F11 默认 term='depreciation'（向后兼容）
    - I-F2 调用时传 term='amortization'
    - 切换字段名让 schedule 输出与上下文术语一致
    """

    def test_default_term_is_depreciation(self):
        """默认 term='depreciation' 字段名（向后兼容 H spec 现有断言）"""
        sched = _calc_straight_line(Decimal("12000"), Decimal("0"), 12, 0)
        assert all("depreciation" in s for s in sched)
        assert all("amortization" not in s for s in sched)

    def test_term_amortization_switches_field_name(self):
        """term='amortization' → schedule 含 'amortization' 字段而非 'depreciation'"""
        sched = _calc_straight_line(
            Decimal("12000"), Decimal("0"), 12, 0, term="amortization"
        )
        assert all("amortization" in s for s in sched)
        assert all("depreciation" not in s for s in sched)

    def test_term_amortization_preserves_amount(self):
        """term 切换不影响金额计算"""
        sched_d = _calc_straight_line(Decimal("12000"), Decimal("0"), 12, 0)
        sched_a = _calc_straight_line(
            Decimal("12000"), Decimal("0"), 12, 0, term="amortization"
        )
        assert len(sched_d) == len(sched_a)
        for d, a in zip(sched_d, sched_a):
            assert d["depreciation"] == a["amortization"]
            assert d["accumulated"] == a["accumulated"]
            assert d["month"] == a["month"]

    def test_units_of_production_term_amortization(self):
        """工作量法同样支持 term 切换"""
        sched = _calc_units_of_production(
            Decimal("100000"), Decimal("0"),
            Decimal("10000"), Decimal("500"), 0,
            term="amortization",
        )
        assert len(sched) == 1
        assert "amortization" in sched[0]
        assert "depreciation" not in sched[0]

    def test_double_declining_term_amortization(self):
        """双倍余额递减法同样支持 term 切换"""
        sched = _calc_double_declining(
            Decimal("100000"), Decimal("5000"), 60, 0, term="amortization"
        )
        assert all("amortization" in s for s in sched)
        assert all("depreciation" not in s for s in sched)

    def test_sum_of_years_term_amortization(self):
        """年数总和法同样支持 term 切换"""
        sched = _calc_sum_of_years(
            Decimal("100000"), Decimal("5000"), 60, 0, term="amortization"
        )
        assert all("amortization" in s for s in sched)
        assert all("depreciation" not in s for s in sched)
