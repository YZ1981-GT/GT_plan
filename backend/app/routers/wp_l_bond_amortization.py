"""L 筹资循环 — L-F8 应付债券摊余成本引擎 API

POST /api/projects/{project_id}/workpapers/{wp_id}/l5/bond-amortization

实际利率法摊余成本计算引擎：
- 每期利息费用 = 期初摊余成本 × 实际利率 / 付息频率
- 每期票面利息 = 面值 × 票面利率 / 付息频率
- 每期摊销额 = 利息费用 - 票面利息
- 期末摊余成本 = 期初摊余成本 + 摊销额

收敛性约束：final_carrying_amount ≈ face_value (±0.01)，最后一期做尾差调整。

写回模式：parsed_data.bond_amortization[sheet] = {method, applied_at, data}
is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动。

对应 spec：workpaper-l-debt-cycle L-F8 / ADR-L5
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/l5",
    tags=["wp-l-bond-amortization"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class BondAmortizationRequest(BaseModel):
    """应付债券摊余成本计算请求"""

    face_value: Decimal = Field(..., description="面值")
    issue_price: Decimal = Field(..., description="发行价格（溢价/折价）")
    coupon_rate: Decimal = Field(..., ge=0, description="票面利率（如 0.05 = 5%）")
    effective_rate: Decimal = Field(..., description="实际利率（如 0.06 = 6%）")
    term_years: int = Field(..., description="期限（年）")
    payment_frequency: Literal["annual", "semi_annual", "quarterly"] = Field(
        ..., description="付息频率"
    )
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.bond_amortization[sheet]",
    )


class AmortizationScheduleItem(BaseModel):
    """摊余成本表单期明细"""

    period: int = Field(..., description="期数")
    opening_carrying: str = Field(..., description="期初摊余成本")
    interest_expense: str = Field(..., description="利息费用")
    coupon_payment: str = Field(..., description="票面利息")
    amortization: str = Field(..., description="摊销额")
    closing_carrying: str = Field(..., description="期末摊余成本")


class BondAmortizationResponse(BaseModel):
    """应付债券摊余成本计算响应"""

    amortization_schedule: list[dict] = Field(..., description="摊余成本表")
    total_interest_expense: str = Field(..., description="利息费用合计")
    total_coupon_payments: str = Field(..., description="票面利息合计")
    total_amortization: str = Field(..., description="摊销额合计")
    final_carrying_amount: str = Field(..., description="最终期末摊余成本（应收敛到面值）")
    is_llm_stub: bool = Field(..., description="是否为 LLM stub 实现")
    applied_to_sheet: str | None = None
    applied_at: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _quantize(value: Decimal) -> Decimal:
    """保留 2 位小数（四舍五入）"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _get_periods_per_year(frequency: str) -> int:
    """获取每年付息次数"""
    if frequency == "annual":
        return 1
    elif frequency == "semi_annual":
        return 2
    elif frequency == "quarterly":
        return 4
    return 1


def _validate_bond_request(payload: BondAmortizationRequest) -> None:
    """校验输入参数，严重错误抛 HTTPException 400。"""
    if payload.face_value == 0:
        raise HTTPException(400, "面值不能为 0（face_value=0）")
    if payload.effective_rate == 0:
        raise HTTPException(400, "实际利率不能为 0（effective_rate=0）")
    if payload.term_years == 0:
        raise HTTPException(400, "期限不能为 0（term_years=0）")


def _calc_amortization_schedule(payload: BondAmortizationRequest) -> dict[str, Any]:
    """计算摊余成本表（实际利率法 + 尾差调整）。

    返回包含所有响应字段的字典。
    """
    face_value = payload.face_value
    issue_price = payload.issue_price
    coupon_rate = payload.coupon_rate
    effective_rate = payload.effective_rate
    term_years = payload.term_years
    frequency = payload.payment_frequency

    periods_per_year = _get_periods_per_year(frequency)
    total_periods = term_years * periods_per_year

    # 每期票面利息 = 面值 × 票面利率 / 付息频率
    coupon_per_period = face_value * coupon_rate / Decimal(str(periods_per_year))

    # 每期实际利率
    effective_rate_per_period = effective_rate / Decimal(str(periods_per_year))

    schedule: list[dict[str, Any]] = []
    carrying = issue_price
    total_interest = Decimal("0")
    total_coupon = Decimal("0")
    total_amort = Decimal("0")

    for period in range(1, total_periods + 1):
        opening = carrying

        if period == total_periods:
            # 最后一期做尾差调整：确保 closing = face_value
            coupon = _quantize(coupon_per_period)
            # 摊销额 = face_value - opening（尾差调整）
            amortization = face_value - opening
            interest_expense = coupon + amortization
            closing = face_value
        else:
            # 每期利息费用 = 期初摊余成本 × 实际利率 / 付息频率
            interest_expense = _quantize(opening * effective_rate_per_period)
            coupon = _quantize(coupon_per_period)
            # 每期摊销额 = 利息费用 - 票面利息
            amortization = interest_expense - coupon
            # 期末摊余成本 = 期初摊余成本 + 摊销额
            closing = opening + amortization

        total_interest += interest_expense
        total_coupon += coupon
        total_amort += amortization

        schedule.append({
            "period": period,
            "opening_carrying": str(_quantize(opening)),
            "interest_expense": str(_quantize(interest_expense)),
            "coupon_payment": str(_quantize(coupon)),
            "amortization": str(_quantize(amortization)),
            "closing_carrying": str(_quantize(closing)),
        })

        carrying = closing

    return {
        "amortization_schedule": schedule,
        "total_interest_expense": str(_quantize(total_interest)),
        "total_coupon_payments": str(_quantize(total_coupon)),
        "total_amortization": str(_quantize(total_amort)),
        "final_carrying_amount": str(_quantize(carrying)),
    }


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/bond-amortization", response_model=BondAmortizationResponse)
async def l_bond_amortization(
    project_id: str,
    wp_id: str,
    payload: BondAmortizationRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> BondAmortizationResponse:
    """L-F8 应付债券摊余成本引擎：实际利率法 + 收敛性尾差调整。

    业务约束：
    - face_value=0 → 400
    - effective_rate=0 → 400
    - term_years=0 → 400
    - is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动
    - 支持 apply_to_sheet 写回
    """
    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    _validate_bond_request(payload)

    result = _calc_amortization_schedule(payload)

    # is_llm_stub 由配置驱动
    is_llm_stub = not getattr(settings, "WP_AI_SERVICE_ENABLED", False)

    # 写回
    applied_to_sheet = None
    applied_at = None
    if payload.apply_to_sheet:
        applied_to_sheet = await _maybe_apply_to_workpaper(
            db, wp_id, payload, result
        )
        if applied_to_sheet:
            applied_at = datetime.now(timezone.utc).isoformat()

    return BondAmortizationResponse(
        amortization_schedule=result["amortization_schedule"],
        total_interest_expense=result["total_interest_expense"],
        total_coupon_payments=result["total_coupon_payments"],
        total_amortization=result["total_amortization"],
        final_carrying_amount=result["final_carrying_amount"],
        is_llm_stub=is_llm_stub,
        applied_to_sheet=applied_to_sheet,
        applied_at=applied_at,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: BondAmortizationRequest,
    result: dict[str, Any],
) -> str | None:
    """若 apply_to_sheet 给出则把摊余成本结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.bond_amortization[sheet] = {
        "method": "effective_interest_rate",
        "applied_at": ISO8601,
        "data": {
          "face_value": "...",
          "issue_price": "...",
          "coupon_rate": "...",
          "effective_rate": "...",
          "term_years": ...,
          "payment_frequency": "...",
          "total_interest_expense": "...",
          "total_coupon_payments": "...",
          "total_amortization": "...",
          "final_carrying_amount": "...",
          "schedule_periods": ...
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
    pd.setdefault("bond_amortization", {})
    pd["bond_amortization"][payload.apply_to_sheet] = {
        "method": "effective_interest_rate",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "face_value": str(payload.face_value),
            "issue_price": str(payload.issue_price),
            "coupon_rate": str(payload.coupon_rate),
            "effective_rate": str(payload.effective_rate),
            "term_years": payload.term_years,
            "payment_frequency": payload.payment_frequency,
            "total_interest_expense": result["total_interest_expense"],
            "total_coupon_payments": result["total_coupon_payments"],
            "total_amortization": result["total_amortization"],
            "final_carrying_amount": result["final_carrying_amount"],
            "schedule_periods": len(result["amortization_schedule"]),
        },
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    from app.services.wp_parsed_data_service import touch_after_parsed_data_commit

    await touch_after_parsed_data_commit(wp, source="wp_l_bond_amortization")
    return payload.apply_to_sheet
