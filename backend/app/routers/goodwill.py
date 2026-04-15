"""商誉计算路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import sync_db, get_current_user
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
def list_goodwill(
    project_id: UUID,
    year: int,
    db: Session = Depends(sync_db),
    user=Depends(get_current_user),
):
    return get_goodwill_list(db, project_id, year)


@router.post("", response_model=GoodwillCalcResponse, status_code=201)
def create_goodwill_route(
    project_id: UUID,
    data: GoodwillInput,
    db: Session = Depends(sync_db),
    user=Depends(get_current_user),
):
    return create_goodwill(db, project_id, data)


@router.put("/{goodwill_id}", response_model=GoodwillCalcResponse)
def update_goodwill_route(
    goodwill_id: UUID,
    project_id: UUID,
    data: GoodwillInput,
    db: Session = Depends(sync_db),
    user=Depends(get_current_user),
):
    goodwill = update_goodwill(db, goodwill_id, project_id, data)
    if not goodwill:
        raise HTTPException(status_code=404, detail="商誉记录不存在")
    return goodwill


@router.post("/{goodwill_id}/impairment", response_model=GoodwillCalcResponse)
def record_impairment_route(
    goodwill_id: UUID,
    project_id: UUID,
    impairment_amount: float,
    db: Session = Depends(sync_db),
    user=Depends(get_current_user),
):
    goodwill = record_impairment(db, goodwill_id, project_id, impairment_amount)
    if not goodwill:
        raise HTTPException(status_code=404, detail="商誉记录不存在")
    return goodwill


@router.delete("/{goodwill_id}", status_code=204)
def delete_goodwill_route(
    goodwill_id: UUID,
    project_id: UUID,
    db: Session = Depends(sync_db),
    user=Depends(get_current_user),
):
    if not delete_goodwill(db, goodwill_id, project_id):
        raise HTTPException(status_code=404, detail="商誉记录不存在")
