"""J 职工薪酬循环 — J-F8 股份支付 Black-Scholes 公允价值计算

POST /api/projects/{project_id}/workpapers/{wp_id}/j3/share-payment-calc

实现 Black-Scholes 期权定价公式（含股息率 q）：
  C = S·e^(-qT)·N(d1) − K·e^(-rT)·N(d2)
  d1 = [ln(S/K) + (r - q + σ²/2)T] / (σ√T)
  d2 = d1 - σ√T

写回模式：parsed_data.share_payment_calcs[sheet] = {method, applied_at, data}
is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动。

对应 spec：workpaper-j-payroll-cycle J-F8 / ADR-J5
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/j3",
    tags=["wp-j-share-payment"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class SharePaymentCalcRequest(BaseModel):
    """股份支付公允价值计算请求"""

    stock_price: float = Field(..., gt=0, description="标的股票价格 S")
    exercise_price: float = Field(..., gt=0, description="行权价格 K")
    risk_free_rate: float = Field(..., ge=0, le=1, description="无风险利率 r")
    volatility: float = Field(..., gt=0, le=5, description="波动率 σ")
    time_to_maturity: float = Field(..., gt=0, description="到期时间 T（年）")
    dividend_yield: float = Field(0.0, ge=0, le=1, description="股息率 q")
    grant_quantity: int = Field(..., ge=1, description="授予数量")
    vesting_period: int = Field(..., ge=1, le=10, description="等待期（年）")
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.share_payment_calcs[sheet]",
    )


class AnnualExpenseItem(BaseModel):
    """年度费用摊销明细"""

    year: int
    expense: float
    cumulative: float


class SharePaymentCalcResponse(BaseModel):
    """股份支付公允价值计算响应"""

    option_value: float
    total_fair_value: float
    annual_expense_schedule: list[AnnualExpenseItem]
    is_llm_stub: bool
    applied_to_sheet: str | None = None
    applied_at: str | None = None


# ─── Black-Scholes Core ───────────────────────────────────────────────────────


def _norm_cdf(x: float) -> float:
    """标准正态分布累积分布函数 N(x)"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _black_scholes_call(
    S: float, K: float, r: float, sigma: float, T: float, q: float = 0.0
) -> float:
    """Black-Scholes 看涨期权定价（含股息率 q）

    C = S·e^(-qT)·N(d1) − K·e^(-rT)·N(d2)
    d1 = [ln(S/K) + (r - q + σ²/2)T] / (σ√T)
    d2 = d1 - σ√T
    """
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    call_value = S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return call_value


def _quantize(value: float, places: int = 2) -> float:
    """保留指定小数位"""
    return round(value, places)


def _validate_share_payment_request(payload: SharePaymentCalcRequest) -> None:
    """校验输入参数，严重错误抛 HTTPException 400。"""
    if payload.volatility <= 0:
        raise HTTPException(400, "波动率 σ 必须 > 0")
    if payload.time_to_maturity <= 0:
        raise HTTPException(400, "到期时间 T 必须 > 0")
    if payload.stock_price <= 0:
        raise HTTPException(400, "标的股票价格 S 必须 > 0")
    if payload.exercise_price <= 0:
        raise HTTPException(400, "行权价格 K 必须 > 0")


def _calc_share_payment(payload: SharePaymentCalcRequest) -> dict[str, Any]:
    """计算期权价值 + 费用摊销计划"""
    option_value = _black_scholes_call(
        S=payload.stock_price,
        K=payload.exercise_price,
        r=payload.risk_free_rate,
        sigma=payload.volatility,
        T=payload.time_to_maturity,
        q=payload.dividend_yield,
    )
    option_value = _quantize(option_value, 4)

    total_fair_value = _quantize(option_value * payload.grant_quantity, 2)

    # 等待期内直线法摊销
    annual_expense = _quantize(total_fair_value / payload.vesting_period, 2)
    schedule: list[dict[str, Any]] = []
    cumulative = 0.0
    for year in range(1, payload.vesting_period + 1):
        # 最后一年吸收尾差
        if year == payload.vesting_period:
            expense = _quantize(total_fair_value - cumulative, 2)
        else:
            expense = annual_expense
        cumulative = _quantize(cumulative + expense, 2)
        schedule.append({
            "year": year,
            "expense": expense,
            "cumulative": cumulative,
        })

    return {
        "option_value": option_value,
        "total_fair_value": total_fair_value,
        "annual_expense_schedule": schedule,
    }


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/share-payment-calc", response_model=SharePaymentCalcResponse)
async def j3_share_payment_calc(
    project_id: str,
    wp_id: str,
    payload: SharePaymentCalcRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> SharePaymentCalcResponse:
    """J-F8 股份支付公允价值计算（Black-Scholes）

    业务约束：
    - σ=0 / T=0 / S<=0 / K<=0 → 400
    - is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动
    - 支持 apply_to_sheet 写回
    """
    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    _validate_share_payment_request(payload)

    result = _calc_share_payment(payload)

    # is_llm_stub 由配置驱动
    is_llm_stub = not getattr(settings, "WP_AI_SERVICE_ENABLED", False)

    # 写回
    applied_to_sheet = None
    applied_at = None
    if payload.apply_to_sheet:
        applied_to_sheet = await _maybe_apply_share_payment_to_workpaper(
            db, wp_id, payload, result
        )
        if applied_to_sheet:
            applied_at = datetime.now(timezone.utc).isoformat()

    return SharePaymentCalcResponse(
        option_value=result["option_value"],
        total_fair_value=result["total_fair_value"],
        annual_expense_schedule=[
            AnnualExpenseItem(**item) for item in result["annual_expense_schedule"]
        ],
        is_llm_stub=is_llm_stub,
        applied_to_sheet=applied_to_sheet,
        applied_at=applied_at,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_share_payment_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: SharePaymentCalcRequest,
    result: dict[str, Any],
) -> str | None:
    """若 apply_to_sheet 给出则把股份支付计算结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.share_payment_calcs[sheet] = {
        "method": "black_scholes",
        "applied_at": ISO8601,
        "data": {
          "stock_price": ...,
          "exercise_price": ...,
          "risk_free_rate": ...,
          "volatility": ...,
          "time_to_maturity": ...,
          "dividend_yield": ...,
          "grant_quantity": ...,
          "vesting_period": ...,
          "option_value": ...,
          "total_fair_value": ...,
          "annual_expense_schedule": [...]
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
    pd.setdefault("share_payment_calcs", {})
    pd["share_payment_calcs"][payload.apply_to_sheet] = {
        "method": "black_scholes",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "stock_price": payload.stock_price,
            "exercise_price": payload.exercise_price,
            "risk_free_rate": payload.risk_free_rate,
            "volatility": payload.volatility,
            "time_to_maturity": payload.time_to_maturity,
            "dividend_yield": payload.dividend_yield,
            "grant_quantity": payload.grant_quantity,
            "vesting_period": payload.vesting_period,
            **result,
        },
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
