"""内部交易路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user
from app.core.database import get_db
from app.models.consolidation_schemas import (
    InternalTradeCreate,
    InternalTradeResponse,
    InternalTradeUpdate,
    InternalArApCreate,
    InternalArApResponse,
    InternalArApUpdate,
    TransactionMatrix,
)
from app.services.internal_trade_service import (
    create_arap,
    create_trade,
    delete_arap,
    delete_trade,
    get_arap,
    get_arap_list,
    get_trade,
    get_trades,
    get_transaction_matrix,
    update_arap,
    update_trade,
)

router = APIRouter(prefix="/api/consolidation/internal-trade", tags=["内部交易"])


# --- 内部交易 ---
@router.get("/trades", response_model=list[InternalTradeResponse])
async def list_trades(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_trades(db, project_id, year)


@router.post("/trades", response_model=InternalTradeResponse, status_code=201)
async def create_trade_route(
    project_id: UUID,
    data: InternalTradeCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await create_trade(db, project_id, data)


@router.put("/trades/{trade_id}", response_model=InternalTradeResponse)
async def update_trade_route(
    trade_id: UUID,
    project_id: UUID,
    data: InternalTradeUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    trade = await update_trade(db, trade_id, project_id, data)
    if not trade:
        raise HTTPException(status_code=404, detail="内部交易不存在")
    return trade


@router.delete("/trades/{trade_id}", status_code=204)
async def delete_trade_route(
    trade_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await delete_trade(db, trade_id, project_id):
        raise HTTPException(status_code=404, detail="内部交易不存在")


# --- 内部往来 ---
@router.get("/arap", response_model=list[InternalArApResponse])
async def list_arap(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_arap_list(db, project_id, year)


@router.post("/arap", response_model=InternalArApResponse, status_code=201)
async def create_arap_route(
    project_id: UUID,
    data: InternalArApCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await create_arap(db, project_id, data)


@router.put("/arap/{arap_id}", response_model=InternalArApResponse)
async def update_arap_route(
    arap_id: UUID,
    project_id: UUID,
    data: InternalArApUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    arap = await update_arap(db, arap_id, project_id, data)
    if not arap:
        raise HTTPException(status_code=404, detail="内部往来不存在")
    return arap


@router.delete("/arap/{arap_id}", status_code=204)
async def delete_arap_route(
    arap_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await delete_arap(db, arap_id, project_id):
        raise HTTPException(status_code=404, detail="内部往来不存在")


# --- 交易矩阵 ---
@router.get("/matrix", response_model=TransactionMatrix)
async def get_matrix(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_transaction_matrix(db, project_id, year)
