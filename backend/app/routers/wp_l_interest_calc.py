"""L 筹资循环 — L-F7 利息自动测算引擎 API

POST /api/projects/{project_id}/workpapers/{wp_id}/l/interest-calc

纯算法 endpoint：根据本金/年利率/起息日/到期日/计息基准/复利频率
计算利息总额。支持 3 种计息基准 × 3 种复利频率 = 9 种组合。

写回模式：parsed_data.interest_calcs[sheet] = {method, applied_at, data}
与 J-F7 薪酬计提引擎 payroll_calcs 对称。

对应 spec：workpaper-l-debt-cycle L-F7 / ADR-L4
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/l",
    tags=["wp-l-interest"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class InterestCalcRequest(BaseModel):
    """利息测算请求"""

    wp_code: Literal["L1", "L3"] = Field(..., description="区分短期/长期借款写回目标")
    principal: Decimal = Field(..., ge=0, description="本金")
    annual_rate: Decimal = Field(..., ge=0, description="年利率（如 0.045 = 4.5%）")
    start_date: date = Field(..., description="起息日")
    end_date: date = Field(..., description="到期日")
    day_count_basis: Literal["ACT/360", "ACT/365", "30/360"] = Field(
        ..., description="计息基准"
    )
    compound_frequency: Literal["simple", "monthly", "quarterly"] = Field(
        ..., description="复利频率"
    )
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.interest_calcs[sheet]",
    )


class InterestCalcResponse(BaseModel):
    """利息测算响应"""

    interest_amount: Decimal = Field(..., description="利息总额")
    daily_interest: Decimal = Field(..., description="日利息（简单利息时有意义）")
    period_days: int = Field(..., description="计息天数")
    day_count_divisor: int = Field(..., description="计息基准分母（360/365）")
    calculation_detail: str = Field(..., description="计算过程描述")
    compound_periods: int | None = Field(None, description="复利期数（复利时）")
    applied_to_sheet: str | None = None
    applied_at: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _quantize(value: Decimal) -> Decimal:
    """保留 2 位小数（四舍五入）"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _actual_days(start: date, end: date) -> int:
    """计算实际天数"""
    return (end - start).days


def _thirty_360_months(start: date, end: date) -> Decimal:
    """30/360 计息基准下的月数（含小数）

    公式：months = (end_year - start_year) × 12 + (end_month - start_month) + (end_day - start_day) / 30
    """
    year_diff = end.year - start.year
    month_diff = end.month - start.month
    day_diff = end.day - start.day
    return Decimal(str(year_diff * 12 + month_diff)) + Decimal(str(day_diff)) / Decimal("30")


def _calc_compound_periods(start: date, end: date, frequency: str) -> int:
    """计算复利期数

    monthly: 总月数
    quarterly: 总季度数
    """
    total_months = (end.year - start.year) * 12 + (end.month - start.month)
    # 如果 end.day > start.day，多算一个不完整月（向下取整）
    if frequency == "monthly":
        return max(total_months, 0)
    elif frequency == "quarterly":
        return max(total_months // 3, 0)
    return 0


def _validate_interest_request(payload: InterestCalcRequest) -> None:
    """校验输入参数，严重错误抛 HTTPException 400。"""
    if payload.start_date > payload.end_date:
        raise HTTPException(400, "起息日不能晚于到期日（start_date > end_date）")
    if payload.annual_rate > Decimal("1"):
        raise HTTPException(400, "年利率不能超过 100%（annual_rate > 1.0）")


def _calc_interest(payload: InterestCalcRequest) -> dict[str, Any]:
    """计算利息。返回包含所有响应字段的字典。

    3 种计息基准 × 3 种复利频率 = 9 种组合。
    """
    principal = payload.principal
    rate = payload.annual_rate
    start = payload.start_date
    end = payload.end_date
    basis = payload.day_count_basis
    freq = payload.compound_frequency

    # 特殊情况：本金=0 或利率=0 → 利息=0
    if principal == 0 or rate == 0:
        days = _actual_days(start, end)
        divisor = 360 if basis in ("ACT/360", "30/360") else 365
        return {
            "interest_amount": Decimal("0.00"),
            "daily_interest": Decimal("0.00"),
            "period_days": days,
            "day_count_divisor": divisor,
            "calculation_detail": f"本金或利率为 0，利息为 0（principal={principal}, rate={rate}）",
            "compound_periods": None,
        }

    # 计算实际天数
    days = _actual_days(start, end)

    # 根据计息基准和复利频率计算
    if freq == "simple":
        # 单利
        interest, detail, divisor = _calc_simple_interest(principal, rate, start, end, basis, days)
        return {
            "interest_amount": _quantize(interest),
            "daily_interest": _quantize(interest / Decimal(str(max(days, 1)))),
            "period_days": days,
            "day_count_divisor": divisor,
            "calculation_detail": detail,
            "compound_periods": None,
        }
    else:
        # 复利（monthly / quarterly）
        interest, detail, divisor, periods = _calc_compound_interest(
            principal, rate, start, end, basis, days, freq
        )
        return {
            "interest_amount": _quantize(interest),
            "daily_interest": _quantize(interest / Decimal(str(max(days, 1)))),
            "period_days": days,
            "day_count_divisor": divisor,
            "calculation_detail": detail,
            "compound_periods": periods,
        }


def _calc_simple_interest(
    principal: Decimal,
    rate: Decimal,
    start: date,
    end: date,
    basis: str,
    days: int,
) -> tuple[Decimal, str, int]:
    """单利计算。返回 (interest, detail, divisor)。"""
    if basis == "ACT/360":
        interest = principal * rate * Decimal(str(days)) / Decimal("360")
        detail = f"ACT/360 单利：{principal} × {rate} × {days} / 360 = {_quantize(interest)}"
        return interest, detail, 360
    elif basis == "ACT/365":
        interest = principal * rate * Decimal(str(days)) / Decimal("365")
        detail = f"ACT/365 单利：{principal} × {rate} × {days} / 365 = {_quantize(interest)}"
        return interest, detail, 365
    else:  # 30/360
        months = _thirty_360_months(start, end)
        interest = principal * rate * months / Decimal("12")
        detail = f"30/360 单利：{principal} × {rate} × {months} / 12 = {_quantize(interest)}"
        return interest, detail, 360


def _calc_compound_interest(
    principal: Decimal,
    rate: Decimal,
    start: date,
    end: date,
    basis: str,
    days: int,
    freq: str,
) -> tuple[Decimal, str, int, int]:
    """复利计算。返回 (interest, detail, divisor, periods)。"""
    periods = _calc_compound_periods(start, end, freq)

    if freq == "monthly":
        period_rate = rate / Decimal("12")
        freq_label = "月复利"
        freq_divisor = 12
    else:  # quarterly
        period_rate = rate / Decimal("4")
        freq_label = "季复利"
        freq_divisor = 4

    # 复利公式：principal × (1 + period_rate)^n - principal
    if periods == 0:
        interest = Decimal("0")
    else:
        # 使用 float 计算幂次，再转回 Decimal
        compound_factor = (1 + float(period_rate)) ** periods
        interest = principal * Decimal(str(compound_factor)) - principal

    # divisor 取决于 basis
    if basis == "ACT/360" or basis == "30/360":
        divisor = 360
    else:
        divisor = 365

    detail = (
        f"{basis} {freq_label}：{principal} × (1 + {rate}/{freq_divisor})^{periods} - {principal}"
        f" = {_quantize(interest)}"
    )

    return interest, detail, divisor, periods


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/interest-calc", response_model=InterestCalcResponse)
async def l_interest_calc(
    project_id: str,
    wp_id: str,
    payload: InterestCalcRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> InterestCalcResponse:
    """L-F7 利息自动测算引擎：3 种计息基准 × 3 种复利频率。

    业务约束：
    - principal=0 或 rate=0 → 返回 interest_amount=0（合法）
    - start_date > end_date → 返回 400
    - rate > 1.0 → 返回 400
    """
    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    _validate_interest_request(payload)

    result = _calc_interest(payload)

    # 写回
    applied_to_sheet = None
    applied_at = None
    if payload.apply_to_sheet:
        applied_to_sheet = await _maybe_apply_interest_to_workpaper(
            db, wp_id, payload, result
        )
        if applied_to_sheet:
            applied_at = datetime.now(timezone.utc).isoformat()

    return InterestCalcResponse(
        interest_amount=result["interest_amount"],
        daily_interest=result["daily_interest"],
        period_days=result["period_days"],
        day_count_divisor=result["day_count_divisor"],
        calculation_detail=result["calculation_detail"],
        compound_periods=result["compound_periods"],
        applied_to_sheet=applied_to_sheet,
        applied_at=applied_at,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_interest_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: InterestCalcRequest,
    result: dict[str, Any],
) -> str | None:
    """若 apply_to_sheet 给出则把利息测算结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.interest_calcs[sheet] = {
        "method": "interest_calculation",
        "applied_at": ISO8601,
        "data": {
          "wp_code": "L1",
          "principal": "...",
          "annual_rate": "...",
          "start_date": "...",
          "end_date": "...",
          "day_count_basis": "...",
          "compound_frequency": "...",
          "interest_amount": "...",
          "period_days": ...,
          "calculation_detail": "..."
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
    pd.setdefault("interest_calcs", {})
    pd["interest_calcs"][payload.apply_to_sheet] = {
        "method": "interest_calculation",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "wp_code": payload.wp_code,
            "principal": str(payload.principal),
            "annual_rate": str(payload.annual_rate),
            "start_date": payload.start_date.isoformat(),
            "end_date": payload.end_date.isoformat(),
            "day_count_basis": payload.day_count_basis,
            "compound_frequency": payload.compound_frequency,
            "interest_amount": str(result["interest_amount"]),
            "daily_interest": str(result["daily_interest"]),
            "period_days": result["period_days"],
            "day_count_divisor": result["day_count_divisor"],
            "calculation_detail": result["calculation_detail"],
            "compound_periods": result["compound_periods"],
        },
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
