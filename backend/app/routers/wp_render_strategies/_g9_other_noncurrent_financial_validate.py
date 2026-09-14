"""G9 其他非流动金融资产 — 公式校验 API.

POST /api/workpapers/{wp_id}/g9/validate-formulas
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_current_user
from app.models.core import User

from ._g9_other_noncurrent_financial_service import G9OtherNoncurrentFinancialService

router = APIRouter(tags=["g9-validate"])
_svc = G9OtherNoncurrentFinancialService()


class G9ValidateRequest(BaseModel):
    adjudication_rows: list[dict[str, Any]] = Field(default_factory=list)
    l3_rows: list[dict[str, Any]] = Field(default_factory=list)
    adjustment_debits: list[float] = Field(default_factory=list)
    adjustment_credits: list[float] = Field(default_factory=list)


class G9ValidateResponse(BaseModel):
    ok: bool
    errors: list[dict[str, Any]]


@router.post("/api/workpapers/{wp_id}/g9/validate-formulas", response_model=G9ValidateResponse)
async def validate_g9_formulas(
    wp_id: str,
    body: G9ValidateRequest,
    _user: User = Depends(get_current_user),
) -> G9ValidateResponse:
    errors: list[dict[str, Any]] = []

    for err in _svc.validate_adjudication_rows(body.adjudication_rows):
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

    return G9ValidateResponse(ok=len(errors) == 0, errors=errors)
