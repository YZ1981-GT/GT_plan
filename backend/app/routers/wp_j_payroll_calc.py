"""J 职工薪酬循环 — J-F7 薪酬计提引擎 API

POST /api/projects/{project_id}/workpapers/{wp_id}/j1/payroll-calc

纯算法 endpoint：根据员工数/月均工资/社保比例/公积金/福利费/教育经费/工会经费
计算月度明细 + 年度汇总。

写回模式：parsed_data.payroll_calcs[sheet] = {method, applied_at, data}
与 H-F11 折旧引擎 depreciation_calcs 对称。

对应 spec：workpaper-j-payroll-cycle J-F7 / ADR-J4
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/j1",
    tags=["wp-j-payroll"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class SocialInsuranceRates(BaseModel):
    """社保 5 项比例"""

    pension: Decimal = Field(..., ge=0, le=1, description="养老保险比例")
    medical: Decimal = Field(..., ge=0, le=1, description="医疗保险比例")
    unemployment: Decimal = Field(..., ge=0, le=1, description="失业保险比例")
    work_injury: Decimal = Field(..., ge=0, le=1, description="工伤保险比例")
    maternity: Decimal = Field(..., ge=0, le=1, description="生育保险比例")


class PayrollCalcRequest(BaseModel):
    """薪酬计提计算请求"""

    employee_count: int = Field(..., ge=0, description="员工人数")
    avg_monthly_salary: Decimal = Field(..., ge=0, description="月均工资")
    social_insurance_rates: SocialInsuranceRates = Field(..., description="社保 5 项比例")
    housing_fund_rate: Decimal = Field(Decimal("0.12"), ge=0, le=1, description="住房公积金比例")
    supplementary_fund_rate: Decimal = Field(Decimal("0"), ge=0, le=1, description="补充公积金比例")
    welfare_rate: Decimal = Field(Decimal("0.14"), ge=0, le=1, description="福利费比例")
    education_rate: Decimal = Field(Decimal("0.025"), ge=0, le=1, description="教育经费比例")
    union_rate: Decimal = Field(Decimal("0.02"), ge=0, le=1, description="工会经费比例")
    months: int = Field(12, ge=0, le=12, description="计提月数（0~12）")
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.payroll_calcs[sheet]",
    )


class MonthlyBreakdown(BaseModel):
    """月度明细"""

    month: int
    salary: Decimal
    pension: Decimal
    medical: Decimal
    unemployment: Decimal
    work_injury: Decimal
    maternity: Decimal
    housing_fund: Decimal
    supplementary_fund: Decimal
    welfare: Decimal
    education: Decimal
    union_fee: Decimal
    total: Decimal


class AnnualSummary(BaseModel):
    """年度汇总"""

    total_salary: Decimal
    total_social_insurance: Decimal
    total_housing_fund: Decimal
    total_supplementary_fund: Decimal
    total_welfare: Decimal
    total_education: Decimal
    total_union: Decimal
    grand_total: Decimal


class PayrollCalcResponse(BaseModel):
    """薪酬计提计算响应"""

    monthly_breakdown: list[MonthlyBreakdown]
    annual_summary: AnnualSummary
    warnings: list[str] = []
    applied_to_sheet: str | None = None
    applied_at: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _quantize(value: Decimal) -> Decimal:
    """保留 2 位小数（四舍五入）"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _validate_payroll_request(payload: PayrollCalcRequest) -> list[str]:
    """校验输入参数，返回 warnings 列表。严重错误抛 HTTPException。"""
    warnings: list[str] = []

    if payload.months == 0:
        raise HTTPException(400, "计提月数不能为 0")

    # 社保 5 项比例之和应 < 0.5
    sir = payload.social_insurance_rates
    social_sum = sir.pension + sir.medical + sir.unemployment + sir.work_injury + sir.maternity
    if social_sum >= Decimal("0.5"):
        warnings.append(
            f"社保 5 项比例之和 = {social_sum}（≥ 0.5），请确认是否合理"
        )

    if payload.employee_count == 0:
        warnings.append("员工人数为 0，计算结果将全部为 0")

    return warnings


def _calc_payroll(payload: PayrollCalcRequest) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """计算月度明细 + 年度汇总。返回 (monthly_breakdown_list, annual_summary_dict)。"""
    sir = payload.social_insurance_rates
    monthly_salary = _quantize(
        Decimal(str(payload.employee_count)) * payload.avg_monthly_salary
    )

    monthly_breakdown: list[dict[str, Any]] = []

    for m in range(1, payload.months + 1):
        pension = _quantize(monthly_salary * sir.pension)
        medical = _quantize(monthly_salary * sir.medical)
        unemployment = _quantize(monthly_salary * sir.unemployment)
        work_injury = _quantize(monthly_salary * sir.work_injury)
        maternity = _quantize(monthly_salary * sir.maternity)
        housing_fund = _quantize(monthly_salary * payload.housing_fund_rate)
        supplementary_fund = _quantize(monthly_salary * payload.supplementary_fund_rate)
        welfare = _quantize(monthly_salary * payload.welfare_rate)
        education = _quantize(monthly_salary * payload.education_rate)
        union_fee = _quantize(monthly_salary * payload.union_rate)

        total = (
            monthly_salary + pension + medical + unemployment + work_injury
            + maternity + housing_fund + supplementary_fund + welfare + education + union_fee
        )

        monthly_breakdown.append({
            "month": m,
            "salary": monthly_salary,
            "pension": pension,
            "medical": medical,
            "unemployment": unemployment,
            "work_injury": work_injury,
            "maternity": maternity,
            "housing_fund": housing_fund,
            "supplementary_fund": supplementary_fund,
            "welfare": welfare,
            "education": education,
            "union_fee": union_fee,
            "total": total,
        })

    # 年度汇总
    months = Decimal(str(payload.months))
    annual_summary = {
        "total_salary": _quantize(monthly_salary * months),
        "total_social_insurance": _quantize(
            (
                _quantize(monthly_salary * sir.pension)
                + _quantize(monthly_salary * sir.medical)
                + _quantize(monthly_salary * sir.unemployment)
                + _quantize(monthly_salary * sir.work_injury)
                + _quantize(monthly_salary * sir.maternity)
            ) * months
        ),
        "total_housing_fund": _quantize(
            _quantize(monthly_salary * payload.housing_fund_rate) * months
        ),
        "total_supplementary_fund": _quantize(
            _quantize(monthly_salary * payload.supplementary_fund_rate) * months
        ),
        "total_welfare": _quantize(_quantize(monthly_salary * payload.welfare_rate) * months),
        "total_education": _quantize(_quantize(monthly_salary * payload.education_rate) * months),
        "total_union": _quantize(_quantize(monthly_salary * payload.union_rate) * months),
        "grand_total": Decimal("0"),
    }
    annual_summary["grand_total"] = (
        annual_summary["total_salary"]
        + annual_summary["total_social_insurance"]
        + annual_summary["total_housing_fund"]
        + annual_summary["total_supplementary_fund"]
        + annual_summary["total_welfare"]
        + annual_summary["total_education"]
        + annual_summary["total_union"]
    )

    return monthly_breakdown, annual_summary


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/payroll-calc", response_model=PayrollCalcResponse)
async def j1_payroll_calc(
    project_id: str,
    wp_id: str,
    payload: PayrollCalcRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> PayrollCalcResponse:
    """J-F7 薪酬计提引擎：计算月度明细 + 年度汇总。

    业务约束：
    - 年度合计 = months × 月度合计 ± 1（四舍五入误差）
    - 社保 5 项比例之和应 < 0.5（超出返回 warning）
    - employee_count=0 → 返回全 0 + warning
    - months=0 → 返回 400
    """
    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    warnings = _validate_payroll_request(payload)

    monthly_breakdown, annual_summary = _calc_payroll(payload)

    # 写回
    applied_to_sheet = None
    applied_at = None
    if payload.apply_to_sheet:
        applied_to_sheet = await _maybe_apply_payroll_to_workpaper(
            db, wp_id, payload, monthly_breakdown, annual_summary
        )
        if applied_to_sheet:
            applied_at = datetime.now(timezone.utc).isoformat()

    return PayrollCalcResponse(
        monthly_breakdown=[MonthlyBreakdown(**m) for m in monthly_breakdown],
        annual_summary=AnnualSummary(**annual_summary),
        warnings=warnings,
        applied_to_sheet=applied_to_sheet,
        applied_at=applied_at,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_payroll_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: PayrollCalcRequest,
    monthly_breakdown: list[dict[str, Any]],
    annual_summary: dict[str, Any],
) -> str | None:
    """若 apply_to_sheet 给出则把薪酬计提结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.payroll_calcs[sheet] = {
        "method": "payroll_accrual",
        "applied_at": ISO8601,
        "data": {
          "employee_count": ...,
          "avg_monthly_salary": "...",
          "months": ...,
          "monthly_breakdown": [...],
          "annual_summary": {...}
        }
      }
    """
    if not payload.apply_to_sheet:
        return None

    from app.models.workpaper_models import WorkingPaper

    try:
        wp_uuid = UUID(wp_id)
    except Exception:
        return None

    res = await db.execute(sa.select(WorkingPaper).where(WorkingPaper.id == wp_uuid))
    wp = res.scalar_one_or_none()
    if wp is None:
        return None

    pd = wp.parsed_data or {}
    if not isinstance(pd, dict):
        pd = {}
    pd.setdefault("payroll_calcs", {})
    pd["payroll_calcs"][payload.apply_to_sheet] = {
        "method": "payroll_accrual",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "employee_count": payload.employee_count,
            "avg_monthly_salary": str(payload.avg_monthly_salary),
            "months": payload.months,
            "monthly_breakdown": [
                {k: str(v) if isinstance(v, Decimal) else v for k, v in m.items()}
                for m in monthly_breakdown
            ],
            "annual_summary": {
                k: str(v) if isinstance(v, Decimal) else v
                for k, v in annual_summary.items()
            },
        },
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
