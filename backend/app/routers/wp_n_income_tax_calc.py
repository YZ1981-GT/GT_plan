"""N 税金循环 — N-F7 所得税费用测算引擎 stub API

POST /api/projects/{project_id}/workpapers/{wp_id}/n5/income-tax-calc

税率调节表逻辑：
- 当期所得税 = (利润总额 + 永久性差异合计) × 法定税率
- 递延所得税 = -(递延资产变动 - 递延负债变动)
- 总所得税 = 当期 + 递延
- 有效税率 = 总所得税 / 利润总额（利润=0 时返回 0）

写回模式：parsed_data.income_tax_calcs[sheet] = {method, applied_at, data}
is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动。

对应 spec：workpaper-n-tax-cycle N-F7 / ADR-N4
"""

from __future__ import annotations

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
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/n5",
    tags=["wp-n-income-tax"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class IncomeTaxCalcRequest(BaseModel):
    """所得税费用测算请求"""

    profit_before_tax: float = Field(..., description="利润总额")
    statutory_rate: float = Field(0.25, description="法定税率（如 0.25 = 25%）")
    permanent_differences: dict[str, float] = Field(
        default_factory=dict, description="永久性差异 {description: amount}"
    )
    temporary_differences: dict[str, float] = Field(
        default_factory=dict, description="暂时性差异 {description: amount}"
    )
    deferred_tax_asset_change: float = Field(0.0, description="递延所得税资产变动")
    deferred_tax_liability_change: float = Field(0.0, description="递延所得税负债变动")
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.income_tax_calcs[sheet]",
    )


class ReconciliationItem(BaseModel):
    """税率调节表项"""

    item: str = Field(..., description="调节项名称")
    amount: float = Field(..., description="金额")
    rate_impact: float = Field(..., description="税率影响（占利润总额比例）")


class IncomeTaxCalcResponse(BaseModel):
    """所得税费用测算响应"""

    current_income_tax: float = Field(..., description="当期所得税费用")
    deferred_income_tax: float = Field(..., description="递延所得税费用")
    total_income_tax: float = Field(..., description="所得税费用合计")
    effective_rate: float = Field(..., description="有效税率")
    reconciliation_items: list[ReconciliationItem] = Field(
        ..., description="税率调节表明细"
    )
    is_llm_stub: bool = Field(..., description="是否为 stub 模式（待 wp_ai_service 接入）")
    applied_to_sheet: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _quantize(value: Decimal) -> Decimal:
    """保留 2 位小数（四舍五入）"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _validate_income_tax_request(payload: IncomeTaxCalcRequest) -> None:
    """校验输入参数，严重错误抛 HTTPException 400。"""
    if payload.statutory_rate > 1.0:
        raise HTTPException(400, "法定税率不能超过 100%（statutory_rate > 1.0）")


def _calc_income_tax(payload: IncomeTaxCalcRequest) -> dict[str, Any]:
    """计算所得税费用。返回包含所有响应字段的字典。

    逻辑：
    - current_income_tax = (profit_before_tax + sum(permanent_differences)) × statutory_rate
    - deferred_income_tax = -(deferred_tax_asset_change - deferred_tax_liability_change)
    - total_income_tax = current + deferred
    - effective_rate = total / profit_before_tax (if profit != 0, else 0)
    """
    profit = payload.profit_before_tax
    rate = payload.statutory_rate

    # 永久性差异合计
    perm_diff_total = sum(payload.permanent_differences.values()) if payload.permanent_differences else 0.0

    # 当期所得税
    current_income_tax = (profit + perm_diff_total) * rate

    # 递延所得税 = -(递延资产变动 - 递延负债变动)
    deferred_income_tax = -(payload.deferred_tax_asset_change - payload.deferred_tax_liability_change)

    # 总所得税
    total_income_tax = current_income_tax + deferred_income_tax

    # 有效税率
    if profit != 0:
        effective_rate = total_income_tax / profit
    else:
        effective_rate = 0.0

    # 构建调节表明细
    reconciliation_items = _build_reconciliation_items(payload, profit)

    return {
        "current_income_tax": round(current_income_tax, 2),
        "deferred_income_tax": round(deferred_income_tax, 2),
        "total_income_tax": round(total_income_tax, 2),
        "effective_rate": round(effective_rate, 6),
        "reconciliation_items": reconciliation_items,
    }


def _build_reconciliation_items(
    payload: IncomeTaxCalcRequest, profit: float
) -> list[dict[str, Any]]:
    """构建税率调节表明细项。

    每个永久性差异和暂时性差异各生成一条调节项。
    rate_impact = amount / profit_before_tax（profit=0 时为 0）。
    """
    items: list[dict[str, Any]] = []

    # 永久性差异
    for desc, amount in (payload.permanent_differences or {}).items():
        rate_impact = (amount * payload.statutory_rate / profit) if profit != 0 else 0.0
        items.append({
            "item": f"永久性差异：{desc}",
            "amount": round(amount * payload.statutory_rate, 2),
            "rate_impact": round(rate_impact, 6),
        })

    # 暂时性差异
    for desc, amount in (payload.temporary_differences or {}).items():
        rate_impact = (amount * payload.statutory_rate / profit) if profit != 0 else 0.0
        items.append({
            "item": f"暂时性差异：{desc}",
            "amount": round(amount * payload.statutory_rate, 2),
            "rate_impact": round(rate_impact, 6),
        })

    return items


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/income-tax-calc", response_model=IncomeTaxCalcResponse)
async def n_income_tax_calc(
    project_id: str,
    wp_id: str,
    payload: IncomeTaxCalcRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> IncomeTaxCalcResponse:
    """N-F7 所得税费用测算引擎：税率调节表 + 递延调整 + apply_to_sheet + RBAC。

    业务约束：
    - statutory_rate > 1.0 → 400 Bad Request
    - profit_before_tax = 0 → 返回 total=0（合法）
    - is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动
    - 支持 apply_to_sheet 写回 parsed_data.income_tax_calcs[sheet]
    """
    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    _validate_income_tax_request(payload)

    result = _calc_income_tax(payload)

    # is_llm_stub 由配置驱动
    is_llm_stub = not getattr(settings, "WP_AI_SERVICE_ENABLED", False)

    # 写回
    applied_to_sheet = None
    if payload.apply_to_sheet:
        applied_to_sheet = await _maybe_apply_income_tax_to_workpaper(
            db, wp_id, payload, result
        )

    return IncomeTaxCalcResponse(
        current_income_tax=result["current_income_tax"],
        deferred_income_tax=result["deferred_income_tax"],
        total_income_tax=result["total_income_tax"],
        effective_rate=result["effective_rate"],
        reconciliation_items=[
            ReconciliationItem(**item) for item in result["reconciliation_items"]
        ],
        is_llm_stub=is_llm_stub,
        applied_to_sheet=applied_to_sheet,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_income_tax_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: IncomeTaxCalcRequest,
    result: dict[str, Any],
) -> str | None:
    """若 apply_to_sheet 给出则把所得税测算结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.income_tax_calcs[sheet] = {
        "method": "income_tax_calculation",
        "applied_at": ISO8601,
        "data": {
          "profit_before_tax": ...,
          "statutory_rate": ...,
          "permanent_differences": {...},
          "temporary_differences": {...},
          "deferred_tax_asset_change": ...,
          "deferred_tax_liability_change": ...,
          "current_income_tax": ...,
          "deferred_income_tax": ...,
          "total_income_tax": ...,
          "effective_rate": ...,
          "reconciliation_items": [...]
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
    pd.setdefault("income_tax_calcs", {})
    pd["income_tax_calcs"][payload.apply_to_sheet] = {
        "method": "income_tax_calculation",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "profit_before_tax": payload.profit_before_tax,
            "statutory_rate": payload.statutory_rate,
            "permanent_differences": payload.permanent_differences,
            "temporary_differences": payload.temporary_differences,
            "deferred_tax_asset_change": payload.deferred_tax_asset_change,
            "deferred_tax_liability_change": payload.deferred_tax_liability_change,
            "current_income_tax": result["current_income_tax"],
            "deferred_income_tax": result["deferred_income_tax"],
            "total_income_tax": result["total_income_tax"],
            "effective_rate": result["effective_rate"],
            "reconciliation_items": result["reconciliation_items"],
        },
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
