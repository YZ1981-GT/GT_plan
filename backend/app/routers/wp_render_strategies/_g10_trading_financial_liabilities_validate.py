"""G10 交易性金融负债 — 公式校验 API.

POST /api/workpapers/{wp_id}/g10/validate-formulas
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_current_user
from app.models.core import User

from ._g10_trading_financial_liabilities_service import G10TradingFinancialLiabilitiesService

router = APIRouter(tags=["g10-validate"])
_svc = G10TradingFinancialLiabilitiesService()


class G10ValidateRequest(BaseModel):
    adjudication_rows: list[dict[str, Any]] = Field(default_factory=list)
    three_part_rows: list[dict[str, Any]] = Field(default_factory=list)
    l3_rows: list[dict[str, Any]] = Field(default_factory=list)
    adjustment_debits: list[float] = Field(default_factory=list)
    adjustment_credits: list[float] = Field(default_factory=list)


class G10ValidateResponse(BaseModel):
    ok: bool
    errors: list[dict[str, Any]]


@router.post("/api/workpapers/{wp_id}/g10/validate-formulas", response_model=G10ValidateResponse)
async def validate_g10_formulas(
    wp_id: str,
    body: G10ValidateRequest,
    _user: User = Depends(get_current_user),
) -> G10ValidateResponse:
    errors: list[dict[str, Any]] = []

    adj_rows = body.adjudication_rows

    for err in _svc.validate_adjudication_rows(adj_rows):
        errors.append({
            "rowKey": err.row_key,
            "field": err.field,
            "message": err.message,
            "variance": err.variance,
        })

    for err in _svc.validate_three_part_rows(body.three_part_rows):
        errors.append({
            "rowKey": err.row_key,
            "field": err.field,
            "message": err.message,
            "variance": err.variance,
        })

    for err in _svc.validate_l3_rows(body.l3_rows):
        errors.append({
            "rowKey": err.row_key,
            "field": err.field,
            "message": err.message,
            "variance": err.variance,
        })

    for err in _svc.validate_adjustment_balance(body.adjustment_debits, body.adjustment_credits):
        errors.append({
            "rowKey": err.row_key,
            "field": err.field,
            "message": err.message,
            "variance": err.variance,
        })

    return G10ValidateResponse(ok=len(errors) == 0, errors=errors)
