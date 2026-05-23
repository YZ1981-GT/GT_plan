"""H 固定资产循环 — H-F12 减值 DCF 模型 LLM 辅助 API

POST /api/projects/{project_id}/workpapers/{wp_id}/h1/impairment-analysis

输入：资产组 ID / 账面价值 / 5 年现金流预测 / 折现率 / 终值
输出：可收回金额 = max(公允价值−处置费用, 未来现金流现值) + 与账面价值比较

当前为 stub 实现（DCF 公式正确但 LLM 真实接入待 wp_ai_service 升级）。

对应 spec：workpaper-h-fixed-assets-cycle H-F12
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/h1",
    tags=["wp-h-impairment"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class ImpairmentAnalysisRequest(BaseModel):
    """减值分析请求"""

    asset_group_id: str = Field(..., description="资产组 ID（如 CGU-001）")
    book_value: Decimal = Field(..., gt=0, description="账面价值（元）")
    cash_flows: list[Decimal] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="未来 N 年（通常 5 年）预测现金流（元）",
    )
    discount_rate: Decimal = Field(
        ...,
        gt=0,
        lt=1,
        description="折现率（0~1，如 0.10 = 10%）",
    )
    terminal_value: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description="终值（第 N 年末残余价值，默认 0）",
    )
    fair_value_less_costs: Decimal | None = Field(
        None,
        ge=0,
        description="公允价值减去处置费用（若已知）；若不提供则仅用 DCF",
    )
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.impairment_analyses[sheet]",
    )


class ImpairmentAnalysisResponse(BaseModel):
    """减值分析响应"""

    asset_group_id: str
    book_value: str
    present_value_of_cash_flows: str
    fair_value_less_costs: str | None
    recoverable_amount: str
    impairment_loss: str
    is_impaired: bool
    dcf_details: list[dict]
    summary: str
    is_llm_stub: bool = True
    applied_to_sheet: str | None = None
    # K-4 解释链字段（task 4.2 / ADR-6）
    reasoning: str | None = None
    references: list[dict] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    confidence: float = 0.0


# ─── DCF Calculation ──────────────────────────────────────────────────────────


def _quantize(value: Decimal) -> Decimal:
    """保留 2 位小数（四舍五入）"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calc_dcf(
    cash_flows: list[Decimal],
    discount_rate: Decimal,
    terminal_value: Decimal,
) -> tuple[Decimal, list[dict]]:
    """计算未来现金流现值（DCF）

    NPV = Σ(CF_t / (1+r)^t) + terminal_value / (1+r)^n

    Returns:
        (npv, details) where details is a list of per-year breakdown
    """
    details: list[dict] = []
    npv = Decimal("0")
    n = len(cash_flows)

    for t, cf in enumerate(cash_flows, start=1):
        discount_factor = (Decimal("1") + discount_rate) ** t
        pv = _quantize(cf / discount_factor)
        npv += pv
        details.append({
            "year": t,
            "cash_flow": str(cf),
            "discount_factor": str(_quantize(discount_factor)),
            "present_value": str(pv),
        })

    # 终值折现到第 n 年末
    if terminal_value > 0:
        terminal_discount_factor = (Decimal("1") + discount_rate) ** n
        terminal_pv = _quantize(terminal_value / terminal_discount_factor)
        npv += terminal_pv
        details.append({
            "year": f"终值(Y{n}末)",
            "cash_flow": str(terminal_value),
            "discount_factor": str(_quantize(terminal_discount_factor)),
            "present_value": str(terminal_pv),
        })

    return _quantize(npv), details


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/impairment-analysis", response_model=ImpairmentAnalysisResponse)
async def h1_impairment_analysis(
    project_id: str,
    wp_id: str,
    payload: ImpairmentAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> ImpairmentAnalysisResponse:
    """H-F12 减值 DCF 模型辅助分析（LLM stub 实现）

    可收回金额 = max(公允价值−处置费用, 未来现金流现值)
    减值损失 = max(0, 账面价值 − 可收回金额)
    """
    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    # 参数校验
    if payload.book_value > Decimal("1e15"):
        raise HTTPException(400, "账面价值超出合理范围（不能超过 1e15）")
    if payload.discount_rate <= 0 or payload.discount_rate >= 1:
        raise HTTPException(400, "折现率必须在 (0, 1) 范围内")
    if len(payload.cash_flows) == 0:
        raise HTTPException(400, "至少需要 1 年的现金流预测")

    # DCF 计算
    pv_cash_flows, dcf_details = _calc_dcf(
        payload.cash_flows,
        payload.discount_rate,
        payload.terminal_value,
    )

    # 可收回金额 = max(公允价值−处置费用, 未来现金流现值)
    fair_value_less_costs = payload.fair_value_less_costs
    if fair_value_less_costs is not None:
        recoverable_amount = max(fair_value_less_costs, pv_cash_flows)
    else:
        recoverable_amount = pv_cash_flows

    recoverable_amount = _quantize(recoverable_amount)

    # 减值损失 = max(0, 账面价值 − 可收回金额)
    impairment_loss = _quantize(max(Decimal("0"), payload.book_value - recoverable_amount))
    is_impaired = impairment_loss > 0

    # 生成摘要
    summary = (
        f"资产组 {payload.asset_group_id}：账面价值 ¥{payload.book_value:,.2f}，"
        f"未来现金流现值 ¥{pv_cash_flows:,.2f}（折现率 {payload.discount_rate * 100:.1f}%，{len(payload.cash_flows)} 年）"
    )
    if fair_value_less_costs is not None:
        summary += f"，公允价值减处置费用 ¥{fair_value_less_costs:,.2f}"
    summary += f"。可收回金额 ¥{recoverable_amount:,.2f}。"
    if is_impaired:
        summary += f"应计提减值 ¥{impairment_loss:,.2f}。"
    else:
        summary += "无需计提减值。"
    summary += "（LLM stub 返回，实际部署需接入 wp_ai_service）"

    # 写回
    applied_to_sheet = await _maybe_apply_impairment_to_workpaper(
        db, wp_id, payload, pv_cash_flows, recoverable_amount, impairment_loss,
        is_impaired, dcf_details, summary,
    )

    return ImpairmentAnalysisResponse(
        asset_group_id=payload.asset_group_id,
        book_value=str(payload.book_value),
        present_value_of_cash_flows=str(pv_cash_flows),
        fair_value_less_costs=str(fair_value_less_costs) if fair_value_less_costs is not None else None,
        recoverable_amount=str(recoverable_amount),
        impairment_loss=str(impairment_loss),
        is_impaired=is_impaired,
        dcf_details=dcf_details,
        summary=summary,
        is_llm_stub=True,
        applied_to_sheet=applied_to_sheet,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_impairment_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: ImpairmentAnalysisRequest,
    pv_cash_flows: Decimal,
    recoverable_amount: Decimal,
    impairment_loss: Decimal,
    is_impaired: bool,
    dcf_details: list[dict],
    summary: str,
) -> str | None:
    """若 apply_to_sheet 给出则把减值分析结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.impairment_analyses[sheet] = {
        "asset_group_id": "CGU-001",
        "book_value": "...",
        "discount_rate": "...",
        "cash_flows": [...],
        "terminal_value": "...",
        "present_value_of_cash_flows": "...",
        "recoverable_amount": "...",
        "impairment_loss": "...",
        "is_impaired": true/false,
        "applied_at": ISO8601,
        "summary": "...",
        "dcf_details": [...]
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
    pd.setdefault("impairment_analyses", {})
    pd["impairment_analyses"][payload.apply_to_sheet] = {
        "asset_group_id": payload.asset_group_id,
        "book_value": str(payload.book_value),
        "discount_rate": str(payload.discount_rate),
        "cash_flows": [str(cf) for cf in payload.cash_flows],
        "terminal_value": str(payload.terminal_value),
        "fair_value_less_costs": str(payload.fair_value_less_costs) if payload.fair_value_less_costs is not None else None,
        "present_value_of_cash_flows": str(pv_cash_flows),
        "recoverable_amount": str(recoverable_amount),
        "impairment_loss": str(impairment_loss),
        "is_impaired": is_impaired,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "dcf_details": dcf_details,
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
