"""M 权益循环 — M-F7 权益变动表引擎 stub API

POST /api/projects/{project_id}/workpapers/{wp_id}/m6/equity-movement

6 列变动汇总（实收资本/资本公积/盈余公积/未分配利润/其他综合收益/其他权益工具）
根据 opening_balances + 本期变动项计算 closing_balances。

写回模式：parsed_data.equity_movement[sheet] = {method, applied_at, data}
is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动。

对应 spec：workpaper-m-equity-cycle M-F7 / ADR-M4
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
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/m6",
    tags=["wp-m-equity-movement"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class OpeningBalances(BaseModel):
    """权益各科目期初余额"""

    paid_in_capital: Decimal = Field(..., description="实收资本（股本）")
    capital_reserve: Decimal = Field(..., description="资本公积")
    surplus_reserve: Decimal = Field(..., description="盈余公积")
    retained_earnings: Decimal = Field(..., description="未分配利润")
    oci: Decimal = Field(Decimal("0"), description="其他综合收益")
    other_equity_instruments: Decimal = Field(Decimal("0"), description="其他权益工具")


class EquityMovementRequest(BaseModel):
    """权益变动表计算请求"""

    opening_balances: OpeningBalances = Field(..., description="期初余额（6 列）")
    net_profit: Decimal = Field(..., description="本期净利润")
    dividends: Decimal = Field(Decimal("0"), ge=0, description="本期分配股利")
    surplus_reserve: Decimal = Field(Decimal("0"), ge=0, description="本期提取盈余公积")
    capital_reserve_changes: Decimal = Field(Decimal("0"), description="资本公积本期变动（正=增加）")
    oci_changes: Decimal = Field(Decimal("0"), description="其他综合收益本期变动")
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.equity_movement[sheet]",
    )


class ClosingBalances(BaseModel):
    """权益各科目期末余额"""

    paid_in_capital: Decimal
    capital_reserve: Decimal
    surplus_reserve: Decimal
    retained_earnings: Decimal
    oci: Decimal
    other_equity_instruments: Decimal


class MovementSummary(BaseModel):
    """6 列变动汇总"""

    paid_in_capital_change: Decimal = Field(..., description="实收资本变动")
    capital_reserve_change: Decimal = Field(..., description="资本公积变动")
    surplus_reserve_change: Decimal = Field(..., description="盈余公积变动")
    retained_earnings_change: Decimal = Field(..., description="未分配利润变动")
    oci_change: Decimal = Field(..., description="其他综合收益变动")
    other_equity_instruments_change: Decimal = Field(..., description="其他权益工具变动")


class EquityMovementResponse(BaseModel):
    """权益变动表计算响应"""

    closing_balances: ClosingBalances
    movement_summary: MovementSummary
    is_llm_stub: bool = Field(..., description="是否为 stub 模式（待 wp_ai_service 接入）")
    applied_to_sheet: str | None = None
    applied_at: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _quantize(value: Decimal) -> Decimal:
    """保留 2 位小数（四舍五入）"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _validate_equity_request(payload: EquityMovementRequest) -> None:
    """校验输入参数。opening_balances 为空（全 0 且无意义）时不报错，
    但如果 opening_balances 本身缺失则由 pydantic 校验。
    """
    # opening_balances 是 required field，pydantic 已校验非 None
    # 额外业务校验：如果所有期初余额都是 0 且净利润也是 0，允许但无意义
    pass


def _calc_equity_movement(payload: EquityMovementRequest) -> dict[str, Any]:
    """计算权益变动。

    逻辑：
    - 实收资本：本期无变动（当前 stub 不处理增资/减资）
    - 资本公积：+= capital_reserve_changes
    - 盈余公积：+= surplus_reserve（从未分配利润提取）
    - 未分配利润：+= net_profit - dividends - surplus_reserve
    - 其他综合收益：+= oci_changes
    - 其他权益工具：本期无变动（当前 stub）
    """
    ob = payload.opening_balances

    # 各科目变动
    paid_in_capital_change = Decimal("0")  # stub: 增资/减资待 LLM 接入
    capital_reserve_change = payload.capital_reserve_changes
    surplus_reserve_change = payload.surplus_reserve
    retained_earnings_change = payload.net_profit - payload.dividends - payload.surplus_reserve
    oci_change = payload.oci_changes
    other_equity_instruments_change = Decimal("0")  # stub

    # 期末余额
    closing = ClosingBalances(
        paid_in_capital=_quantize(ob.paid_in_capital + paid_in_capital_change),
        capital_reserve=_quantize(ob.capital_reserve + capital_reserve_change),
        surplus_reserve=_quantize(ob.surplus_reserve + surplus_reserve_change),
        retained_earnings=_quantize(ob.retained_earnings + retained_earnings_change),
        oci=_quantize(ob.oci + oci_change),
        other_equity_instruments=_quantize(ob.other_equity_instruments + other_equity_instruments_change),
    )

    # 变动汇总
    summary = MovementSummary(
        paid_in_capital_change=_quantize(paid_in_capital_change),
        capital_reserve_change=_quantize(capital_reserve_change),
        surplus_reserve_change=_quantize(surplus_reserve_change),
        retained_earnings_change=_quantize(retained_earnings_change),
        oci_change=_quantize(oci_change),
        other_equity_instruments_change=_quantize(other_equity_instruments_change),
    )

    return {"closing_balances": closing, "movement_summary": summary}


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/equity-movement", response_model=EquityMovementResponse)
async def m_equity_movement(
    project_id: str,
    wp_id: str,
    payload: EquityMovementRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> EquityMovementResponse:
    """M-F7 权益变动表引擎：6 列变动汇总 + apply_to_sheet + RBAC。

    业务约束：
    - opening_balances 必填（pydantic 校验）
    - is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动
    - 支持 apply_to_sheet 写回 parsed_data.equity_movement[sheet]
    """
    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    _validate_equity_request(payload)

    result = _calc_equity_movement(payload)

    # is_llm_stub 由配置驱动
    is_llm_stub = not getattr(settings, "WP_AI_SERVICE_ENABLED", False)

    # 写回
    applied_to_sheet = None
    applied_at = None
    if payload.apply_to_sheet:
        applied_to_sheet = await _maybe_apply_equity_to_workpaper(
            db, wp_id, payload, result
        )
        if applied_to_sheet:
            applied_at = datetime.now(timezone.utc).isoformat()

    return EquityMovementResponse(
        closing_balances=result["closing_balances"],
        movement_summary=result["movement_summary"],
        is_llm_stub=is_llm_stub,
        applied_to_sheet=applied_to_sheet,
        applied_at=applied_at,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_equity_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: EquityMovementRequest,
    result: dict[str, Any],
) -> str | None:
    """若 apply_to_sheet 给出则把权益变动结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.equity_movement[sheet] = {
        "method": "equity_movement_calculation",
        "applied_at": ISO8601,
        "data": {
          "opening_balances": {...},
          "net_profit": "...",
          "dividends": "...",
          "surplus_reserve": "...",
          "capital_reserve_changes": "...",
          "oci_changes": "...",
          "closing_balances": {...},
          "movement_summary": {...}
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
    pd.setdefault("equity_movement", {})

    closing = result["closing_balances"]
    summary = result["movement_summary"]

    pd["equity_movement"][payload.apply_to_sheet] = {
        "method": "equity_movement_calculation",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "opening_balances": {
                "paid_in_capital": str(payload.opening_balances.paid_in_capital),
                "capital_reserve": str(payload.opening_balances.capital_reserve),
                "surplus_reserve": str(payload.opening_balances.surplus_reserve),
                "retained_earnings": str(payload.opening_balances.retained_earnings),
                "oci": str(payload.opening_balances.oci),
                "other_equity_instruments": str(payload.opening_balances.other_equity_instruments),
            },
            "net_profit": str(payload.net_profit),
            "dividends": str(payload.dividends),
            "surplus_reserve": str(payload.surplus_reserve),
            "capital_reserve_changes": str(payload.capital_reserve_changes),
            "oci_changes": str(payload.oci_changes),
            "closing_balances": {
                "paid_in_capital": str(closing.paid_in_capital),
                "capital_reserve": str(closing.capital_reserve),
                "surplus_reserve": str(closing.surplus_reserve),
                "retained_earnings": str(closing.retained_earnings),
                "oci": str(closing.oci),
                "other_equity_instruments": str(closing.other_equity_instruments),
            },
            "movement_summary": {
                "paid_in_capital_change": str(summary.paid_in_capital_change),
                "capital_reserve_change": str(summary.capital_reserve_change),
                "surplus_reserve_change": str(summary.surplus_reserve_change),
                "retained_earnings_change": str(summary.retained_earnings_change),
                "oci_change": str(summary.oci_change),
                "other_equity_instruments_change": str(summary.other_equity_instruments_change),
            },
        },
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
