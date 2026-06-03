"""F 采购存货循环 — F-F12 跌价准备 ECL 模型辅助 API

POST /api/projects/{project_id}/workpapers/{wp_id}/f2/impairment-analysis

输入：库龄分析 + 各产品成本/可变现净值
输出：LLM 分析跌价准备计提充分性（stub 返回结构化建议）

对应 spec：workpaper-f-purchase-inventory F-F12
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/f2",
    tags=["wp-f2-impairment"],
)


class ProductImpairmentItem(BaseModel):
    """单个产品的跌价分析输入"""

    product_name: str = Field(..., description="产品名称")
    cost: float = Field(..., ge=0, description="账面成本")
    nrv: float = Field(..., ge=0, description="可变现净值")
    aging_months: int = Field(0, ge=0, description="库龄月数")
    qty: float = Field(0, description="数量")


class ImpairmentAnalysisRequest(BaseModel):
    products: list[ProductImpairmentItem] = Field(..., description="产品级跌价输入清单")
    method: str = Field(
        "lower_of_cost_or_nrv",
        description="计提方法：lower_of_cost_or_nrv (默认) / specific_id / aging_based",
    )
    materiality_threshold: float = Field(50000.0, ge=0, description="重要性水平（元）")
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将分析结果写回 working_paper.parsed_data.impairment_analyses[sheet]",
    )


class ImpairmentSuggestion(BaseModel):
    product_name: str
    book_cost: str
    nrv: str
    suggested_provision: str
    rationale: str
    risk_level: str  # high / medium / low


class ImpairmentAnalysisResponse(BaseModel):
    method: str
    total_products: int
    suggestions: list[ImpairmentSuggestion]
    summary: str
    total_suggested_provision: str
    is_llm_stub: bool = True
    applied_to_sheet: str | None = None  # 写回时返回 sheet 名，否则 None


@router.post("/impairment-analysis", response_model=ImpairmentAnalysisResponse)
async def f2_impairment_analysis(
    project_id: str,
    wp_id: str,
    payload: ImpairmentAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> ImpairmentAnalysisResponse:
    """F-F12 跌价准备分析（LLM stub 实现）

    规则（成本与可变现净值孰低法）：
    - cost > nrv → 应计提 = cost - nrv
    - 库龄 > 24 个月 → 风险等级 high
    - 12-24 个月 → medium
    - < 12 个月 → low
    - 应计提 < materiality_threshold → 提示"低于重要性"
    """
    valid_methods = {"lower_of_cost_or_nrv", "specific_id", "aging_based"}
    if payload.method not in valid_methods:
        raise HTTPException(400, f"method must be one of {sorted(valid_methods)}")

    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    suggestions: list[ImpairmentSuggestion] = []
    total_provision = Decimal("0")

    for p in payload.products:
        cost = Decimal(str(p.cost))
        nrv = Decimal(str(p.nrv))
        provision = cost - nrv if cost > nrv else Decimal("0")

        # 库龄风险等级
        if p.aging_months >= 24:
            risk = "high"
        elif p.aging_months >= 12:
            risk = "medium"
        else:
            risk = "low"

        # rationale 说明
        if provision <= 0:
            rationale = (
                f"成本 ¥{cost:,.2f} ≤ 可变现净值 ¥{nrv:,.2f}，无需计提跌价。"
                + (f" 库龄 {p.aging_months} 月，建议关注。" if risk == "high" else "")
            )
        else:
            rationale = (
                f"成本 ¥{cost:,.2f} > 可变现净值 ¥{nrv:,.2f}，"
                f"按孰低原则应计提跌价 ¥{provision:,.2f}。"
                f"库龄 {p.aging_months} 月（{risk} 风险）。"
            )

        # 重要性提示
        if 0 < provision < Decimal(str(payload.materiality_threshold)):
            rationale += f" 注：拟计提金额低于重要性水平 ¥{payload.materiality_threshold:,.0f}。"

        total_provision += provision
        suggestions.append(
            ImpairmentSuggestion(
                product_name=p.product_name,
                book_cost=str(cost),
                nrv=str(nrv),
                suggested_provision=str(provision),
                rationale=rationale,
                risk_level=risk,
            )
        )

    high_risk_count = sum(1 for s in suggestions if s.risk_level == "high")
    summary = (
        f"共分析 {len(suggestions)} 个产品，建议合计计提跌价准备 ¥{total_provision:,.2f}。"
        f"其中高风险（库龄 ≥ 24 月）{high_risk_count} 个产品。"
        f"方法：{payload.method}（LLM stub 返回，实际部署需接入 wp_ai_service）。"
    )

    return ImpairmentAnalysisResponse(
        method=payload.method,
        total_products=len(suggestions),
        suggestions=suggestions,
        summary=summary,
        total_suggested_provision=str(total_provision),
        is_llm_stub=True,
        applied_to_sheet=await _maybe_apply_impairment_to_workpaper(
            db, wp_id, payload, suggestions, total_provision, summary
        ),
    )


async def _maybe_apply_impairment_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: ImpairmentAnalysisRequest,
    suggestions: list[ImpairmentSuggestion],
    total_provision: Decimal,
    summary: str,
) -> str | None:
    """若 apply_to_sheet 给出则把跌价分析结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.impairment_analyses[sheet] = {
        "method": "lower_of_cost_or_nrv",
        "applied_at": ISO8601,
        "total_provision": "...",
        "summary": "...",
        "suggestions": [...]
      }
    """
    if not payload.apply_to_sheet:
        return None

    from datetime import datetime, timezone

    import sqlalchemy as sa
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
        "method": payload.method,
        "materiality_threshold": payload.materiality_threshold,
        "total_provision": str(total_provision),
        "summary": summary,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "suggestions": [s.model_dump() for s in suggestions],
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    from app.services.wp_parsed_data_service import touch_after_parsed_data_commit

    await touch_after_parsed_data_commit(wp, source="wp_f2_impairment")
    return payload.apply_to_sheet
