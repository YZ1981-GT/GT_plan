"""合并抵消路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user
from app.core.database import get_db
from app.models.consolidation_models import EliminationEntryType, ReviewStatusEnum
from app.models.consolidation_schemas import (
    EliminationCreate,
    EliminationEntryResponse,
    EliminationEntryUpdate,
    EliminationReviewAction,
    EliminationSummary,
)
from app.services.elimination_service import (
    change_review_status,
    create_entry,
    delete_entry,
    get_entries,
    get_entry,
    get_summary,
    update_entry,
)

router = APIRouter(prefix="/api/consolidation/eliminations", tags=["合并抵消"])


@router.get("", response_model=list[EliminationEntryResponse])
async def list_eliminations(
    project_id: UUID,
    year: int | None = None,
    entry_type: EliminationEntryType | None = None,
    review_status: ReviewStatusEnum | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_entries(db, project_id, year, entry_type, review_status)


@router.post("", response_model=EliminationEntryResponse, status_code=201)
async def create_elimination(
    project_id: UUID,
    data: EliminationCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return await create_entry(db, project_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{entry_id}", response_model=EliminationEntryResponse)
async def get_elimination(
    entry_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    entry = await get_entry(db, entry_id, project_id)
    if not entry:
        raise HTTPException(status_code=404, detail="抵消分录不存在")
    return entry


@router.put("/{entry_id}", response_model=EliminationEntryResponse)
async def update_elimination(
    entry_id: UUID,
    project_id: UUID,
    data: EliminationEntryUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        entry = await update_entry(db, entry_id, project_id, data)
        if not entry:
            raise HTTPException(status_code=404, detail="抵消分录不存在")
        return entry
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{entry_id}", status_code=204)
async def delete_elimination(
    entry_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        if not await delete_entry(db, entry_id, project_id):
            raise HTTPException(status_code=404, detail="抵消分录不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{entry_id}/review", response_model=EliminationEntryResponse)
async def review_elimination(
    entry_id: UUID,
    project_id: UUID,
    action: EliminationReviewAction,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        entry = await change_review_status(db, entry_id, project_id, action, user.id)
        if not entry:
            raise HTTPException(status_code=404, detail="抵消分录不存在")
        return entry
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/summary/year", response_model=list[EliminationSummary])
async def elimination_summary(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_summary(db, project_id, year)
