"""H1 固定资产 — 折旧引擎端点

POST /api/workpapers/{wp_id}/h1/depreciation/calculate → 批量计算
POST /api/workpapers/{wp_id}/h1/depreciation/validate → 验证差异

4种折旧方法：直线法/双倍余额递减/年数总和法/工作量法
支持含减值+多次减值场景
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["h1-depreciation"])


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：折旧计算引擎（与前端 useH1DepreciationEngine.ts 对等）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_straight_line(cost: float, salvage_rate: float, useful_life_years: int) -> float:
    """直线法月折旧 = 原值×(1-残值率) / 使用年限 / 12."""
    if useful_life_years <= 0:
        return 0.0
    return cost * (1 - salvage_rate) / useful_life_years / 12


def calc_double_declining(
    net_value: float,
    useful_life_years: int,
    elapsed_months: int,
    total_months: int,
    salvage: float = 0.0,
) -> float:
    """双倍余额递减法月折旧.

    前期：净值 × 2 / 使用年限 / 12
    最后24个月（转直线）：(净值 - 残值) / 24
    """
    if useful_life_years <= 0 or total_months <= 0:
        return 0.0
    remaining_months = total_months - elapsed_months
    if remaining_months <= 24:
        # 最后两年转直线法
        return max((net_value - salvage) / 24, 0.0) if remaining_months > 0 else 0.0
    return net_value * 2 / useful_life_years / 12


def calc_sum_of_years(
    cost: float,
    salvage_rate: float,
    useful_life_years: int,
    remaining_years: int,
) -> float:
    """年数总和法月折旧 = 原值×(1-残值率) × 剩余年限 / 年数总和 / 12."""
    if useful_life_years <= 0 or remaining_years <= 0:
        return 0.0
    sum_of_years = useful_life_years * (useful_life_years + 1) / 2
    return cost * (1 - salvage_rate) * remaining_years / sum_of_years / 12


def calc_units_of_production(
    cost: float,
    salvage_rate: float,
    total_units: float,
    current_units: float,
) -> float:
    """工作量法月折旧 = 原值×(1-残值率) / 预计总工作量 × 当月工作量."""
    if total_units <= 0:
        return 0.0
    unit_dep = cost * (1 - salvage_rate) / total_units
    return unit_dep * current_units


def calc_depreciation_with_impairment(
    cost: float,
    salvage_rate: float,
    useful_life_years: int,
    impairment: float,
    elapsed_months: int,
) -> float:
    """含减值直线法：减值后净值按剩余年限重新计算月折旧."""
    if useful_life_years <= 0:
        return 0.0
    total_months = useful_life_years * 12
    remaining_months = total_months - elapsed_months
    if remaining_months <= 0:
        return 0.0
    salvage = cost * salvage_rate
    depreciable_base = cost - salvage - impairment
    # 已计折旧 = 月折旧 × 已用月数（减值前直线法）
    pre_impairment_monthly = cost * (1 - salvage_rate) / total_months
    accumulated_dep = pre_impairment_monthly * elapsed_months
    # 减值后剩余可折旧额
    remaining_depreciable = max(depreciable_base - accumulated_dep, 0.0)
    return remaining_depreciable / remaining_months


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic模型
# ═══════════════════════════════════════════════════════════════════════════════


class DepreciationAssetInput(BaseModel):
    asset_id: str = ""
    asset_category: str = ""
    original_cost: float = Field(ge=0)
    salvage_rate: float = Field(ge=0, le=1)
    useful_life_years: int = Field(ge=1, le=100)
    method: str = Field(description="straight_line|double_declining|sum_of_years|units_of_production")
    elapsed_months: int = Field(ge=0, default=0)
    impairment: float = Field(ge=0, default=0)
    impairment_points: list[dict[str, Any]] = Field(default_factory=list)
    total_units: float = Field(ge=0, default=0)
    current_units: float = Field(ge=0, default=0)
    book_depreciation: float = Field(default=0, description="账面折旧金额（用于差异验证）")


class DepreciationResult(BaseModel):
    asset_id: str = ""
    asset_category: str = ""
    monthly_depreciation: float
    annual_depreciation: float
    accumulated_depreciation: float
    net_value: float
    method_used: str
    book_depreciation: float = 0
    difference: float = 0
    is_within_tolerance: bool = True


class CalculateRequest(BaseModel):
    assets: list[DepreciationAssetInput]


class CalculateResponse(BaseModel):
    results: list[DepreciationResult]
    total_calculated: float
    total_book: float
    total_difference: float


class ValidateRequest(BaseModel):
    assets: list[DepreciationAssetInput]
    tolerance: float = Field(default=1.0, description="允许的差异容忍度（元），默认1元")


class ValidateResponse(BaseModel):
    is_valid: bool
    total_difference: float
    discrepancies: list[DepreciationResult]
    summary: str


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


def _calculate_single(asset: DepreciationAssetInput) -> DepreciationResult:
    """计算单个资产的折旧."""
    cost = asset.original_cost
    salvage_rate = asset.salvage_rate
    life = asset.useful_life_years
    elapsed = asset.elapsed_months
    total_months = life * 12

    monthly = 0.0
    if asset.method == "straight_line":
        if asset.impairment > 0:
            monthly = calc_depreciation_with_impairment(cost, salvage_rate, life, asset.impairment, elapsed)
        else:
            monthly = calc_straight_line(cost, salvage_rate, life)
    elif asset.method == "double_declining":
        salvage = cost * salvage_rate
        # 计算当前净值（近似：原值-已有折旧-减值）
        pre_monthly = calc_straight_line(cost, salvage_rate, life)
        accumulated = pre_monthly * elapsed
        net_value = cost - accumulated - asset.impairment
        monthly = calc_double_declining(net_value, life, elapsed, total_months, salvage)
    elif asset.method == "sum_of_years":
        remaining_years = max(life - (elapsed // 12), 1)
        monthly = calc_sum_of_years(cost, salvage_rate, life, remaining_years)
    elif asset.method == "units_of_production":
        monthly = calc_units_of_production(cost, salvage_rate, asset.total_units, asset.current_units)
    else:
        monthly = calc_straight_line(cost, salvage_rate, life)

    annual = monthly * 12
    accumulated = monthly * elapsed
    salvage_amount = cost * salvage_rate
    net_value = max(cost - accumulated - asset.impairment - salvage_amount, 0.0)
    difference = asset.book_depreciation - annual if asset.book_depreciation else 0.0

    return DepreciationResult(
        asset_id=asset.asset_id,
        asset_category=asset.asset_category,
        monthly_depreciation=round(monthly, 2),
        annual_depreciation=round(annual, 2),
        accumulated_depreciation=round(accumulated, 2),
        net_value=round(net_value, 2),
        method_used=asset.method,
        book_depreciation=asset.book_depreciation,
        difference=round(difference, 2),
        is_within_tolerance=abs(difference) <= monthly,
    )


@router.post("/api/workpapers/{wp_id}/h1/depreciation/calculate", response_model=CalculateResponse)
async def h1_depreciation_calculate(
    wp_id: str,
    body: CalculateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalculateResponse:
    """批量计算固定资产折旧（4方法+含减值+多次减值）."""
    if not body.assets:
        raise HTTPException(400, "assets 列表不能为空")

    results = [_calculate_single(asset) for asset in body.assets]
    total_calculated = sum(r.annual_depreciation for r in results)
    total_book = sum(r.book_depreciation for r in results)

    return CalculateResponse(
        results=results,
        total_calculated=round(total_calculated, 2),
        total_book=round(total_book, 2),
        total_difference=round(total_book - total_calculated, 2),
    )


@router.post("/api/workpapers/{wp_id}/h1/depreciation/validate", response_model=ValidateResponse)
async def h1_depreciation_validate(
    wp_id: str,
    body: ValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidateResponse:
    """验证账面折旧与测算折旧的差异."""
    if not body.assets:
        raise HTTPException(400, "assets 列表不能为空")

    results = [_calculate_single(asset) for asset in body.assets]
    discrepancies = [r for r in results if abs(r.difference) > body.tolerance]
    total_difference = sum(r.difference for r in results)
    is_valid = len(discrepancies) == 0

    summary = (
        f"共{len(results)}项资产，"
        f"测算折旧合计={sum(r.annual_depreciation for r in results):,.2f}元，"
        f"账面折旧合计={sum(r.book_depreciation for r in results):,.2f}元，"
        f"总差异={total_difference:,.2f}元，"
        f"{'全部通过' if is_valid else f'有{len(discrepancies)}项超容忍度'}"
    )

    return ValidateResponse(
        is_valid=is_valid,
        total_difference=round(total_difference, 2),
        discrepancies=discrepancies,
        summary=summary,
    )
