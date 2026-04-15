"""外币折算路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import sync_db, get_current_user
from app.models.consolidation_schemas import ForexRates, TranslationWorksheet
from app.services.forex_service import create_or_update_forex, delete_forex, get_forex, get_forex_list

router = APIRouter(prefix="/api/consolidation/forex", tags=["外币折算"])


@router.get("", response_model=list)
def list_forex(
    project_id: UUID,
    year: int,
    db: Session = Depends(sync_db),
    user=Depends(get_current_user),
):
    return get_forex_list(db, project_id, year)


@router.post("")
def create_or_update_forex_route(
    project_id: UUID,
    company_code: str,
    year: int,
    functional_currency: str,
    reporting_currency: str = "CNY",
    rates: ForexRates | None = None,
    worksheet: TranslationWorksheet | None = None,
    db: Session = Depends(sync_db),
    user=Depends(get_current_user),
):
    return create_or_update_forex(db, project_id, company_code, year, functional_currency, reporting_currency, rates, worksheet)


@router.delete("/{forex_id}", status_code=204)
def delete_forex_route(
    forex_id: UUID,
    project_id: UUID,
    db: Session = Depends(sync_db),
    user=Depends(get_current_user),
):
    if not delete_forex(db, forex_id, project_id):
        raise HTTPException(status_code=404, detail="外币折算记录不存在")
