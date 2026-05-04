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
    get_summary_center,
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


@router.get("/summary-center/year")
async def elimination_summary_center(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """合并抵消分录表汇总中心 [R11.2] — 5 个区域分类汇总"""
    return await get_summary_center(db, project_id, year)


@router.post("/auto-generate")
async def auto_generate_eliminations(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    内部抵消表自动汇总 [R11.3]

    从内部交易表、内部往来表自动生成合并抵消分录（预览模式，不直接写入）。
    前端确认后再调用 POST /api/consolidation/eliminations 逐条创建。
    """
    from app.services.internal_trade_service import auto_generate_elimination_entries
    entries = await auto_generate_elimination_entries(db, project_id, year)
    return {"generated_entries": entries, "count": len(entries)}


@router.post("/equity-method/calculate")
async def calculate_equity_method_route(
    data: dict,
    user=Depends(get_current_user),
):
    """
    模拟权益法计算 [R11.1]

    接收被投资单位财务数据，返回权益法调整结果和生成的抵消分录。
    """
    from decimal import Decimal
    from app.services.equity_method_service import EquityMethodInput, calculate_equity_method

    inp = EquityMethodInput(
        subsidiary_code=data.get("subsidiary_code", ""),
        subsidiary_name=data.get("subsidiary_name", ""),
        parent_share_ratio=Decimal(str(data.get("parent_share_ratio", "0"))),
        initial_investment_cost=Decimal(str(data.get("initial_investment_cost", "0"))),
        opening_book_value=Decimal(str(data.get("opening_book_value", "0"))),
        sub_net_profit=Decimal(str(data.get("sub_net_profit", "0"))),
        sub_other_comprehensive_income=Decimal(str(data.get("sub_other_comprehensive_income", "0"))),
        sub_net_assets_at_acquisition=Decimal(str(data.get("sub_net_assets_at_acquisition", "0"))),
        sub_current_net_assets=Decimal(str(data.get("sub_current_net_assets", "0"))),
        sub_dividend_declared=Decimal(str(data.get("sub_dividend_declared", "0"))),
        unrealized_upstream_profit=Decimal(str(data.get("unrealized_upstream_profit", "0"))),
        unrealized_downstream_profit=Decimal(str(data.get("unrealized_downstream_profit", "0"))),
        recoverable_amount=Decimal(str(data["recoverable_amount"])) if data.get("recoverable_amount") is not None else None,
        accumulated_impairment=Decimal(str(data.get("accumulated_impairment", "0"))),
    )

    result = calculate_equity_method(inp)

    return {
        "subsidiary_code": result.subsidiary_code,
        "subsidiary_name": result.subsidiary_name,
        "investment_income": str(result.investment_income),
        "adjusted_net_profit": str(result.adjusted_net_profit),
        "oci_adjustment": str(result.oci_adjustment),
        "upstream_profit_elimination": str(result.upstream_profit_elimination),
        "downstream_profit_elimination": str(result.downstream_profit_elimination),
        "impairment_loss": str(result.impairment_loss),
        "accumulated_impairment": str(result.accumulated_impairment),
        "excess_loss": str(result.excess_loss),
        "is_excess_loss": result.is_excess_loss,
        "goodwill": str(result.goodwill),
        "bargain_purchase_gain": str(result.bargain_purchase_gain),
        "closing_book_value": str(result.closing_book_value),
        "total_adjustment": str(result.total_adjustment),
        "journal_entries": result.journal_entries,
    }
