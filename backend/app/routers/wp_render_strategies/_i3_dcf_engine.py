"""I3 商誉 — DCF引擎验证端点 + 减值分摊验证

POST /api/workpapers/{wp_id}/i3/dcf/validate → 验证前端DCF计算
POST /api/workpapers/{wp_id}/i3/dcf/calculate → 服务端DCF完整计算
POST /api/workpapers/{wp_id}/i3/impairment/allocate → 减值分摊验证（先冲商誉再分摊）

纯函数与前端 useI3DcfEngine.ts 对等：
- calc_dcf_present_value: Σ(CF_i / (1+r)^(i+1))
- calc_terminal_value: FCF_n × (1+g) / (WACC-g)  (永续增长模型)
- calc_wacc: Ke×(E/V) + Kd×(1-T)×(D/V)
- calc_recoverable_amount: MAX(公允价值-处置费用, 使用价值DCF)
- calc_impairment_allocation: 先冲商誉再按比例分摊至资产组其他资产(CAS8)
- calc_goodwill_end_balance: 期初+新并购-减值（不摊销！）

Requirements: 5.1-5.5, 6.1-6.7
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

router = APIRouter(tags=["i3-dcf-engine"])


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：DCF引擎 + 减值分摊（与前端 useI3DcfEngine.ts 对等）
# ═══════════════════════════════════════════════════════════════════════════════


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


def calc_terminal_value(last_fcf: float, growth_rate: float, discount_rate: float) -> float:
    """终值（Gordon永续增长模型）= FCF_n × (1+g) / (WACC-g).

    当 discountRate <= growthRate 时返回 0（参数错误防护）。
    """
    if discount_rate <= growth_rate:
        return 0.0
    return last_fcf * (1 + growth_rate) / (discount_rate - growth_rate)


def calc_wacc(
    equity_ratio: float,
    debt_ratio: float,
    cost_of_equity: float,
    cost_of_debt: float,
    tax_rate: float,
) -> float:
    """加权平均资本成本 WACC = Ke×(E/V) + Kd×(1-T)×(D/V)."""
    return cost_of_equity * equity_ratio + cost_of_debt * (1 - tax_rate) * debt_ratio


def calc_recoverable_amount(fair_value_less_disposal: float, value_in_use: float) -> float:
    """可收回金额 = MAX(公允价值-处置费用, 使用价值DCF)."""
    return max(fair_value_less_disposal, value_in_use)


def calc_goodwill_end_balance(opening: float, new_acquisition: float, impairment: float) -> float:
    """商誉期末余额 = 期初 + 新并购(通常0) - 减值.

    商誉不摊销！仅通过新并购增加、减值测试减少。
    """
    return opening + new_acquisition - impairment


def calc_impairment_allocation(
    total_impairment: float,
    goodwill_amount: float,
    other_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    """减值分摊两步法（CAS8）：先冲商誉再按比例分摊至资产组其他资产.

    Args:
        total_impairment: 资产组总减值金额 = MAX(账面-可收回, 0)
        goodwill_amount: 分配至该CGU的商誉账面价值
        other_assets: [{"name": str, "bookValue": float}, ...]

    Returns:
        {
            "goodwill_impairment": float,  # 商誉承担的减值
            "remaining_impairment": float,  # 剩余待分摊
            "other_allocations": [{"name": str, "bookValue": float, "impairment": float}, ...],
            "total_allocated": float,
        }
    """
    if total_impairment <= 0:
        return {
            "goodwill_impairment": 0.0,
            "remaining_impairment": 0.0,
            "other_allocations": [
                {"name": a["name"], "bookValue": a["bookValue"], "impairment": 0.0}
                for a in other_assets
            ],
            "total_allocated": 0.0,
        }

    # Step 1: 先冲商誉（至零为止）
    goodwill_impairment = min(total_impairment, goodwill_amount)
    remaining = total_impairment - goodwill_impairment

    # Step 2: 剩余按账面比例分摊至其他资产
    other_allocations = []
    total_other_book = sum(a["bookValue"] for a in other_assets if a["bookValue"] > 0)

    for asset in other_assets:
        if remaining <= 0 or total_other_book <= 0:
            other_allocations.append({
                "name": asset["name"],
                "bookValue": asset["bookValue"],
                "impairment": 0.0,
            })
        else:
            ratio = asset["bookValue"] / total_other_book if asset["bookValue"] > 0 else 0.0
            asset_impairment = remaining * ratio
            # 单项资产减值不超过其账面价值
            asset_impairment = min(asset_impairment, asset["bookValue"])
            other_allocations.append({
                "name": asset["name"],
                "bookValue": asset["bookValue"],
                "impairment": round(asset_impairment, 2),
            })

    total_allocated = goodwill_impairment + sum(a["impairment"] for a in other_allocations)

    return {
        "goodwill_impairment": round(goodwill_impairment, 2),
        "remaining_impairment": round(remaining, 2),
        "other_allocations": other_allocations,
        "total_allocated": round(total_allocated, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 模型
# ═══════════════════════════════════════════════════════════════════════════════


class CguDcfInput(BaseModel):
    """单个CGU的DCF计算输入."""

    cgu_name: str = ""
    cash_flows: list[float] = Field(description="各期预测自由现金流(FCF)数组，通常5年")
    discount_rate: float = Field(gt=0, description="WACC折现率(如0.10表示10%)")
    growth_rate: float = Field(default=0.02, description="永续增长率(如0.02表示2%)")
    fair_value_less_disposal: float = Field(default=0, description="公允价值减处置费用")
    goodwill_book_value: float = Field(ge=0, default=0, description="分配至CGU的商誉账面价值")
    other_assets_book_value: float = Field(ge=0, default=0, description="CGU其他资产账面价值")
    total_cgu_book_value: float = Field(ge=0, default=0, description="CGU总账面(含商誉)")


class CguDcfResult(BaseModel):
    """单个CGU的DCF计算结果."""

    cgu_name: str = ""
    present_value: float
    terminal_value: float
    terminal_value_pv: float
    value_in_use: float
    fair_value_less_disposal: float
    recoverable_amount: float
    impairment_amount: float
    needs_impairment: bool
    sensitivity: dict[str, Any] = Field(default_factory=dict)


class DcfValidateRequest(BaseModel):
    """DCF验证请求：前端提交计算结果，后端验证."""

    cgus: list[CguDcfInput]
    include_sensitivity: bool = Field(default=True)


class DcfValidateResponse(BaseModel):
    """DCF验证响应."""

    results: list[CguDcfResult]
    total_impairment: float
    cgus_with_impairment: int
    summary: str


class OtherAssetInput(BaseModel):
    """资产组其他资产."""

    name: str
    bookValue: float = Field(ge=0)


class ImpairmentAllocateRequest(BaseModel):
    """减值分摊请求."""

    cgu_name: str = ""
    total_impairment: float = Field(ge=0, description="资产组总减值金额")
    goodwill_amount: float = Field(ge=0, description="商誉账面价值")
    other_assets: list[OtherAssetInput] = Field(description="其他资产列表")


class OtherAssetAllocation(BaseModel):
    """其他资产分摊结果."""

    name: str
    bookValue: float
    impairment: float


class ImpairmentAllocateResponse(BaseModel):
    """减值分摊响应."""

    cgu_name: str = ""
    goodwill_impairment: float
    remaining_impairment: float
    other_allocations: list[OtherAssetAllocation]
    total_allocated: float
    summary: str


class WaccInput(BaseModel):
    """WACC计算输入."""

    equity_ratio: float = Field(ge=0, le=1, description="权益比例 E/(E+D)")
    debt_ratio: float = Field(ge=0, le=1, description="债务比例 D/(E+D)")
    cost_of_equity: float = Field(gt=0, description="权益成本(Ke)")
    cost_of_debt: float = Field(gt=0, description="税前债务成本(Kd)")
    tax_rate: float = Field(ge=0, le=1, description="所得税率(T)")
    risk_free_rate: float = Field(default=0, description="无风险利率(参考)")
    equity_risk_premium: float = Field(default=0, description="权益风险溢价(参考)")
    beta: float = Field(default=0, description="Beta系数(参考)")


class WaccResult(BaseModel):
    """WACC计算结果."""

    wacc: float
    breakdown: dict[str, float]


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


def _calculate_single_cgu(inp: CguDcfInput, include_sensitivity: bool = True) -> CguDcfResult:
    """计算单个CGU的DCF可收回金额 + 减值金额."""
    # 现值
    pv = calc_dcf_present_value(inp.cash_flows, inp.discount_rate)

    # 终值（永续增长模型）
    tv = 0.0
    tv_pv = 0.0
    if inp.cash_flows:
        last_fcf = inp.cash_flows[-1]
        tv = calc_terminal_value(last_fcf, inp.growth_rate, inp.discount_rate)
        # 终值折现到当前
        n = len(inp.cash_flows)
        tv_pv = tv / ((1 + inp.discount_rate) ** n) if n > 0 else tv

    # 使用价值 = 预测期现值 + 终值现值
    value_in_use = pv + tv_pv

    # 可收回金额
    recoverable = calc_recoverable_amount(inp.fair_value_less_disposal, value_in_use)

    # 减值金额 = MAX(资产组账面 - 可收回, 0)
    total_book = inp.total_cgu_book_value or (inp.goodwill_book_value + inp.other_assets_book_value)
    impairment = max(total_book - recoverable, 0.0)

    # 敏感性分析
    sensitivity: dict[str, Any] = {}
    if include_sensitivity and inp.cash_flows:
        # 折现率 ±1%
        rate_up = inp.discount_rate + 0.01
        rate_down = max(inp.discount_rate - 0.01, 0.001)
        pv_up = calc_dcf_present_value(inp.cash_flows, rate_up)
        pv_down = calc_dcf_present_value(inp.cash_flows, rate_down)
        tv_up = calc_terminal_value(inp.cash_flows[-1], inp.growth_rate, rate_up)
        tv_down = calc_terminal_value(inp.cash_flows[-1], inp.growth_rate, rate_down)
        viu_up = pv_up + (tv_up / ((1 + rate_up) ** len(inp.cash_flows)) if tv_up else 0)
        viu_down = pv_down + (tv_down / ((1 + rate_down) ** len(inp.cash_flows)) if tv_down else 0)

        # 增长率 ±0.5%
        growth_up = inp.growth_rate + 0.005
        growth_down = inp.growth_rate - 0.005
        tv_g_up = calc_terminal_value(inp.cash_flows[-1], growth_up, inp.discount_rate)
        tv_g_down = calc_terminal_value(inp.cash_flows[-1], growth_down, inp.discount_rate)

        # 收入 ±10%（近似：现金流按比例调整）
        cf_up = [cf * 1.1 for cf in inp.cash_flows]
        cf_down = [cf * 0.9 for cf in inp.cash_flows]
        pv_rev_up = calc_dcf_present_value(cf_up, inp.discount_rate)
        pv_rev_down = calc_dcf_present_value(cf_down, inp.discount_rate)

        sensitivity = {
            "wacc_plus_1pct": {
                "rate": round(rate_up, 4),
                "value_in_use": round(viu_up, 2),
                "impairment": round(max(total_book - max(inp.fair_value_less_disposal, viu_up), 0), 2),
            },
            "wacc_minus_1pct": {
                "rate": round(rate_down, 4),
                "value_in_use": round(viu_down, 2),
                "impairment": round(max(total_book - max(inp.fair_value_less_disposal, viu_down), 0), 2),
            },
            "growth_plus_05pct": {
                "rate": round(growth_up, 4),
                "terminal_value": round(tv_g_up, 2),
            },
            "growth_minus_05pct": {
                "rate": round(growth_down, 4),
                "terminal_value": round(tv_g_down, 2),
            },
            "revenue_plus_10pct": {
                "present_value": round(pv_rev_up, 2),
            },
            "revenue_minus_10pct": {
                "present_value": round(pv_rev_down, 2),
            },
        }

    return CguDcfResult(
        cgu_name=inp.cgu_name,
        present_value=round(pv, 2),
        terminal_value=round(tv, 2),
        terminal_value_pv=round(tv_pv, 2),
        value_in_use=round(value_in_use, 2),
        fair_value_less_disposal=round(inp.fair_value_less_disposal, 2),
        recoverable_amount=round(recoverable, 2),
        impairment_amount=round(impairment, 2),
        needs_impairment=impairment > 0,
        sensitivity=sensitivity,
    )


@router.post(
    "/api/workpapers/{wp_id}/i3/dcf/validate",
    response_model=DcfValidateResponse,
)
async def i3_dcf_validate(
    wp_id: str,
    body: DcfValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DcfValidateResponse:
    """验证前端DCF计算结果.

    对每个CGU执行：
    1. 计算预测期FCF现值 PV=Σ(FCF_i/(1+WACC)^(i+1))
    2. 计算终值（永续增长模型）TV=FCF_n×(1+g)/(WACC-g) 并折现
    3. 使用价值 = PV + TV_PV
    4. 可收回金额 = MAX(公允-处置费, 使用价值)
    5. 减值金额 = MAX(资产组账面-可收回, 0)
    6. 敏感性分析（WACC±1%，增长率±0.5%，收入±10%）
    """
    if not body.cgus:
        raise HTTPException(400, "cgus 列表不能为空")

    results = [_calculate_single_cgu(inp, body.include_sensitivity) for inp in body.cgus]

    total_impairment = sum(r.impairment_amount for r in results)
    cgus_with_impairment = sum(1 for r in results if r.needs_impairment)

    summary = (
        f"共{len(results)}个CGU资产组DCF测试，"
        f"{'全部无需计提减值' if cgus_with_impairment == 0 else f'有{cgus_with_impairment}个需计提减值'}，"
        f"减值合计={total_impairment:,.2f}元"
    )

    return DcfValidateResponse(
        results=results,
        total_impairment=round(total_impairment, 2),
        cgus_with_impairment=cgus_with_impairment,
        summary=summary,
    )


@router.post(
    "/api/workpapers/{wp_id}/i3/dcf/calculate",
    response_model=DcfValidateResponse,
)
async def i3_dcf_calculate(
    wp_id: str,
    body: DcfValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DcfValidateResponse:
    """服务端DCF完整计算（与validate相同逻辑，语义区分用于首次计算场景）."""
    return await i3_dcf_validate(wp_id, body, db, current_user)


@router.post(
    "/api/workpapers/{wp_id}/i3/impairment/allocate",
    response_model=ImpairmentAllocateResponse,
)
async def i3_impairment_allocate(
    wp_id: str,
    body: ImpairmentAllocateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImpairmentAllocateResponse:
    """减值分摊验证：先冲商誉再按比例分摊至资产组其他资产.

    CAS8明确规定：
    Step 1: 先抵减分配至该CGU的商誉账面价值（至零为止）
    Step 2: 剩余减值按其他资产账面价值比例分摊（单项不超过其账面）
    商誉减值不可转回！
    """
    result = calc_impairment_allocation(
        total_impairment=body.total_impairment,
        goodwill_amount=body.goodwill_amount,
        other_assets=[{"name": a.name, "bookValue": a.bookValue} for a in body.other_assets],
    )

    other_allocs = [
        OtherAssetAllocation(name=a["name"], bookValue=a["bookValue"], impairment=a["impairment"])
        for a in result["other_allocations"]
    ]

    goodwill_impairment = result["goodwill_impairment"]
    total_allocated = result["total_allocated"]

    summary = (
        f"CGU「{body.cgu_name}」总减值{body.total_impairment:,.2f}元，"
        f"商誉承担{goodwill_impairment:,.2f}元"
        f"{'（商誉已冲至零）' if goodwill_impairment >= body.goodwill_amount else ''}，"
        f"其他资产分摊{result['remaining_impairment']:,.2f}元，"
        f"合计已分配{total_allocated:,.2f}元"
    )

    return ImpairmentAllocateResponse(
        cgu_name=body.cgu_name,
        goodwill_impairment=goodwill_impairment,
        remaining_impairment=result["remaining_impairment"],
        other_allocations=other_allocs,
        total_allocated=total_allocated,
        summary=summary,
    )
