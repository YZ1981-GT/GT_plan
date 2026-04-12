"""商誉计算路由"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.deps import get_current_user
from app.core.database import get_db
from app.models.consolidation_schemas import GoodwillInput, GoodwillCalcResponse
from app.services.goodwill_service import (
    create_goodwill,
    delete_goodwill,
    get_goodwill,
    get_goodwill_list,
    record_impairment,
    update_goodwill,
)

router = APIRouter(prefix="/api/consolidation/goodwill", tags=["商誉计算"])


@router.get("", response_model=list[GoodwillCalcResponse])
async def list_goodwill(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_goodwill_list(db, project_id, year)


@router.post("", response_model=GoodwillCalcResponse, status_code=201)
async def create_goodwill_route(
    project_id: UUID,
    data: GoodwillInput,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await create_goodwill(db, project_id, data)


@router.get("/{goodwill_id}", response_model=GoodwillCalcResponse)
async def get_goodwill_route(
    goodwill_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    goodwill = await get_goodwill(db, goodwill_id)
    if not goodwill:
        raise HTTPException(status_code=404, detail="商誉记录不存在")
    return goodwill


@router.put("/{goodwill_id}", response_model=GoodwillCalcResponse)
async def update_goodwill_route(
    goodwill_id: UUID,
    project_id: UUID,
    data: GoodwillInput,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    goodwill = await update_goodwill(db, goodwill_id, project_id, data)
    if not goodwill:
        raise HTTPException(status_code=404, detail="商誉记录不存在")
    return goodwill


@router.post("/{goodwill_id}/impairment", response_model=GoodwillCalcResponse)
async def record_impairment_route(
    goodwill_id: UUID,
    project_id: UUID,
    impairment_amount: float,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    goodwill = await record_impairment(db, goodwill_id, project_id, impairment_amount)
    if not goodwill:
        raise HTTPException(status_code=404, detail="商誉记录不存在")
    return goodwill


@router.delete("/{goodwill_id}", status_code=204)
async def delete_goodwill_route(
    goodwill_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await delete_goodwill(db, goodwill_id, project_id):
        raise HTTPException(status_code=404, detail="商誉记录不存在")
    return None
