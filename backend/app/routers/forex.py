"""外币折算路由"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.deps import get_current_user
from app.core.database import get_db
from app.models.consolidation_schemas import ForexRates, TranslationWorksheet
from app.services.forex_service import (
    create_or_update_forex,
    delete_forex,
    get_forex,
    get_forex_list,
)

router = APIRouter(prefix="/api/consolidation/forex", tags=["外币折算"])


@router.get("", response_model=list)
async def list_forex(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_forex_list(db, project_id, year)


@router.post("")
async def create_or_update_forex_route(
    project_id: UUID,
    company_code: str,
    year: int,
    functional_currency: str,
    reporting_currency: str = "CNY",
    rates: ForexRates | None = None,
    worksheet: TranslationWorksheet | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await create_or_update_forex(db, project_id, company_code, year, functional_currency, reporting_currency, rates, worksheet)


@router.get("/{forex_id}")
async def get_forex_route(
    forex_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    forex = await get_forex(db, forex_id)
    if not forex:
        raise HTTPException(status_code=404, detail="外币折算记录不存在")
    return forex


@router.delete("/{forex_id}", status_code=204)
async def delete_forex_route(
    forex_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await delete_forex(db, forex_id, project_id):
        raise HTTPException(status_code=404, detail="外币折算记录不存在")
    return None
