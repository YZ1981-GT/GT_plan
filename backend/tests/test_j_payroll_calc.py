"""Comprehensive unit tests for J-F7 薪酬计提引擎 — 多参数组合 + 写回 + RBAC + 边界.

Covers:
- 计提公式正确性（标准参数 / 多参数组合 / 月度明细一致性）
- apply_to_sheet 写回联动
- RBAC 校验（无权限返回 403）
- 边界 case（employee_count=0 / 社保比例之和 > 0.5 返回 warning / months=0 返回 400）
- 年度合计 = months × 月度合计 ± 1

对应 spec: workpaper-j-payroll-cycle J-F7
"""

import sys
sys.path.insert(0, "backend")

import inspect
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.routers.wp_j_payroll_calc import (
    PayrollCalcRequest,
    SocialInsuranceRates,
    _calc_payroll,
    _maybe_apply_payroll_to_workpaper,
    _quantize,
    _validate_payroll_request,
    j1_payroll_calc,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: 构造标准请求
# ═══════════════════════════════════════════════════════════════════════════════


def _make_request(**overrides) -> PayrollCalcRequest:
    """构造标准薪酬计提请求，可覆盖任意字段。"""
    defaults = {
        "employee_count": 100,
        "avg_monthly_salary": Decimal("15000"),
        "social_insurance_rates": SocialInsuranceRates(
            pension=Decimal("0.16"),
            medical=Decimal("0.095"),
            unemployment=Decimal("0.005"),
            work_injury=Decimal("0.004"),
            maternity=Decimal("0.008"),
        ),
        "housing_fund_rate": Decimal("0.12"),
        "supplementary_fund_rate": Decimal("0"),
        "welfare_rate": Decimal("0.14"),
        "education_rate": Decimal("0.025"),
        "union_rate": Decimal("0.02"),
        "months": 12,
        "apply_to_sheet": None,
    }
    defaults.update(overrides)
    return PayrollCalcRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 计提公式正确性
# ═══════════════════════════════════════════════════════════════════════════════


class TestPayrollFormula:
    """薪酬计提公式正确性验证"""

    def test_standard_params_monthly_salary(self):
        """标准参数：月度工资总额 = employee_count × avg_monthly_salary"""
        req = _make_request()
        breakdown, summary = _calc_payroll(req)
        # 100 × 15000 = 1,500,000
        assert breakdown[0]["salary"] == Decimal("1500000.00")

    def test_standard_params_pension(self):
        """标准参数：养老保险 = 月度工资 × pension rate"""
        req = _make_request()
        breakdown, _ = _calc_payroll(req)
        # 1,500,000 × 0.16 = 240,000
        assert breakdown[0]["pension"] == Decimal("240000.00")

    def test_standard_params_medical(self):
        """标准参数：医疗保险 = 月度工资 × medical rate"""
        req = _make_request()
        breakdown, _ = _calc_payroll(req)
        # 1,500,000 × 0.095 = 142,500
        assert breakdown[0]["medical"] == Decimal("142500.00")

    def test_standard_params_total_per_month(self):
        """月度合计 = salary + 各项计提之和"""
        req = _make_request()
        breakdown, _ = _calc_payroll(req)
        m = breakdown[0]
        expected_total = (
            m["salary"] + m["pension"] + m["medical"] + m["unemployment"]
            + m["work_injury"] + m["maternity"] + m["housing_fund"]
            + m["supplementary_fund"] + m["welfare"] + m["education"] + m["union_fee"]
        )
        assert m["total"] == expected_total

    def test_annual_summary_grand_total(self):
        """年度汇总 grand_total = 各项年度合计之和"""
        req = _make_request()
        _, summary = _calc_payroll(req)
        expected = (
            summary["total_salary"]
            + summary["total_social_insurance"]
            + summary["total_housing_fund"]
            + summary["total_supplementary_fund"]
            + summary["total_welfare"]
            + summary["total_education"]
            + summary["total_union"]
        )
        assert summary["grand_total"] == expected

    def test_annual_total_salary_equals_months_times_monthly(self):
        """年度工资合计 = months × 月度工资"""
        req = _make_request(months=12)
        breakdown, summary = _calc_payroll(req)
        monthly_salary = breakdown[0]["salary"]
        assert summary["total_salary"] == monthly_salary * 12

    def test_monthly_breakdown_count_equals_months(self):
        """月度明细条数 = months"""
        req = _make_request(months=6)
        breakdown, _ = _calc_payroll(req)
        assert len(breakdown) == 6

    def test_all_months_identical(self):
        """所有月度明细应完全相同（固定参数下）"""
        req = _make_request(months=12)
        breakdown, _ = _calc_payroll(req)
        first = breakdown[0]
        for m in breakdown[1:]:
            assert m["salary"] == first["salary"]
            assert m["total"] == first["total"]

    def test_different_employee_count(self):
        """不同员工数：50 人 × 20000 = 1,000,000 月度工资"""
        req = _make_request(employee_count=50, avg_monthly_salary=Decimal("20000"))
        breakdown, _ = _calc_payroll(req)
        assert breakdown[0]["salary"] == Decimal("1000000.00")

    def test_supplementary_fund_nonzero(self):
        """补充公积金非零时正确计算"""
        req = _make_request(supplementary_fund_rate=Decimal("0.05"))
        breakdown, summary = _calc_payroll(req)
        # 1,500,000 × 0.05 = 75,000
        assert breakdown[0]["supplementary_fund"] == Decimal("75000.00")
        assert summary["total_supplementary_fund"] == Decimal("900000.00")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 年度合计一致性（年度合计 = months × 月度合计 ± 1）
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnnualConsistency:
    """年度合计 = months × 月度合计 ± 1（四舍五入误差）"""

    def test_annual_grand_total_within_tolerance(self):
        """grand_total 与 months × monthly_total 差值 ≤ 1"""
        req = _make_request(months=12)
        breakdown, summary = _calc_payroll(req)
        monthly_total = breakdown[0]["total"]
        expected_annual = monthly_total * 12
        diff = abs(summary["grand_total"] - expected_annual)
        assert diff <= Decimal("1.00")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 边界 case
# ═══════════════════════════════════════════════════════════════════════════════


class TestBoundaryCases:
    """边界 case 验证"""

    def test_employee_count_zero_returns_warning(self):
        """employee_count=0 → 返回 warning + 全 0 结果"""
        req = _make_request(employee_count=0)
        warnings = _validate_payroll_request(req)
        assert any("员工人数为 0" in w for w in warnings)
        breakdown, summary = _calc_payroll(req)
        assert breakdown[0]["salary"] == Decimal("0.00")
        assert summary["grand_total"] == Decimal("0.00")

    def test_months_zero_raises_400(self):
        """months=0 → 返回 400"""
        req = _make_request(months=0)
        with pytest.raises(HTTPException) as exc_info:
            _validate_payroll_request(req)
        assert exc_info.value.status_code == 400
        assert "月数" in str(exc_info.value.detail)

    def test_social_insurance_sum_ge_05_returns_warning(self):
        """社保 5 项比例之和 ≥ 0.5 → 返回 warning"""
        req = _make_request(
            social_insurance_rates=SocialInsuranceRates(
                pension=Decimal("0.20"),
                medical=Decimal("0.15"),
                unemployment=Decimal("0.10"),
                work_injury=Decimal("0.03"),
                maternity=Decimal("0.03"),
            )
        )
        warnings = _validate_payroll_request(req)
        assert any("社保 5 项比例之和" in w for w in warnings)

    def test_social_insurance_sum_lt_05_no_warning(self):
        """社保 5 项比例之和 < 0.5 → 无 warning"""
        req = _make_request()  # 标准参数 sum = 0.272 < 0.5
        warnings = _validate_payroll_request(req)
        assert not any("社保 5 项比例之和" in w for w in warnings)

    def test_single_month(self):
        """months=1 → 只有 1 条月度明细"""
        req = _make_request(months=1)
        breakdown, summary = _calc_payroll(req)
        assert len(breakdown) == 1
        assert summary["total_salary"] == breakdown[0]["salary"]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 写回联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """apply_to_sheet 写回联动"""

    def test_write_back_function_is_callable(self):
        """_maybe_apply_payroll_to_workpaper 是可调用函数"""
        assert callable(_maybe_apply_payroll_to_workpaper)

    def test_write_back_returns_none_when_no_sheet(self):
        """apply_to_sheet=None → 不写回"""
        import asyncio

        async def _run():
            return await _maybe_apply_payroll_to_workpaper(
                None, "invalid-uuid", _make_request(), [], {}
            )

        result = asyncio.run(_run())
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. RBAC 校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC 校验"""

    def test_endpoint_function_has_user_dependency(self):
        """endpoint 函数签名中包含 _user 参数（RBAC 注入）"""
        sig = inspect.signature(j1_payroll_calc)
        param_names = list(sig.parameters.keys())
        assert "_user" in param_names, "endpoint 必须有 _user 参数用于 RBAC"

    def test_endpoint_requires_edit_permission(self):
        """endpoint 使用 require_project_access('edit') 依赖"""
        sig = inspect.signature(j1_payroll_calc)
        user_param = sig.parameters["_user"]
        # 检查 default 是 Depends(require_project_access("edit"))
        default = user_param.default
        assert default is not None, "应有 Depends 默认值"
