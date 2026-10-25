"""share_change_events router — 动态股比变动事件 CRUD API。

spec: consol-node-key-isolation-and-shared-context 任务 9.1~9.2
设计: §十三（ADR-CNSC-009~010）

端点：
- GET    /{project_id}/{year}/events          列出事件
- POST   /{project_id}/{year}/events          手动创建事件
- POST   /{project_id}/{year}/events/from-g7  G7 幂等归一
- PUT    /{project_id}/{year}/events/{id}/approve  审批
- PUT    /{project_id}/{year}/events/{id}/revoke   撤回
- DELETE /{project_id}/{year}/events/{id}     删除 draft
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.core import User
from app.deps import require_project_access
from app.services import share_change_event_service as svc

router = APIRouter(
    prefix="/api/share-change-events",
    tags=["share-change-events"],
)


# ─── Request / Response schemas ──────────────────────────────────────────────


class ShareChangeEventCreate(BaseModel):
    company_code: str
    node_key: str | None = None
    effective_date: str | None = None
    sequence: int = 0
    before_ratio: float | None = None
    after_ratio: float | None = None
    change_type: str | None = None
    amount: float | None = None
    equity_adjustment: float | None = None
    detail: dict | None = None


class ShareChangeEventResponse(BaseModel):
    id: str
    project_id: str
    year: int
    company_code: str
    node_key: str | None
    effective_date: str | None
    sequence: int
    before_ratio: float | None
    after_ratio: float | None
    ratio_delta: float | None
    change_type: str | None
    amount: float | None
    equity_adjustment: float | None
    source_type: str | None
    source_row_id: str | None
    source_sheet_key: str | None
    review_status: str
    calculation_version: int
    detail: dict | None
    created_at: str | None
    updated_at: str | None


class G7UpsertRequest(BaseModel):
    suggestions: list[dict[str, Any]]


class G7UpsertResponse(BaseModel):
    created: int
    updated: int
    skipped: int


def _to_response(event: Any) -> ShareChangeEventResponse:
    return ShareChangeEventResponse(
        id=str(event.id),
        project_id=str(event.project_id),
        year=event.year,
        company_code=event.company_code,
        node_key=event.node_key,
        effective_date=str(event.effective_date) if event.effective_date else None,
        sequence=event.sequence,
        before_ratio=float(event.before_ratio) if event.before_ratio is not None else None,
        after_ratio=float(event.after_ratio) if event.after_ratio is not None else None,
        ratio_delta=float(event.ratio_delta) if event.ratio_delta is not None else None,
        change_type=event.change_type,
        amount=float(event.amount) if event.amount is not None else None,
        equity_adjustment=float(event.equity_adjustment) if event.equity_adjustment is not None else None,
        source_type=event.source_type,
        source_row_id=event.source_row_id,
        source_sheet_key=event.source_sheet_key,
        review_status=event.review_status,
        calculation_version=event.calculation_version,
        detail=event.detail,
        created_at=event.created_at.isoformat() if event.created_at else None,
        updated_at=event.updated_at.isoformat() if event.updated_at else None,
    )


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/{project_id}/{year}/events", response_model=list[ShareChangeEventResponse])
async def list_events(
    project_id: UUID,
    year: int,
    company_code: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """列出项目/年度的股比变动事件。"""
    events = await svc.list_events(db, project_id, year, company_code)
    return [_to_response(e) for e in events]


@router.post("/{project_id}/{year}/events", response_model=ShareChangeEventResponse)
async def create_event(
    project_id: UUID,
    year: int,
    body: ShareChangeEventCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """手动创建股比变动事件。"""
    from datetime import date as date_type

    effective_date = None
    if body.effective_date:
        try:
            effective_date = date_type.fromisoformat(body.effective_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="effective_date 格式无效，需 YYYY-MM-DD")

    event = await svc.create_event(
        db,
        project_id=project_id,
        year=year,
        company_code=body.company_code,
        node_key=body.node_key,
        effective_date=effective_date,
        sequence=body.sequence,
        before_ratio=Decimal(str(body.before_ratio)) if body.before_ratio is not None else None,
        after_ratio=Decimal(str(body.after_ratio)) if body.after_ratio is not None else None,
        change_type=body.change_type,
        amount=Decimal(str(body.amount)) if body.amount is not None else None,
        equity_adjustment=Decimal(str(body.equity_adjustment)) if body.equity_adjustment is not None else None,
        detail=body.detail,
        created_by=getattr(user, "id", None),
    )
    await db.commit()
    return _to_response(event)


@router.post("/{project_id}/{year}/events/from-g7", response_model=G7UpsertResponse)
async def upsert_from_g7(
    project_id: UUID,
    year: int,
    body: G7UpsertRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """将 G7-10 建议归一为事件并幂等 upsert。"""
    result = await svc.upsert_from_g7(
        db,
        project_id=project_id,
        year=year,
        suggestions=body.suggestions,
        created_by=getattr(user, "id", None),
    )
    await db.commit()
    return G7UpsertResponse(**result)


@router.put("/{project_id}/{year}/events/{event_id}/approve", response_model=ShareChangeEventResponse)
async def approve_event(
    project_id: UUID,
    year: int,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """审批事件（draft → approved）。"""
    try:
        event = await svc.approve_event(db, event_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    await db.commit()
    return _to_response(event)


@router.put("/{project_id}/{year}/events/{event_id}/revoke", response_model=ShareChangeEventResponse)
async def revoke_event(
    project_id: UUID,
    year: int,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """撤回事件（approved → revoked）。"""
    try:
        event = await svc.revoke_event(db, event_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    await db.commit()
    return _to_response(event)


@router.delete("/{project_id}/{year}/events/{event_id}")
async def delete_event(
    project_id: UUID,
    year: int,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """删除 draft 状态的事件。"""
    try:
        deleted = await svc.delete_event(db, event_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="事件不存在")
    await db.commit()
    return {"ok": True}
