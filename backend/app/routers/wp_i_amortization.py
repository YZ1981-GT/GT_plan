"""I 无形资产循环 — I-F2 / Sprint 3 Task 3.1 摊销自动测算引擎 API

POST /api/projects/{project_id}/workpapers/{wp_id}/i1/amortization-calc
POST /api/projects/{project_id}/workpapers/{wp_id}/i4/amortization-calc

支持 2 种摊销方法（H-F11 折旧引擎子集）：
- straight_line（直线法 / 剩余年限法）
- units_of_production（工作量法）

纯算法 endpoint，无 DB IO（除 apply_to_sheet 写回时 PATCH parsed_data）。

对应 spec：workpaper-i-intangible-assets-cycle I-F2 / ADR-I5
对应 task：Sprint 3 Task 3.1
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

# 复用 H-F11 折旧引擎的计算原语（直线法 + 工作量法 + quantize）
from app.routers.wp_h_depreciation import (
    _calc_straight_line,
    _calc_units_of_production,
    _quantize,
)

# ─── Routers (I1 + I4 共用 schema / 计算逻辑) ─────────────────────────────────

router_i1 = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/i1",
    tags=["wp-i-amortization"],
)

router_i4 = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/i4",
    tags=["wp-i-amortization"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class AmortizationCalcRequest(BaseModel):
    """摊销计算请求（I-F2 / ADR-I5）"""

    method: Literal["straight_line", "units_of_production"]
    original_cost: Decimal = Field(..., description="原值")
    residual_rate: Decimal = Field(..., ge=0, le=1, description="残值率（0~1）")
    useful_life_months: int = Field(..., gt=0, description="使用年限（月数）")
    start_month: int = Field(..., ge=1, le=12, description="起始月份（1~12）")
    already_amortized_months: int = Field(0, ge=0, description="已计提月数")
    # 工作量法专用
    total_units: Decimal | None = Field(None, description="总工作量（工作量法专用）")
    current_period_units: Decimal | None = Field(None, description="当期工作量（工作量法专用）")
    # 写回
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.amortization_calcs[sheet]",
    )


class AmortizationCalcResponse(BaseModel):
    """摊销计算响应"""

    method: str
    monthly_schedule: list[dict]
    total_amortization: Decimal
    remaining_book_value: Decimal
    applied_to_sheet: str | None = None


# ─── Validation Helpers ───────────────────────────────────────────────────────


def _validate_request(payload: AmortizationCalcRequest) -> None:
    """校验输入参数范围，超出合理范围返回 400。

    与 H-F11 折旧引擎对称（保留同样的边界值），仅"已计提月数"语义改为摊销。
    """
    if payload.original_cost > Decimal("1e15"):
        raise HTTPException(400, "原值超出合理范围（不能超过 1e15）")
    if payload.original_cost < 0:
        raise HTTPException(400, "原值不能为负数")
    if payload.useful_life_months > 600:
        raise HTTPException(400, "使用年限超出合理范围（不能超过 600 个月）")
    if payload.already_amortized_months > payload.useful_life_months:
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


# ─── Core engine (共用直线法 + 工作量法) ──────────────────────────────────────


def _run_amortization(payload: AmortizationCalcRequest) -> tuple[list[dict], Decimal, Decimal]:
    """根据 method 执行摊销计算，返回 (schedule, total_amortization, remaining_book_value)。

    传入 term='amortization' 让 H-F11 引擎直接输出 'amortization' 字段名（统一术语）。
    """
    residual = _quantize(payload.original_cost * payload.residual_rate)

    if payload.method == "straight_line":
        schedule = _calc_straight_line(
            payload.original_cost,
            residual,
            payload.useful_life_months,
            payload.already_amortized_months,
            term="amortization",
        )
    elif payload.method == "units_of_production":
        # _calc_units_of_production 入参顺序: (original, residual, total, current, already_months)
        schedule = _calc_units_of_production(
            payload.original_cost,
            residual,
            payload.total_units,  # type: ignore[arg-type]
            payload.current_period_units,  # type: ignore[arg-type]
            payload.already_amortized_months,
            term="amortization",
        )
    else:
        raise HTTPException(400, f"不支持的摊销方法: {payload.method}")

    total_amortization = schedule[-1]["accumulated"] if schedule else Decimal("0")
    remaining_book_value = payload.original_cost - residual - total_amortization
    if remaining_book_value < 0:
        remaining_book_value = Decimal("0")
    return schedule, total_amortization, remaining_book_value


async def _execute(
    project_id: str,
    wp_id: str,
    payload: AmortizationCalcRequest,
    db: AsyncSession,
    *,
    wp_section: str,
) -> AmortizationCalcResponse:
    """共享入口：参数校验 + 计算 + 写回。

    wp_section: "I1" / "I4" — 仅用于写回 namespace 调试可读性，不影响计算。
    """
    _validate_request(payload)

    try:
        UUID(project_id)
    except Exception as exc:
        raise HTTPException(400, "invalid project_id") from exc

    schedule, total_amortization, remaining_book_value = _run_amortization(payload)

    applied_to_sheet = await _maybe_apply_amortization_to_workpaper(
        db,
        wp_id,
        payload,
        schedule,
        total_amortization,
        remaining_book_value,
        wp_section=wp_section,
    )

    return AmortizationCalcResponse(
        method=payload.method,
        monthly_schedule=schedule,
        total_amortization=total_amortization,
        remaining_book_value=remaining_book_value,
        applied_to_sheet=applied_to_sheet,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router_i1.post("/amortization-calc", response_model=AmortizationCalcResponse)
async def i1_amortization_calc(
    project_id: str,
    wp_id: str,
    payload: AmortizationCalcRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> AmortizationCalcResponse:
    """I1 无形资产摊销自动测算（剩余年限法 / 工作量法）

    - straight_line: 直线法（含剩余年限法语义，每月摊销严格相等）
    - units_of_production: 工作量法（按当期工作量）

    写回 namespace: working_paper.parsed_data.amortization_calcs[sheet]
    """
    return await _execute(project_id, wp_id, payload, db, wp_section="I1")


@router_i4.post("/amortization-calc", response_model=AmortizationCalcResponse)
async def i4_amortization_calc(
    project_id: str,
    wp_id: str,
    payload: AmortizationCalcRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> AmortizationCalcResponse:
    """I4 长期待摊费用摊销自动测算（直线法 / 工作量法）

    - straight_line: 直线法（每月摊销严格相等）
    - units_of_production: 工作量法（按当期工作量）

    写回 namespace: working_paper.parsed_data.amortization_calcs[sheet]
    """
    return await _execute(project_id, wp_id, payload, db, wp_section="I4")


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_amortization_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: AmortizationCalcRequest,
    schedule: list[dict],
    total_amortization: Decimal,
    remaining_book_value: Decimal,
    *,
    wp_section: str,
) -> str | None:
    """若 apply_to_sheet 给出则把摊销计算结果写回 working_paper.parsed_data。

    数据结构（与 H-F11 depreciation_calcs 对称）：
      parsed_data.amortization_calcs[sheet] = {
        "section": "I1" | "I4",
        "method": "straight_line" | "units_of_production",
        "original_cost": "...",
        "residual_rate": "...",
        "useful_life_months": ...,
        "applied_at": ISO8601,
        "total_amortization": "...",
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
    pd.setdefault("amortization_calcs", {})
    pd["amortization_calcs"][payload.apply_to_sheet] = {
        "section": wp_section,
        "method": payload.method,
        "original_cost": str(payload.original_cost),
        "residual_rate": str(payload.residual_rate),
        "useful_life_months": payload.useful_life_months,
        "start_month": payload.start_month,
        "already_amortized_months": payload.already_amortized_months,
        "total_amortization": str(total_amortization),
        "remaining_book_value": str(remaining_book_value),
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "schedule": [
            {
                "month": s["month"],
                "amortization": str(s["amortization"]),
                "accumulated": str(s["accumulated"]),
            }
            for s in schedule
        ],
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
