"""I1 无形资产 — 摊销引擎验证端点

POST /api/workpapers/{wp_id}/i1/amortization/validate → 验证前端摊销计算
POST /api/workpapers/{wp_id}/i1/amortization/calculate-dcf → 服务端DCF验证

纯函数与前端 useI1AmortizationEngine.ts 对等：
- calcStraightLineAmort: (cost - salvage) / usefulLifeMonths
- calcRemainingLifeAmort: (cost - salvage - accAmort - impairment) / remainingMonths
- calcAmortWithImpairment: 同上（减值发生后重算基数）
- calcDcfPresentValue: Σ(CF_i/(1+r)^(i+1))
- calcTerminalValue: perpetuityCF / (discountRate - growthRate)
- calcRecoverableAmount: MAX(fairValueLessDisposal, valueInUse)
- calcImpairmentAmount: MAX(bookValue - recoverableAmount, 0)

Requirements: 11.4-11.5, 12.2, 13.2-13.3
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

router = APIRouter(tags=["i1-amortization"])


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：摊销计算引擎（与前端 useI1AmortizationEngine.ts 对等）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_straight_line_amort(cost: float, salvage: float, useful_life_months: int) -> float:
    """直线法月摊销 = (原值 - 残值) / 使用寿命月数."""
    if useful_life_months <= 0:
        return 0.0
    return (cost - salvage) / useful_life_months


def calc_remaining_life_amort(
    cost: float, salvage: float, acc_amort: float, impairment: float, remaining_months: int
) -> float:
    """剩余年限法月摊销 = (原值 - 残值 - 累计摊销 - 减值准备) / 剩余月数."""
    if remaining_months <= 0:
        return 0.0
    return (cost - salvage - acc_amort - impairment) / remaining_months


def calc_amort_with_impairment(
    cost: float, salvage: float, acc_amort: float, impairment: float, remaining_months: int
) -> float:
    """含减值重算基数摊销（减值发生月重新计算剩余摊销基数）.

    公式与 calc_remaining_life_amort 相同，语义区分：
    I1-11含减值版本在减值发生后调用此函数重新计算。
    """
    if remaining_months <= 0:
        return 0.0
    return (cost - salvage - acc_amort - impairment) / remaining_months


def calc_dcf_present_value(cash_flows: list[float], discount_rate: float) -> float:
    """DCF现值 = Σ(CF_i / (1+r)^(i+1))  (i从0开始).

    空数组或折现率<=0返回0。
    """
    if not cash_flows or discount_rate <= 0:
        return 0.0
    pv = 0.0
    for i, cf in enumerate(cash_flows):
        pv += cf / ((1 + discount_rate) ** (i + 1))
    return pv


def calc_terminal_value(perpetuity_cf: float, discount_rate: float, growth_rate: float) -> float:
    """终值（永续价值）= 永续现金流 / (折现率 - 增长率).

    Gordon Growth Model。当 discountRate <= growthRate 时返回 0。
    """
    if discount_rate <= growth_rate:
        return 0.0
    return perpetuity_cf / (discount_rate - growth_rate)


def calc_recoverable_amount(fair_value_less_disposal: float, value_in_use: float) -> float:
    """可收回金额 = MAX(公允价值-处置费用, 使用价值DCF)."""
    return max(fair_value_less_disposal, value_in_use)


def calc_impairment_amount(book_value: float, recoverable_amount: float) -> float:
    """减值金额 = MAX(账面净值 - 可收回金额, 0)，但不超过账面净值."""
    raw = book_value - recoverable_amount
    if raw <= 0:
        return 0.0
    return min(raw, book_value)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 模型
# ═══════════════════════════════════════════════════════════════════════════════


class AmortizationAssetInput(BaseModel):
    """单个无形资产摊销测算输入."""

    asset_id: str = ""
    asset_name: str = ""
    cost: float = Field(ge=0, description="无形资产原值")
    salvage: float = Field(ge=0, default=0, description="预计残值")
    acc_amort: float = Field(ge=0, default=0, description="已计提累计摊销")
    impairment: float = Field(ge=0, default=0, description="已计提减值准备")
    useful_life_months: int = Field(ge=0, default=0, description="使用寿命总月数")
    remaining_months: int = Field(ge=0, default=0, description="剩余使用月数")
    method: str = Field(
        default="straight_line",
        description="摊销方法：straight_line | remaining_life | with_impairment",
    )
    book_amortization: float = Field(default=0, description="账面摊销金额（用于差异验证）")


class AmortizationResult(BaseModel):
    """单个资产摊销计算结果."""

    asset_id: str = ""
    asset_name: str = ""
    monthly_amortization: float
    annual_amortization: float
    method_used: str
    book_amortization: float = 0
    difference: float = 0
    is_within_tolerance: bool = True


class ValidateAmortizationRequest(BaseModel):
    """摊销验证请求."""

    assets: list[AmortizationAssetInput]
    tolerance: float = Field(default=1.0, description="允许的差异容忍度（元），默认1元")


class ValidateAmortizationResponse(BaseModel):
    """摊销验证响应."""

    is_valid: bool
    total_calculated: float
    total_book: float
    total_difference: float
    results: list[AmortizationResult]
    discrepancies: list[AmortizationResult]
    summary: str


class DcfInput(BaseModel):
    """DCF计算输入."""

    asset_id: str = ""
    asset_name: str = ""
    cash_flows: list[float] = Field(description="各期预测现金流数组")
    discount_rate: float = Field(gt=0, description="折现率(如0.08表示8%)")
    growth_rate: float = Field(default=0, description="永续增长率")
    perpetuity_cf: float = Field(default=0, description="永续年金现金流（终值计算用）")
    fair_value_less_disposal: float = Field(default=0, description="公允价值减处置费用")
    book_value: float = Field(ge=0, default=0, description="账面净值")


class DcfResult(BaseModel):
    """DCF计算结果."""

    asset_id: str = ""
    asset_name: str = ""
    present_value: float
    terminal_value: float
    terminal_value_pv: float
    value_in_use: float
    fair_value_less_disposal: float
    recoverable_amount: float
    impairment_amount: float
    sensitivity: dict[str, Any] = Field(default_factory=dict, description="敏感性分析结果")


class CalculateDcfRequest(BaseModel):
    """DCF批量计算请求."""

    assets: list[DcfInput]
    include_sensitivity: bool = Field(default=True, description="是否包含敏感性分析")


class CalculateDcfResponse(BaseModel):
    """DCF计算响应."""

    results: list[DcfResult]
    summary: str


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


def _calculate_single_amort(asset: AmortizationAssetInput) -> AmortizationResult:
    """计算单个无形资产的月摊销额."""
    monthly = 0.0

    if asset.method == "straight_line":
        monthly = calc_straight_line_amort(asset.cost, asset.salvage, asset.useful_life_months)
    elif asset.method == "remaining_life":
        monthly = calc_remaining_life_amort(
            asset.cost, asset.salvage, asset.acc_amort, asset.impairment, asset.remaining_months
        )
    elif asset.method == "with_impairment":
        monthly = calc_amort_with_impairment(
            asset.cost, asset.salvage, asset.acc_amort, asset.impairment, asset.remaining_months
        )
    else:
        # 默认直线法
        monthly = calc_straight_line_amort(asset.cost, asset.salvage, asset.useful_life_months)

    annual = monthly * 12
    difference = asset.book_amortization - annual if asset.book_amortization else 0.0

    return AmortizationResult(
        asset_id=asset.asset_id,
        asset_name=asset.asset_name,
        monthly_amortization=round(monthly, 2),
        annual_amortization=round(annual, 2),
        method_used=asset.method,
        book_amortization=asset.book_amortization,
        difference=round(difference, 2),
        is_within_tolerance=True,  # 由调用方根据tolerance判断
    )


def _calculate_single_dcf(inp: DcfInput, include_sensitivity: bool = True) -> DcfResult:
    """计算单个资产的DCF可收回金额+减值金额."""
    # 现值
    pv = calc_dcf_present_value(inp.cash_flows, inp.discount_rate)

    # 终值
    tv = 0.0
    tv_pv = 0.0
    if inp.perpetuity_cf > 0:
        tv = calc_terminal_value(inp.perpetuity_cf, inp.discount_rate, inp.growth_rate)
        # 终值折现到当前
        n = len(inp.cash_flows)
        tv_pv = tv / ((1 + inp.discount_rate) ** n) if n > 0 else tv

    # 使用价值 = 预测期现值 + 终值现值
    value_in_use = pv + tv_pv

    # 可收回金额
    recoverable = calc_recoverable_amount(inp.fair_value_less_disposal, value_in_use)

    # 减值金额
    impairment = calc_impairment_amount(inp.book_value, recoverable) if inp.book_value > 0 else 0.0

    # 敏感性分析
    sensitivity: dict[str, Any] = {}
    if include_sensitivity and inp.cash_flows:
        # 折现率 ±1%
        rate_up = inp.discount_rate + 0.01
        rate_down = max(inp.discount_rate - 0.01, 0.001)
        pv_rate_up = calc_dcf_present_value(inp.cash_flows, rate_up)
        pv_rate_down = calc_dcf_present_value(inp.cash_flows, rate_down)

        # 增长率 ±0.5%
        growth_up = inp.growth_rate + 0.005
        growth_down = inp.growth_rate - 0.005
        tv_growth_up = calc_terminal_value(inp.perpetuity_cf, inp.discount_rate, growth_up) if inp.perpetuity_cf > 0 else 0.0
        tv_growth_down = calc_terminal_value(inp.perpetuity_cf, inp.discount_rate, growth_down) if inp.perpetuity_cf > 0 else 0.0

        sensitivity = {
            "discount_rate_plus_1pct": {
                "rate": round(rate_up, 4),
                "present_value": round(pv_rate_up, 2),
            },
            "discount_rate_minus_1pct": {
                "rate": round(rate_down, 4),
                "present_value": round(pv_rate_down, 2),
            },
            "growth_rate_plus_05pct": {
                "rate": round(growth_up, 4),
                "terminal_value": round(tv_growth_up, 2),
            },
            "growth_rate_minus_05pct": {
                "rate": round(growth_down, 4),
                "terminal_value": round(tv_growth_down, 2),
            },
        }

    return DcfResult(
        asset_id=inp.asset_id,
        asset_name=inp.asset_name,
        present_value=round(pv, 2),
        terminal_value=round(tv, 2),
        terminal_value_pv=round(tv_pv, 2),
        value_in_use=round(value_in_use, 2),
        fair_value_less_disposal=round(inp.fair_value_less_disposal, 2),
        recoverable_amount=round(recoverable, 2),
        impairment_amount=round(impairment, 2),
        sensitivity=sensitivity,
    )


@router.post(
    "/api/workpapers/{wp_id}/i1/amortization/validate",
    response_model=ValidateAmortizationResponse,
)
async def i1_amortization_validate(
    wp_id: str,
    body: ValidateAmortizationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidateAmortizationResponse:
    """验证前端摊销计算结果与后端引擎的差异.

    对每个资产按指定方法（直线法/剩余年限法/含减值）计算月摊销额，
    与账面摊销比较，超出容忍度的标记为差异项。
    """
    if not body.assets:
        raise HTTPException(400, "assets 列表不能为空")

    results = [_calculate_single_amort(asset) for asset in body.assets]

    # 根据tolerance标记差异
    for r in results:
        r.is_within_tolerance = abs(r.difference) <= body.tolerance

    discrepancies = [r for r in results if not r.is_within_tolerance]
    total_calculated = sum(r.annual_amortization for r in results)
    total_book = sum(r.book_amortization for r in results)
    total_difference = total_book - total_calculated
    is_valid = len(discrepancies) == 0

    summary = (
        f"共{len(results)}项无形资产，"
        f"测算摊销合计={total_calculated:,.2f}元，"
        f"账面摊销合计={total_book:,.2f}元，"
        f"总差异={total_difference:,.2f}元，"
        f"{'全部通过' if is_valid else f'有{len(discrepancies)}项超容忍度({body.tolerance}元)'}"
    )

    return ValidateAmortizationResponse(
        is_valid=is_valid,
        total_calculated=round(total_calculated, 2),
        total_book=round(total_book, 2),
        total_difference=round(total_difference, 2),
        results=results,
        discrepancies=discrepancies,
        summary=summary,
    )


@router.post(
    "/api/workpapers/{wp_id}/i1/amortization/calculate-dcf",
    response_model=CalculateDcfResponse,
)
async def i1_amortization_calculate_dcf(
    wp_id: str,
    body: CalculateDcfRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalculateDcfResponse:
    """服务端DCF计算验证.

    对每个资产执行：
    1. 计算预测期现金流现值 PV=Σ(CF_i/(1+r)^(i+1))
    2. 计算终值（Gordon模型）并折现
    3. 使用价值 = PV + TV_PV
    4. 可收回金额 = MAX(公允-处置费, 使用价值)
    5. 减值金额 = MAX(账面-可收回, 0)
    6. 可选敏感性分析（折现率±1%，增长率±0.5%）
    """
    if not body.assets:
        raise HTTPException(400, "assets 列表不能为空")

    results = [_calculate_single_dcf(inp, body.include_sensitivity) for inp in body.assets]

    total_impairment = sum(r.impairment_amount for r in results)
    assets_with_impairment = sum(1 for r in results if r.impairment_amount > 0)

    summary = (
        f"共{len(results)}项无形资产DCF测试，"
        f"{'全部无需计提减值' if assets_with_impairment == 0 else f'有{assets_with_impairment}项需计提减值'}，"
        f"减值合计={total_impairment:,.2f}元"
    )

    return CalculateDcfResponse(
        results=results,
        summary=summary,
    )
