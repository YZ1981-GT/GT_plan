"""合并抵消路由"""

import logging
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
    GenerateFromWorksheetRequest,
    LegacySheetConvertRequest,
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
    node_key: str | None = Query(None, description="按归属差额节点筛选：{企业代码}:consol_elim / {企业代码}:branch_elim"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    try:
        return await get_entries(db, project_id, year, entry_type, review_status, node_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── 合并抵消分录明细表（spec consol-elimination-single-source-push 任务 6）─────────────
# 固定路径必须声明在 ``/{entry_id}`` 之前，否则会被当成分录 id 解析成 422。


def _sheet_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc))


@router.get("/tree-lines")
async def elimination_tree_lines(
    project_id: UUID,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """本企业树全部未删分录的明细行（含下级合并项目承载的，只读）+ 合计 + 本项目承载的差额节点。"""
    from app.services.consol_elimination_sheet_service import SheetError, tree_lines

    try:
        return await tree_lines(db, project_id, year)
    except SheetError as e:
        raise _sheet_error(e) from e


@router.post("/generate-from-worksheet")
async def generate_eliminations_from_worksheet(
    project_id: UUID,
    body: GenerateFromWorksheetRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """合并工作底稿（模拟权益法 / 内部往来 / 内部交易）计算结果 ⇒ 草稿分录（幂等；已提交审批与已审批的不改）。

    ``dry_run=true`` 只返回映射与将要发生的变化（明细表「待生成」预览），不写库。
    """
    from app.services.consol_elimination_sheet_service import SheetError, generate_from_worksheet

    try:
        result = await generate_from_worksheet(
            db, project_id, body.year, body.groups, origins=body.origins, dry_run=body.dry_run, user_id=user.id,
        )
    except SheetError as e:
        raise _sheet_error(e) from e
    if not body.dry_run:
        await db.commit()
    return result.to_dict()


@router.get("/legacy-sheet")
async def elimination_legacy_sheet(
    project_id: UUID,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """旧版明细表（``consol_worksheet_data['elimination']``）自定义行检测：条数、分组预演与不能转入的原因。"""
    from app.services.consol_elimination_sheet_service import SheetError, legacy_sheet

    try:
        return await legacy_sheet(db, project_id, year)
    except SheetError as e:
        raise _sheet_error(e) from e


@router.post("/legacy-sheet/convert")
async def convert_elimination_legacy_sheet(
    project_id: UUID,
    body: LegacySheetConvertRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """旧版自定义行转为草稿分录（``origin='legacy_sheet'``）；转不了的逐条返回原因，重复调用不重复转入。"""
    from app.services.consol_elimination_sheet_service import SheetError, legacy_sheet

    try:
        result = await legacy_sheet(
            db, project_id, body.year, convert=True,
            entry_type=body.entry_type.value if body.entry_type else None, user_id=user.id,
        )
    except SheetError as e:
        raise _sheet_error(e) from e
    await db.commit()
    return result


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


_AUDITED_ACTIONS = {"approve": "consol.elimination.approve", "revoke": "consol.elimination.revoke"}


@router.post("/{entry_id}/review", response_model=EliminationEntryResponse)
async def review_elimination(
    entry_id: UUID,
    project_id: UUID,
    action: EliminationReviewAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """复核：提交审批 / 审批 / 驳回 / 撤销审批。审批与撤销审批记审计日志，并触发合并推送
    （本项目 + 上层合并项目：差额表 → 合并试算 → 合并报表 → 附注标记，spec consol-elimination-single-source-push 需求 8）。"""
    from app.services.elimination_service import EntryLockedError, get_entry

    existing = await get_entry(db, entry_id, project_id)
    before_status = existing.review_status.value if existing and existing.review_status else None
    try:
        entry = await change_review_status(db, entry_id, project_id, action, user.id)
    except EntryLockedError as e:
        raise HTTPException(status_code=423, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not entry:
        raise HTTPException(status_code=404, detail="抵消分录不存在")

    audit_action = _AUDITED_ACTIONS.get(action.action)
    if audit_action is None:
        return entry
    from app.services.consol_audit_helper import log_consol_action

    await log_consol_action(
        db,
        user_id=user.id,
        project_id=project_id,
        action=audit_action,
        resource_type="elimination_entry",
        resource_id=str(entry_id),
        before={"review_status": before_status},
        after={"review_status": entry.review_status.value if entry.review_status else None},
    )
    await db.flush()
    await db.commit()

    # 审批 / 撤销审批已落库 commit；推送为下游派生，失败记推送运行但不影响审批本身（EH3）
    try:
        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.schemas.consol_context import ConsolContext
        from app.services.event_bus import event_bus

        await event_bus.publish(EventPayload(
            event_type=EventType.ELIMINATION_APPROVED if action.action == "approve" else EventType.ELIMINATION_REVOKED,
            project_id=project_id,
            year=entry.year,
            extra={"entry_id": str(entry_id)},
            context=ConsolContext.legacy(
                project_id=project_id,
                year=entry.year,
                source_version=str(entry_id),
            ),
        ))
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("分录 %s 事件发布失败（审批已生效，可在合并推送页手动推送）", entry_id)
    return entry


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
