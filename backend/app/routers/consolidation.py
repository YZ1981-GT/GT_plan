"""合并抵消路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import require_project_access
from app.core.database import get_db
from app.models.core import User
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
    user: User = Depends(require_project_access("readonly")),
):
    return await get_entries(db, project_id, year, entry_type, review_status)


@router.post("", response_model=EliminationEntryResponse, status_code=201)
async def create_elimination(
    project_id: UUID,
    data: EliminationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
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
    user: User = Depends(require_project_access("readonly")),
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
    user: User = Depends(require_project_access("edit")),
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
    user: User = Depends(require_project_access("edit")),
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
    user: User = Depends(require_project_access("edit")),
):
    try:
        before_status = None
        # Capture before state for audit
        from app.services.elimination_service import get_entry
        existing = await get_entry(db, entry_id, project_id)
        if existing:
            before_status = existing.review_status.value if existing.review_status else None

        entry = await change_review_status(db, entry_id, project_id, action, user.id)
        if not entry:
            raise HTTPException(status_code=404, detail="抵消分录不存在")

        # Audit log for approval actions
        if action.action == "approve":
            from app.services.consol_audit_helper import log_consol_action
            await log_consol_action(
                db,
                user_id=user.id,
                project_id=project_id,
                action="consol.elimination.approve",
                resource_type="elimination_entry",
                resource_id=str(entry_id),
                before={"review_status": before_status},
                after={"review_status": entry.review_status.value if entry.review_status else None},
            )
            await db.flush()
            await db.commit()

            # 衔接2 / Phase 2 Task 4.4：审批 → 发 ELIMINATION_APPROVED 事件触发 worksheet + trial 重算
            # （Phase 1 实装了该事件，填补了 Phase 2 自动抵销审批后重算的依赖；
            # 审批已落库 commit，重算为下游派生，失败不影响审批本身，EH3）
            try:
                from app.models.audit_platform_schemas import EventPayload, EventType
                from app.services.event_bus import event_bus
                await event_bus.publish(EventPayload(
                    event_type=EventType.ELIMINATION_APPROVED,
                    project_id=project_id,
                    year=entry.year,
                    extra={"entry_id": str(entry_id)},
                ))
            except Exception:
                pass  # 事件发布失败不阻断审批

        return entry
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/summary/year", response_model=list[EliminationSummary])
async def elimination_summary(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    return await get_summary(db, project_id, year)


@router.get("/summary-center/year")
async def elimination_summary_center(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """合并抵消分录表汇总中心 [R11.2] — 5 个区域分类汇总"""
    return await get_summary_center(db, project_id, year)


@router.post("/auto-generate")
async def auto_generate_eliminations(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """
    内部抵消表自动汇总 [R11.3 / Phase 2 B3]

    接通 4 类预设抵销规则（consol_elimination_rules.calculate_elimination_amount：
    internal_ar / internal_revenue / internal_inventory_unrealized / internal_dividend），
    从子公司内部交易/往来数据自动生成抵销分录**草稿**（review_status=draft）。

    铁律（S3 / ADR-CONSOL-203）：
    - 生成的所有分录强制 review_status=draft，本端点不触发任何重算。
    - 审计师复核草稿（→APPROVED）后，经 Phase 1 ELIMINATION_APPROVED 事件触发
      worksheet + trial 重算才进合并数。
    - 无匹配内部交易数据的规则返回 0，跳过不生成、不报错（EH4）。
    """
    from app.services.consol_auto_elimination_service import (
        auto_generate_draft_eliminations,
    )

    entries = await auto_generate_draft_eliminations(db, project_id, year)
    serialized = [
        {
            "id": str(e.id),
            "entry_no": e.entry_no,
            "entry_type": e.entry_type.value if e.entry_type else None,
            "description": e.description,
            "account_code": e.account_code,
            "account_name": e.account_name,
            "debit_amount": str(e.debit_amount),
            "credit_amount": str(e.credit_amount),
            "review_status": e.review_status.value if e.review_status else None,
            "entry_group_id": str(e.entry_group_id) if e.entry_group_id else None,
            "related_company_codes": e.related_company_codes,
        }
        for e in entries
    ]
    return {"generated_entries": serialized, "count": len(serialized)}


@router.post("/equity-method/calculate")
async def calculate_equity_method_route(
    data: dict,
    project_id: UUID = Query(...),
    user: User = Depends(require_project_access("edit")),
):
    """
    模拟权益法计算 [R11.1]

    接收被投资单位财务数据，返回权益法调整结果和生成的抵消分录。
    """
    from decimal import Decimal
    from app.services.equity_method_service import EquityMethodInput, calculate_equity_method

    def _dec(key: str, default: str = "0") -> Decimal:
        val = data.get(key, default)
        if val is None or val == "":
            return Decimal(default)
        return Decimal(str(val))

    def _opt_dec(key: str) -> Decimal | None:
        if data.get(key) is None or data.get(key) == "":
            return None
        return Decimal(str(data[key]))

    inp = EquityMethodInput(
        subsidiary_code=data.get("subsidiary_code", ""),
        subsidiary_name=data.get("subsidiary_name", ""),
        parent_share_ratio=_dec("parent_share_ratio"),
        initial_investment_cost=_dec("initial_investment_cost"),
        opening_book_value=_dec("opening_book_value"),
        sub_net_profit=_dec("sub_net_profit"),
        sub_other_comprehensive_income=_dec("sub_other_comprehensive_income"),
        sub_net_assets_at_acquisition=_dec("sub_net_assets_at_acquisition"),
        sub_current_net_assets=_dec("sub_current_net_assets"),
        sub_dividend_declared=_dec("sub_dividend_declared"),
        unrealized_upstream_profit=_dec("unrealized_upstream_profit"),
        unrealized_downstream_profit=_dec("unrealized_downstream_profit"),
        recoverable_amount=_opt_dec("recoverable_amount"),
        accumulated_impairment=_dec("accumulated_impairment"),
        long_term_receivable=_dec("long_term_receivable"),
        other_long_term_equity=_dec("other_long_term_equity"),
        estimated_liability=_dec("estimated_liability"),
        g716_unrecognized_loss=_opt_dec("g716_unrecognized_loss"),
        g716_current_change=_opt_dec("g716_current_change"),
        g716_excess_loss=_opt_dec("g716_excess_loss"),
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
        "long_term_interest_capacity": str(result.long_term_interest_capacity),
        "g716_unrecognized_loss": (
            str(result.g716_unrecognized_loss)
            if result.g716_unrecognized_loss is not None else None
        ),
        "g716_current_change": (
            str(result.g716_current_change)
            if result.g716_current_change is not None else None
        ),
        "g716_excess_loss": (
            str(result.g716_excess_loss) if result.g716_excess_loss is not None else None
        ),
        "goodwill": str(result.goodwill),
        "bargain_purchase_gain": str(result.bargain_purchase_gain),
        "closing_book_value": str(result.closing_book_value),
        "total_adjustment": str(result.total_adjustment),
        "journal_entries": result.journal_entries,
    }
