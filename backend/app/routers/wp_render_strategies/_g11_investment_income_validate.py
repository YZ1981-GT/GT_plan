"""G11 投资收益 — 公式校验与审定保存 API.

POST /api/workpapers/{wp_id}/g11/validate-formulas
POST /api/workpapers/{wp_id}/g11/save-adjudication
"""

from __future__ import annotations

import json
from typing import Any

from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.routers.wp_render_strategies._cycle_import_export_common import upsert_json_rows

from ._g11_investment_income_service import G11InvestmentIncomeService

router = APIRouter(tags=["g11-validate"])
_svc = G11InvestmentIncomeService()


async def _upsert_adj_store(db: AsyncSession, wp_id: str, store: dict[str, Any]) -> None:
    proj = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id AND is_deleted = false"),
        {"wp_id": wp_id},
    )
    project_id = proj.scalar_one_or_none()
    if not project_id:
        raise HTTPException(404, "底稿不存在")
    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at, created_at)
            VALUES (:id, :project_id, :wp_id, 'G11-adj-rows', :payload, NOW(), NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :payload, updated_at = NOW()
        """),
        {
            "id": str(uuid4()),
            "project_id": str(project_id),
            "wp_id": wp_id,
            "payload": json.dumps(store, ensure_ascii=False),
        },
    )


async def _upsert_conclusion(
    db: AsyncSession, wp_id: str, project_id: str, item_id: str, conclusion: str | None,
) -> None:
    if conclusion is None:
        return
    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, updated_at, created_at)
            VALUES (:id, :project_id, :wp_id, :item_id, :conclusion, NOW(), NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET conclusion = :conclusion, updated_at = NOW()
        """),
        {
            "id": str(uuid4()),
            "project_id": project_id,
            "wp_id": wp_id,
            "item_id": item_id,
            "conclusion": conclusion,
        },
    )


class G11ValidateRequest(BaseModel):
    adjudication_rows: list[dict[str, Any]] = Field(default_factory=list)
    detail_rows: list[dict[str, Any]] = Field(default_factory=list)
    return_rate_rows: list[dict[str, Any]] = Field(default_factory=list)
    adjustment_debits: list[float] = Field(default_factory=list)
    adjustment_credits: list[float] = Field(default_factory=list)


class G11ValidateResponse(BaseModel):
    ok: bool
    errors: list[dict[str, Any]]


class G11SaveAdjudicationRequest(BaseModel):
    row_store: dict[str, Any] = Field(default_factory=dict)
    adjudicated_amount: float | None = None
    audit_note: str = ""
    audit_conclusion: str = ""


class G11SaveAdjudicationResponse(BaseModel):
    ok: bool
    adjudicated_amount: float
    validation_errors: list[dict[str, Any]]


async def _load_remark_json(db: AsyncSession, wp_id: str, item_id: str) -> Any:
    result = await db.execute(
        sa.text("SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"),
        {"wp_id": wp_id, "iid": item_id},
    )
    row = result.fetchone()
    if not row or not row.remark:
        return None
    try:
        return json.loads(row.remark)
    except (json.JSONDecodeError, TypeError):
        return None


def _flatten_adj_rows(store: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, fields in store.items():
        if not isinstance(fields, dict):
            continue
        rows.append({
            "rowKey": key,
            "currentUnadjusted": fields.get("currentUnadjusted", 0),
            "currentAdjustment": fields.get("currentAdjustment", 0),
            "currentAudited": _svc.calc_adjusted(
                fields.get("currentUnadjusted", 0),
                fields.get("currentAdjustment", 0),
            ),
            "priorUnadjusted": fields.get("priorUnadjusted", 0),
            "priorAdjustment": fields.get("priorAdjustment", 0),
            "priorAudited": _svc.calc_adjusted(
                fields.get("priorUnadjusted", 0),
                fields.get("priorAdjustment", 0),
            ),
        })
    return rows


@router.post("/api/workpapers/{wp_id}/g11/validate-formulas", response_model=G11ValidateResponse)
async def validate_g11_formulas(
    wp_id: str,
    body: G11ValidateRequest,
    _user: User = Depends(get_current_user),
) -> G11ValidateResponse:
    errors: list[dict[str, Any]] = []

    for err in _svc.validate_adjudication_rows(body.adjudication_rows):
        errors.append({"rowKey": err.row_key, "field": err.field, "message": err.message, "variance": err.variance})

    for err in _svc.validate_detail_reconciliation(body.adjudication_rows, body.detail_rows):
        errors.append({"rowKey": err.row_key, "field": err.field, "message": err.message, "variance": err.variance})

    for err in _svc.validate_return_rate_rows(body.return_rate_rows):
        errors.append({"rowKey": err.row_key, "field": err.field, "message": err.message, "variance": err.variance})

    if body.adjustment_debits or body.adjustment_credits:
        if not _svc.is_debit_credit_balanced(body.adjustment_debits, body.adjustment_credits):
            errors.append({
                "rowKey": "G11-3",
                "field": "balance",
                "message": "调整分录借贷不平衡",
                "variance": sum(body.adjustment_debits) - sum(body.adjustment_credits),
            })

    return G11ValidateResponse(ok=len(errors) == 0, errors=errors)


@router.post("/api/workpapers/{wp_id}/g11/save-adjudication", response_model=G11SaveAdjudicationResponse)
async def save_g11_adjudication(
    wp_id: str,
    body: G11SaveAdjudicationRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G11SaveAdjudicationResponse:
    store = body.row_store or {}
    flat = _flatten_adj_rows(store)
    validation_errors = [
        {"rowKey": e.row_key, "field": e.field, "message": e.message, "variance": e.variance}
        for e in _svc.validate_adjudication_rows(flat)
    ]
    if validation_errors:
        raise HTTPException(status_code=422, detail={"errors": validation_errors})

    await _upsert_adj_store(db, wp_id, store)

    adjudicated = body.adjudicated_amount
    if adjudicated is None:
        adjudicated = sum(r.get("currentAudited", 0) for r in flat if r.get("rowKey") != "total")

    proj = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id AND is_deleted = false"),
        {"wp_id": wp_id},
    )
    project_id = str(proj.scalar_one_or_none())
    await _upsert_conclusion(db, wp_id, project_id, "G11-1-adjudicated-amount", str(adjudicated))
    await _upsert_conclusion(db, wp_id, project_id, "G11-adj-note", body.audit_note or None)
    await _upsert_conclusion(db, wp_id, project_id, "G11-adj-conclusion", body.audit_conclusion or None)
    await db.commit()

    return G11SaveAdjudicationResponse(
        ok=True,
        adjudicated_amount=float(adjudicated or 0),
        validation_errors=[],
    )
