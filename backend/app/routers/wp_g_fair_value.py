"""G 投资循环 — G-F4 公允价值测试 API（Level 1/2/3 三层级）

POST /api/projects/{project_id}/workpapers/{wp_id}/g/fair-value-test

输入：level(1/2/3) + instrument_type + face_value + Level 对应参数
输出：fair_value + valuation_method + conclusion + is_llm_stub

公允价值层级（IFRS 13 / CAS 39）：
- Level 1: 活跃市场报价（市场价格 × 数量）
- Level 2: 可观察输入（利率曲线 + 信用利差 + 波动率，简化为面值×(1 - credit_spread)×波动率系数）
- Level 3: 不可观察输入（DCF 折现模型）
  pv = Σ(cf_i / (1+r)^(i+1)) + terminal_value / (1+r)^n

当前 Level 1/2 公式准确；Level 3 DCF 公式正确但 LLM 辅助参数建议待 wp_ai_service 升级
（is_llm_stub = not settings.WP_AI_SERVICE_ENABLED）。

对应 spec：workpaper-g-investment-cycle G-F4 / ADR-G3
对应 task：Sprint 2 Task 2.5
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/g",
    tags=["wp-g-fair-value"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class FairValueTestRequest(BaseModel):
    """公允价值测试请求（Level 1/2/3）"""

    level: Literal[1, 2, 3] = Field(..., description="公允价值层级（1=市场报价 / 2=可观察输入 / 3=DCF 不可观察输入）")
    instrument_type: str = Field(..., min_length=1, description="金融工具类型（如 交易性金融资产/债权投资/其他权益工具投资）")
    face_value: Decimal = Field(..., gt=0, description="面值/数量（元或单位数）")

    # Level 1 参数
    market_price: Decimal | None = Field(None, ge=0, description="Level 1：市场报价（元/单位）")
    price_date: str | None = Field(None, description="Level 1：报价日期（ISO 日期字符串）")

    # Level 2 参数
    interest_rate_curve: list[Decimal] | None = Field(
        None,
        description="Level 2：利率曲线（各期间利率列表，0~1）",
    )
    credit_spread: Decimal | None = Field(
        None,
        ge=0,
        lt=1,
        description="Level 2：信用利差（0~1）",
    )
    volatility: Decimal | None = Field(
        None,
        ge=0,
        description="Level 2：波动率（0~+∞，作为调整系数）",
    )

    # Level 3 参数（DCF）
    cash_flow_projections: list[Decimal] | None = Field(
        None,
        description="Level 3：现金流预测（各期间现金流列表）",
    )
    discount_rate: Decimal | None = Field(
        None,
        description="Level 3：折现率（0~1，如 0.10 = 10%）",
    )
    terminal_value: Decimal | None = Field(
        None,
        ge=0,
        description="Level 3：终值（第 N 年末残余价值，可选默认 0）",
    )

    # 写回
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.fair_value_tests[sheet]",
    )


class FairValueTestResponse(BaseModel):
    """公允价值测试响应"""

    level: int
    instrument_type: str
    face_value: str
    fair_value: str
    valuation_method: str
    conclusion: str
    dcf_details: list[dict] | None = None
    is_llm_stub: bool
    applied_to_sheet: str | None = None
    # K-4 解释链字段（task 4.2 / ADR-6）
    reasoning: str | None = None
    references: list[dict] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    confidence: float = 0.0


def _build_g_fair_value_reasoning(
    payload: "FairValueTestRequest",
    fair_value: Decimal,
    valuation_method: str,
    is_llm_stub: bool,
) -> tuple[str | None, list[dict], list[str], float]:
    """G 公允价值测试推理链（task 4.2）"""
    from app.services.llm_service import build_reasoning_chain

    level = payload.level
    parts = [
        f"基于公允价值层级 Level {level} 对 '{payload.instrument_type}' 进行估值，"
        f"采用 {valuation_method}",
    ]
    if level == 1:
        parts.append(
            f"，按市场报价 × 数量计算公允价值 {fair_value} 元。"
        )
    elif level == 2:
        parts.append(
            f"，结合利率曲线/信用利差/波动率调整后公允价值 {fair_value} 元。"
        )
    else:
        parts.append(
            f"，DCF 折现现金流后公允价值 {fair_value} 元。"
        )
    if is_llm_stub:
        parts.append("（LLM 暂未启用，已降级为规则结果）")
    reasoning = "".join(parts)

    references = [
        {"type": "IFRS", "code": "IFRS 13", "section": "Fair Value Measurement"},
        {"type": "CAS", "code": "CAS 39", "section": "公允价值计量"},
    ]
    if level == 3:
        references.append(
            {"type": "ISA", "code": "ISA 540", "section": "审计会计估计"}
        )

    sources = [f"WP:G:{payload.instrument_type}.面值"]
    if level == 1 and payload.market_price is not None:
        sources.append(f"WP:G:{payload.instrument_type}.市场报价")
    elif level == 2:
        if payload.interest_rate_curve:
            sources.append(f"WP:G:{payload.instrument_type}.利率曲线")
        if payload.credit_spread is not None:
            sources.append(f"WP:G:{payload.instrument_type}.信用利差")
    elif level == 3:
        if payload.cash_flow_projections:
            sources.append(f"WP:G:{payload.instrument_type}.现金流预测")
        if payload.discount_rate is not None:
            sources.append(f"WP:G:{payload.instrument_type}.折现率")

    # 不同 level 的置信度差异
    base_conf = {1: 0.85, 2: 0.75, 3: 0.7}.get(level, 0.7)
    return build_reasoning_chain(
        reasoning=reasoning,
        references=references,
        data_sources=sources,
        is_llm_stub=is_llm_stub,
        base_confidence=base_conf,
    )


# ─── Calculation Helpers ──────────────────────────────────────────────────────


def _quantize(value: Decimal) -> Decimal:
    """保留 2 位小数（四舍五入）"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _validate_inputs(payload: FairValueTestRequest) -> None:
    """按 level 校验必填字段，缺失返回 422；数值越界返回 400。"""
    if payload.face_value > Decimal("1e15"):
        raise HTTPException(400, "面值超出合理范围（不能超过 1e15）")

    if payload.level == 1:
        if payload.market_price is None:
            raise HTTPException(422, "Level 1 必须提供 market_price（市场报价）")
        if payload.price_date is None:
            raise HTTPException(422, "Level 1 必须提供 price_date（报价日期）")
        if payload.market_price < 0:
            raise HTTPException(400, "市场报价不能为负数")
    elif payload.level == 2:
        if payload.interest_rate_curve is None or len(payload.interest_rate_curve) == 0:
            raise HTTPException(422, "Level 2 必须提供 interest_rate_curve（利率曲线，至少 1 期）")
        if payload.credit_spread is None:
            raise HTTPException(422, "Level 2 必须提供 credit_spread（信用利差）")
        if payload.volatility is None:
            raise HTTPException(422, "Level 2 必须提供 volatility（波动率）")
        for r in payload.interest_rate_curve:
            if r < 0 or r >= 1:
                raise HTTPException(400, "利率曲线各期间利率应在 0~100% 之间")
    elif payload.level == 3:
        if payload.cash_flow_projections is None or len(payload.cash_flow_projections) == 0:
            raise HTTPException(422, "Level 3 必须提供 cash_flow_projections（现金流预测，至少 1 期）")
        if payload.discount_rate is None:
            raise HTTPException(422, "Level 3 必须提供 discount_rate（折现率）")
        if payload.discount_rate <= 0 or payload.discount_rate >= 1:
            raise HTTPException(400, "折现率应在 0~100% 之间")


def _calc_level_1_fv(face_value: Decimal, market_price: Decimal) -> Decimal:
    """Level 1：活跃市场报价 × 数量（公允价值 = 市场单价 × 数量/面值单位）。"""
    return _quantize(face_value * market_price)


def _calc_level_2_fv(
    face_value: Decimal,
    interest_rate_curve: list[Decimal],
    credit_spread: Decimal,
    volatility: Decimal,
) -> Decimal:
    """Level 2：可观察输入估值（简化模型）。

    估值思路（业务可观察输入近似）：
    - 平均无风险利率 = avg(interest_rate_curve)
    - 调整因子 = 1 - credit_spread + volatility * 平均利率
    - 公允价值 = face_value × 调整因子（下限 0）

    注：这是审计辅助场景的简化模型，真实定价需用债券/期权专属公式（如 Hull-White / Black-Scholes）。
    """
    n = len(interest_rate_curve)
    avg_rate = sum(interest_rate_curve, Decimal("0")) / Decimal(str(n))
    adjustment = Decimal("1") - credit_spread + volatility * avg_rate
    if adjustment < 0:
        adjustment = Decimal("0")
    return _quantize(face_value * adjustment)


def _calc_level_3_fv(
    cash_flows: list[Decimal],
    discount_rate: Decimal,
    terminal_value: Decimal,
) -> tuple[Decimal, list[dict]]:
    """Level 3：DCF 折现模型（现金流现值 + 终值现值）

    pv = Σ(cf_i / (1+r)^(i+1)) + terminal_value / (1+r)^n

    Returns:
        (npv, details) where details is per-period breakdown
    """
    details: list[dict] = []
    npv = Decimal("0")
    n = len(cash_flows)

    for i, cf in enumerate(cash_flows):
        period = i + 1
        discount_factor = (Decimal("1") + discount_rate) ** period
        pv = _quantize(cf / discount_factor)
        npv += pv
        details.append({
            "period": period,
            "cash_flow": str(cf),
            "discount_factor": str(_quantize(discount_factor)),
            "present_value": str(pv),
        })

    if terminal_value > 0:
        terminal_discount_factor = (Decimal("1") + discount_rate) ** n
        terminal_pv = _quantize(terminal_value / terminal_discount_factor)
        npv += terminal_pv
        details.append({
            "period": f"终值(P{n}末)",
            "cash_flow": str(terminal_value),
            "discount_factor": str(_quantize(terminal_discount_factor)),
            "present_value": str(terminal_pv),
        })

    return _quantize(npv), details


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/fair-value-test", response_model=FairValueTestResponse)
async def g_fair_value_test(
    project_id: str,
    wp_id: str,
    payload: FairValueTestRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> FairValueTestResponse:
    """G-F4 公允价值层级测试（Level 1/2/3）

    - Level 1: 活跃市场报价 × 数量
    - Level 2: 可观察输入（利率曲线/信用利差/波动率）简化估值
    - Level 3: DCF 折现模型（不可观察输入）

    is_llm_stub = not settings.WP_AI_SERVICE_ENABLED（Level 3 LLM 参数建议待真实接入）
    """
    try:
        UUID(project_id)
    except Exception as exc:
        raise HTTPException(400, "invalid project_id") from exc

    _validate_inputs(payload)

    is_llm_stub = not settings.WP_AI_SERVICE_ENABLED
    dcf_details: list[dict] | None = None

    if payload.level == 1:
        # Level 1: 活跃市场报价
        assert payload.market_price is not None  # _validate_inputs 已保证
        fair_value = _calc_level_1_fv(payload.face_value, payload.market_price)
        valuation_method = (
            f"Level 1（活跃市场报价）：market_price={payload.market_price} × "
            f"face_value={payload.face_value}（报价日 {payload.price_date}）"
        )
    elif payload.level == 2:
        assert payload.interest_rate_curve is not None
        assert payload.credit_spread is not None
        assert payload.volatility is not None
        fair_value = _calc_level_2_fv(
            payload.face_value,
            payload.interest_rate_curve,
            payload.credit_spread,
            payload.volatility,
        )
        n = len(payload.interest_rate_curve)
        avg_rate = sum(payload.interest_rate_curve, Decimal("0")) / Decimal(str(n))
        valuation_method = (
            f"Level 2（可观察输入）：avg_rate={_quantize(avg_rate)}，"
            f"credit_spread={payload.credit_spread}，volatility={payload.volatility}（{n} 期利率曲线）"
        )
    else:
        # Level 3: DCF
        assert payload.cash_flow_projections is not None
        assert payload.discount_rate is not None
        terminal_value = payload.terminal_value if payload.terminal_value is not None else Decimal("0")
        fair_value, dcf_details = _calc_level_3_fv(
            payload.cash_flow_projections,
            payload.discount_rate,
            terminal_value,
        )
        valuation_method = (
            f"Level 3（DCF 折现模型）：discount_rate={payload.discount_rate}，"
            f"{len(payload.cash_flow_projections)} 期现金流，terminal_value={terminal_value}"
        )

    # 结论：与面值比较的偏离度
    deviation_rate = (
        (fair_value - payload.face_value) / payload.face_value
        if payload.face_value > 0
        else Decimal("0")
    )
    if abs(deviation_rate) < Decimal("0.05"):
        conclusion_core = "公允价值与面值偏离 < 5%，估值合理"
    elif abs(deviation_rate) < Decimal("0.20"):
        conclusion_core = (
            f"公允价值与面值偏离 {_quantize(deviation_rate * 100)}%，需关注估值参数合理性"
        )
    else:
        conclusion_core = (
            f"公允价值与面值偏离 {_quantize(deviation_rate * 100)}%，存在重大偏差需进一步核查"
        )

    if is_llm_stub and payload.level == 3:
        conclusion = f"{conclusion_core}（Level 3 DCF 参数建议待 wp_ai_service 接入）"
    else:
        conclusion = conclusion_core

    applied_to_sheet = await _maybe_apply_fair_value_to_workpaper(
        db, wp_id, payload, fair_value, valuation_method, conclusion, dcf_details, is_llm_stub,
    )

    return FairValueTestResponse(
        level=payload.level,
        instrument_type=payload.instrument_type,
        face_value=str(payload.face_value),
        fair_value=str(fair_value),
        valuation_method=valuation_method,
        conclusion=conclusion,
        dcf_details=dcf_details,
        is_llm_stub=is_llm_stub,
        applied_to_sheet=applied_to_sheet,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_fair_value_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: FairValueTestRequest,
    fair_value: Decimal,
    valuation_method: str,
    conclusion: str,
    dcf_details: list[dict] | None,
    is_llm_stub: bool,
) -> str | None:
    """若 apply_to_sheet 给出则把公允价值测试结果写回 working_paper.parsed_data。

    数据结构（与 H-F12 impairment_analyses 对称）：
      parsed_data.fair_value_tests[sheet] = {
        "level": 1|2|3,
        "instrument_type": "...",
        "face_value": "...",
        "fair_value": "...",
        "valuation_method": "...",
        "conclusion": "...",
        "is_llm_stub": bool,
        "applied_at": ISO8601,
        "dcf_details": [...] | None,
        # 输入回显（按 level 不同）
        "inputs": { ... },
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

    # 输入回显（按 level 序列化）
    inputs: dict = {}
    if payload.level == 1:
        inputs = {
            "market_price": str(payload.market_price) if payload.market_price is not None else None,
            "price_date": payload.price_date,
        }
    elif payload.level == 2:
        inputs = {
            "interest_rate_curve": [str(r) for r in (payload.interest_rate_curve or [])],
            "credit_spread": str(payload.credit_spread) if payload.credit_spread is not None else None,
            "volatility": str(payload.volatility) if payload.volatility is not None else None,
        }
    else:
        inputs = {
            "cash_flow_projections": [str(cf) for cf in (payload.cash_flow_projections or [])],
            "discount_rate": str(payload.discount_rate) if payload.discount_rate is not None else None,
            "terminal_value": str(payload.terminal_value) if payload.terminal_value is not None else "0",
        }

    pd = wp.parsed_data or {}
    if not isinstance(pd, dict):
        pd = {}
    pd.setdefault("fair_value_tests", {})
    pd["fair_value_tests"][payload.apply_to_sheet] = {
        "level": payload.level,
        "instrument_type": payload.instrument_type,
        "face_value": str(payload.face_value),
        "fair_value": str(fair_value),
        "valuation_method": valuation_method,
        "conclusion": conclusion,
        "is_llm_stub": is_llm_stub,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "dcf_details": dcf_details,
        "inputs": inputs,
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    from app.services.wp_parsed_data_service import touch_after_parsed_data_commit

    await touch_after_parsed_data_commit(wp, source="wp_g_fair_value")
    return payload.apply_to_sheet
