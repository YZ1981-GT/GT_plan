"""合并试算表路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user
from app.core.database import get_db
from app.models.consolidation_schemas import ConsolTrialResponse, ConsolTrialUpdate, ConsistencyCheckResult
from app.services.consol_trial_service import (
    check_trial_consistency,
    delete_trial,
    get_trial_balance,
    get_trial_row,
    recalculate_trial,
    upsert_trial_row,
)

router = APIRouter(prefix="/api/consolidation/trial", tags=["合并试算表"])


@router.get("", response_model=list[ConsolTrialResponse])
async def get_trial_balance_list(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_trial_balance(db, project_id, year)


@router.put("/{trial_id}", response_model=ConsolTrialResponse)
async def update_trial_row(
    trial_id: UUID,
    project_id: UUID,
    data: ConsolTrialUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    trial = await get_trial_row(db, trial_id, project_id)
    if not trial:
        raise HTTPException(status_code=404, detail="试算表行不存在")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(trial, key, value)

    db.commit()
    db.refresh(trial)
    return trial


@router.post("/recalculate", response_model=list[ConsolTrialResponse])
async def trigger_recalculate(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """触发全量重算"""
    return await recalculate_trial(db, project_id, year)


@router.get("/consistency-check", response_model=ConsistencyCheckResult)
async def check_consistency(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """一致性校验"""
    return ConsistencyCheckResult(**check_trial_consistency(db, project_id, year))


@router.delete("/{trial_id}", status_code=204)
async def delete_trial_row(
    trial_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await delete_trial(db, trial_id, project_id):
        raise HTTPException(status_code=404, detail="试算表行不存在")
