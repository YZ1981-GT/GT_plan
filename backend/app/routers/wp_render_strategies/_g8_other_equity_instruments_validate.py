"""G8 其他权益工具投资 — 公式校验 API.

POST /api/workpapers/{wp_id}/g8/validate-formulas
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_current_user
from app.models.core import User

from ._g8_other_equity_instruments_service import G8OtherEquityInstrumentsService

router = APIRouter(tags=["g8-validate"])
_svc = G8OtherEquityInstrumentsService()


class G8ValidateRequest(BaseModel):
    adjudication_rows: list[dict[str, Any]] = Field(default_factory=list)
    detail_rows: list[dict[str, Any]] = Field(default_factory=list)
    fair_value_rows: list[dict[str, Any]] = Field(default_factory=list)
    adjustment_debits: list[float] = Field(default_factory=list)
    adjustment_credits: list[float] = Field(default_factory=list)


class G8ValidateResponse(BaseModel):
    ok: bool
    errors: list[dict[str, Any]]


@router.post("/api/workpapers/{wp_id}/g8/validate-formulas", response_model=G8ValidateResponse)
async def validate_g8_formulas(
    wp_id: str,
    body: G8ValidateRequest,
    _user: User = Depends(get_current_user),
) -> G8ValidateResponse:
    errors: list[dict[str, Any]] = []

    for err in _svc.validate_adjudication_rows(body.adjudication_rows):
        errors.append({
            "rowKey": err.row_key,
            "field": err.field,
            "message": err.message,
            "variance": err.variance,
        })

    for err in _svc.validate_detail_rows(body.detail_rows):
        errors.append({
            "rowKey": err.row_key,
            "field": err.field,
            "message": err.message,
            "variance": err.variance,
        })

    for err in _svc.validate_fair_value_rows(body.fair_value_rows):
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

    return G8ValidateResponse(ok=len(errors) == 0, errors=errors)
