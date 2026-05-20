"""H 固定资产循环 — H-F11 折旧自动测算引擎 API

POST /api/projects/{project_id}/workpapers/{wp_id}/h1/depreciation-calc

支持 4 种折旧方法：
- straight_line（直线法）
- double_declining（双倍余额递减法）
- sum_of_years（年数总和法）
- units_of_production（工作量法）

纯算法 endpoint，无 DB IO（除 apply_to_sheet 写回时 PATCH parsed_data）。

对应 spec：workpaper-h-fixed-assets-cycle H-F11
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/h1",
    tags=["wp-h-depreciation"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class DepreciationCalcRequest(BaseModel):
    """折旧计算请求"""

    method: Literal["straight_line", "double_declining", "sum_of_years", "units_of_production"]
    original_cost: Decimal = Field(..., description="原值")
    residual_rate: Decimal = Field(..., ge=0, le=1, description="残值率（0~1）")
    useful_life_months: int = Field(..., gt=0, description="使用年限（月数）")
    start_month: int = Field(..., ge=1, le=12, description="起始月份（1~12）")
    already_depreciated_months: int = Field(0, ge=0, description="已计提月数")
    # 工作量法专用
    total_units: Decimal | None = Field(None, description="总工作量（工作量法专用）")
    current_period_units: Decimal | None = Field(None, description="当期工作量（工作量法专用）")
    # 写回
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.depreciation_calcs[sheet]",
    )


class DepreciationCalcResponse(BaseModel):
    """折旧计算响应"""

    method: str
    monthly_schedule: list[dict]
    total_depreciation: Decimal
    remaining_book_value: Decimal
    applied_to_sheet: str | None = None


# ─── Validation Helpers ───────────────────────────────────────────────────────


def _validate_request(payload: DepreciationCalcRequest) -> None:
    """校验输入参数范围，超出合理范围返回 400。"""
    if payload.original_cost > Decimal("1e15"):
        raise HTTPException(400, "原值超出合理范围（不能超过 1e15）")
    if payload.original_cost < 0:
        raise HTTPException(400, "原值不能为负数")
    if payload.useful_life_months > 600:
        raise HTTPException(400, "使用年限超出合理范围（不能超过 600 个月）")
    if payload.already_depreciated_months > payload.useful_life_months:
        raise HTTPException(400, "已计提月数不能超过使用年限")
    if payload.method == "units_of_production":
        if payload.total_units is None or payload.current_period_units is None:
            raise HTTPException(422, "工作量法必须提供 total_units 和 current_period_units")
        if payload.total_units == 0:
            raise HTTPException(400, "总工作量不能为零")
        if payload.total_units < 0:
            raise HTTPException(400, "总工作量不能为负数")
        if payload.current_period_units < 0:
            raise HTTPException(400, "当期工作量不能为负数")


# ─── 4 Depreciation Methods ──────────────────────────────────────────────────


def _quantize(value: Decimal) -> Decimal:
    """保留 2 位小数（四舍五入）"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calc_straight_line(
    original_cost: Decimal,
    residual: Decimal,
    useful_life_months: int,
    already_depreciated_months: int,
    *,
    term: Literal["depreciation", "amortization"] = "depreciation",
) -> list[dict]:
    """直线法：monthly_dep = (original_cost - residual) / useful_life_months

    term: 输出 schedule 的金额字段名（'depreciation' 折旧 / 'amortization' 摊销）。
    跨 spec 复用约定（H-F11 → I-F2）：H 默认 'depreciation'，I 传 'amortization'。
    """
    depreciable = original_cost - residual
    if useful_life_months <= 0 or depreciable <= 0:
        return []

    monthly_dep = _quantize(depreciable / useful_life_months)
    schedule: list[dict] = []
    accumulated = Decimal("0")

    remaining_months = useful_life_months - already_depreciated_months
    for i in range(1, remaining_months + 1):
        # 最后一个月用差额，避免累计误差
        if i == remaining_months:
            dep = _quantize(depreciable - accumulated)
        else:
            dep = monthly_dep
        # 确保累计不超过 depreciable
        if accumulated + dep > depreciable:
            dep = _quantize(depreciable - accumulated)
        accumulated += dep
        schedule.append({
            "month": already_depreciated_months + i,
            term: dep,
            "accumulated": accumulated,
        })

    return schedule


def _calc_double_declining(
    original_cost: Decimal,
    residual: Decimal,
    useful_life_months: int,
    already_depreciated_months: int,
    *,
    term: Literal["depreciation", "amortization"] = "depreciation",
) -> list[dict]:
    """双倍余额递减法：
    annual_rate = 2 / (useful_life_months / 12)
    前 N-2 年：月折旧 = 年初账面净值 × annual_rate / 12
    最后 2 年（剩余月数 ≤ 24）：切换为直线法
      月折旧 = (当前账面净值 - residual) / 剩余月数
    """
    depreciable = original_cost - residual
    if useful_life_months <= 0 or depreciable <= 0:
        return []

    useful_life_years = Decimal(str(useful_life_months)) / Decimal("12")
    annual_rate = Decimal("2") / useful_life_years

    schedule: list[dict] = []
    # 从头开始模拟，跳过已计提月份
    book_value = original_cost
    accumulated = Decimal("0")
    remaining_total = useful_life_months

    for month_idx in range(1, useful_life_months + 1):
        remaining_months = useful_life_months - month_idx + 1

        if remaining_months <= 24:
            # 最后 2 年切换为直线法
            # 防御性 max(remaining_months, 1)
            effective_remaining = max(remaining_months, 1)
            monthly_dep = _quantize((book_value - residual) / effective_remaining)
        else:
            # 双倍余额递减
            monthly_dep = _quantize(book_value * annual_rate / Decimal("12"))

        # 确保累计折旧不超过 depreciable
        if accumulated + monthly_dep > depreciable:
            monthly_dep = _quantize(depreciable - accumulated)
        if monthly_dep < 0:
            monthly_dep = Decimal("0")

        accumulated += monthly_dep
        book_value = original_cost - accumulated

        # 只输出已计提月数之后的月份
        if month_idx > already_depreciated_months:
            schedule.append({
                "month": month_idx,
                term: monthly_dep,
                "accumulated": accumulated,
            })

    return schedule


def _calc_sum_of_years(
    original_cost: Decimal,
    residual: Decimal,
    useful_life_months: int,
    already_depreciated_months: int,
    *,
    term: Literal["depreciation", "amortization"] = "depreciation",
) -> list[dict]:
    """年数总和法：
    sum_of_years = useful_life_years × (useful_life_years + 1) / 2
    第 k 年：年折旧 = depreciable × (useful_life_years - k + 1) / sum_of_years
    月折旧 = 年折旧 / 12
    """
    depreciable = original_cost - residual
    if useful_life_months <= 0 or depreciable <= 0:
        return []

    useful_life_years = useful_life_months // 12
    # 处理不足整年的情况
    if useful_life_years <= 0:
        useful_life_years = 1

    sum_of_years = Decimal(str(useful_life_years * (useful_life_years + 1))) / Decimal("2")

    schedule: list[dict] = []
    accumulated = Decimal("0")

    for month_idx in range(1, useful_life_months + 1):
        # 确定当前属于第几年（从 1 开始）
        year_k = (month_idx - 1) // 12 + 1
        if year_k > useful_life_years:
            year_k = useful_life_years

        remaining_years = useful_life_years - year_k + 1
        year_dep = depreciable * Decimal(str(remaining_years)) / sum_of_years
        monthly_dep = _quantize(year_dep / Decimal("12"))

        # 确保累计折旧不超过 depreciable
        if accumulated + monthly_dep > depreciable:
            monthly_dep = _quantize(depreciable - accumulated)
        if monthly_dep < 0:
            monthly_dep = Decimal("0")

        accumulated += monthly_dep

        # 只输出已计提月数之后的月份
        if month_idx > already_depreciated_months:
            schedule.append({
                "month": month_idx,
                term: monthly_dep,
                "accumulated": accumulated,
            })

    return schedule


def _calc_units_of_production(
    original_cost: Decimal,
    residual: Decimal,
    total_units: Decimal,
    current_period_units: Decimal,
    already_depreciated_months: int,
    *,
    term: Literal["depreciation", "amortization"] = "depreciation",
) -> list[dict]:
    """工作量法：
    unit_dep = depreciable / total_units
    period_dep = unit_dep × current_period_units

    term: 输出 schedule 的金额字段名（'depreciation' / 'amortization'）。
    """
    depreciable = original_cost - residual
    if depreciable <= 0 or total_units <= 0:
        return []

    unit_dep = depreciable / total_units
    period_dep = _quantize(unit_dep * current_period_units)

    # 确保不超过 depreciable
    if period_dep > depreciable:
        period_dep = depreciable

    schedule: list[dict] = []
    schedule.append({
        "month": already_depreciated_months + 1,
        term: period_dep,
        "accumulated": period_dep,
    })

    return schedule


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/depreciation-calc", response_model=DepreciationCalcResponse)
async def h1_depreciation_calc(
    project_id: str,
    wp_id: str,
    payload: DepreciationCalcRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> DepreciationCalcResponse:
    """H-F11 折旧自动测算引擎：4 种方法计算月度折旧序列。

    - straight_line: 直线法（每月折旧严格相等）
    - double_declining: 双倍余额递减法（最后 2 年切换直线）
    - sum_of_years: 年数总和法（加速折旧）
    - units_of_production: 工作量法（按当期工作量）
    """
    _validate_request(payload)

    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    residual = _quantize(payload.original_cost * payload.residual_rate)

    if payload.method == "straight_line":
        schedule = _calc_straight_line(
            payload.original_cost, residual,
            payload.useful_life_months, payload.already_depreciated_months,
        )
    elif payload.method == "double_declining":
        schedule = _calc_double_declining(
            payload.original_cost, residual,
            payload.useful_life_months, payload.already_depreciated_months,
        )
    elif payload.method == "sum_of_years":
        schedule = _calc_sum_of_years(
            payload.original_cost, residual,
            payload.useful_life_months, payload.already_depreciated_months,
        )
    elif payload.method == "units_of_production":
        schedule = _calc_units_of_production(
            payload.original_cost, residual,
            payload.total_units,  # type: ignore[arg-type]
            payload.current_period_units,  # type: ignore[arg-type]
            payload.already_depreciated_months,
        )
    else:
        raise HTTPException(400, f"不支持的折旧方法: {payload.method}")

    # 计算汇总
    total_depreciation = schedule[-1]["accumulated"] if schedule else Decimal("0")
    remaining_book_value = payload.original_cost - residual - total_depreciation
    if remaining_book_value < 0:
        remaining_book_value = Decimal("0")

    # 写回
    applied_to_sheet = await _maybe_apply_depreciation_to_workpaper(
        db, wp_id, payload, schedule, total_depreciation, remaining_book_value
    )

    return DepreciationCalcResponse(
        method=payload.method,
        monthly_schedule=schedule,
        total_depreciation=total_depreciation,
        remaining_book_value=remaining_book_value,
        applied_to_sheet=applied_to_sheet,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_depreciation_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: DepreciationCalcRequest,
    schedule: list[dict],
    total_depreciation: Decimal,
    remaining_book_value: Decimal,
) -> str | None:
    """若 apply_to_sheet 给出则把折旧计算结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.depreciation_calcs[sheet] = {
        "method": "straight_line",
        "original_cost": "...",
        "residual_rate": "...",
        "useful_life_months": ...,
        "applied_at": ISO8601,
        "total_depreciation": "...",
        "remaining_book_value": "...",
        "schedule": [...]
      }
    """
    if not payload.apply_to_sheet:
        return None

    from datetime import datetime, timezone
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
    pd.setdefault("depreciation_calcs", {})
    pd["depreciation_calcs"][payload.apply_to_sheet] = {
        "method": payload.method,
        "original_cost": str(payload.original_cost),
        "residual_rate": str(payload.residual_rate),
        "useful_life_months": payload.useful_life_months,
        "start_month": payload.start_month,
        "already_depreciated_months": payload.already_depreciated_months,
        "total_depreciation": str(total_depreciation),
        "remaining_book_value": str(remaining_book_value),
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "schedule": [
            {
                "month": s["month"],
                "depreciation": str(s["depreciation"]),
                "accumulated": str(s["accumulated"]),
            }
            for s in schedule
        ],
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
