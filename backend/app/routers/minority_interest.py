"""少数股东权益路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user
from app.core.database import get_db
from app.models.consolidation_schemas import MinorityInterestResult
from app.services.minority_interest_service import (
    calculate_mi,
    create_or_update_mi,
    delete_mi,
    get_mi,
    get_mi_list,
)

router = APIRouter(prefix="/api/consolidation/minority-interest", tags=["少数股东权益"])


@router.get("", response_model=list)
async def list_mi(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_mi_list(db, project_id, year)


@router.post("/calculate")
async def calculate_mi_route(
    subsidiary_net_assets: float | None = None,
    subsidiary_net_profit: float | None = None,
    minority_share_ratio: float | None = None,
    opening_equity: float | None = None,
) -> MinorityInterestResult:
    """计算少数股东权益（仅计算，不存储）"""
    return await calculate_mi(subsidiary_net_assets, subsidiary_net_profit, minority_share_ratio, opening_equity)


@router.post("", status_code=201)
async def create_or_update_mi_route(
    project_id: UUID,
    year: int,
    company_code: str,
    data: MinorityInterestResult,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await create_or_update_mi(db, project_id, year, company_code, data)


@router.delete("/{mi_id}", status_code=204)
async def delete_mi_route(
    mi_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await delete_mi(db, mi_id, project_id):
        raise HTTPException(status_code=404, detail="少数股东权益记录不存在")
