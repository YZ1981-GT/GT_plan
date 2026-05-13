"""试算表 API"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access, get_user_scope_cycles
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.core import User
from app.deps import check_consol_lock
from app.services.mapping_service import get_codes_by_cycles
from app.services.event_bus import event_bus
from app.services.materiality_service import MaterialityService
from app.services.trial_balance_service import TrialBalanceService

router = APIRouter(
    prefix="/api/projects/{project_id}/trial-balance",
    tags=["trial-balance"],
)


@router.get("")
async def get_trial_balance(
    project_id: UUID,
    year: int = Query(...),
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取试算表（四列结构），含重要性水平高亮标记"""
    svc = TrialBalanceService(db)
    rows = await svc.get_trial_balance(project_id, year, company_code)

    # scope_cycles 过滤：非 admin/partner 用户只能看到被分配循环对应的科目
    scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
    if scope_cycles is not None:
        allowed_codes = await get_codes_by_cycles(project_id, scope_cycles)
        rows = [r for r in rows if r.standard_account_code in allowed_codes]

    # 获取重要性水平用于高亮
    mat_svc = MaterialityService(db)
    materiality = await mat_svc.get_current(project_id, year)
    overall_mat = float(materiality.overall_materiality) if materiality else None
    trivial_thr = float(materiality.trivial_threshold) if materiality else None

    result = []
    for r in rows:
        audited = float(r.audited_amount) if r.audited_amount is not None else 0
        item = {
            "standard_account_code": r.standard_account_code,
            "account_name": r.account_name,
            "account_category": r.account_category.value if r.account_category else None,
            "unadjusted_amount": str(r.unadjusted_amount) if r.unadjusted_amount is not None else None,
            "rje_adjustment": str(r.rje_adjustment),
            "aje_adjustment": str(r.aje_adjustment),
            "audited_amount": str(r.audited_amount) if r.audited_amount is not None else None,
            "opening_balance": str(r.opening_balance) if r.opening_balance is not None else None,
            "exceeds_materiality": abs(audited) >= overall_mat if overall_mat else False,
            "below_trivial": abs(audited) < trivial_thr if trivial_thr else False,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        result.append(item)

    return result


@router.post("/recalc")
async def recalc_trial_balance(
    project_id: UUID,
    year: int = Query(...),
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
    _lock_check=Depends(check_consol_lock),
    current_user: User = Depends(require_project_access("edit")),
):
    """手动触发全量重算（合并锁定期间禁止，需编辑权限）"""
    from app.services.prerequisite_checker import PrerequisiteChecker

    check = await PrerequisiteChecker().check(db, project_id, year, "recalc")
    if not check["ok"]:
        raise HTTPException(status_code=400, detail=check)

    svc = TrialBalanceService(db)
    await svc.full_recalc(project_id, year, company_code)
    await db.commit()
    await event_bus.publish_immediate(EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=project_id,
        year=year,
    ))
    return {"message": "重算完成"}


@router.get("/trace")
async def trace_to_balance(
    project_id: UUID,
    year: int = Query(...),
    standard_account_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """数据溯源：查询标准科目对应的所有客户科目及其余额表原始数据。

    返回该标准科目由哪些客户科目汇总而来，每个客户科目的期末余额/借方发生额/贷方发生额。
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import AccountMapping, TbBalance
    from app.services.dataset_query import get_active_filter

    mp = AccountMapping.__table__
    bal = TbBalance.__table__
    balance_filter = await get_active_filter(db, bal, project_id, year)

    # 查询映射到该标准科目的所有客户科目
    q = (
        sa.select(
            bal.c.account_code,
            bal.c.account_name,
            sa.func.coalesce(bal.c.closing_balance, 0).label("closing_balance"),
            sa.func.coalesce(bal.c.debit_amount, 0).label("debit_amount"),
            sa.func.coalesce(bal.c.credit_amount, 0).label("credit_amount"),
            sa.func.coalesce(bal.c.opening_balance, 0).label("opening_balance"),
        )
        .select_from(
            bal.join(
                mp,
                sa.and_(
                    mp.c.project_id == bal.c.project_id,
                    mp.c.original_account_code == bal.c.account_code,
                    mp.c.is_deleted == sa.false(),
                ),
            )
        )
        .where(
            balance_filter,
            mp.c.standard_account_code == standard_account_code,
        )
        .order_by(bal.c.account_code)
    )

    result = await db.execute(q)
    sources = [
        {
            "account_code": r.account_code,
            "account_name": r.account_name,
            "closing_balance": float(r.closing_balance),
            "debit_amount": float(r.debit_amount),
            "credit_amount": float(r.credit_amount),
            "opening_balance": float(r.opening_balance),
        }
        for r in result.fetchall()
    ]
    return {"sources": sources}


@router.get("/summary-with-adjustments")
async def get_summary_with_adjustments(
    project_id: UUID,
    year: int = Query(...),
    report_type: str = Query("balance_sheet", description="报表类型: balance_sheet / income_statement / cash_flow_statement"),
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """
    试算平衡表汇总（按报表行次），AJE/RJE 从 adjustments 表自动汇总。
    替代前端手动输入 AJE/RJE 的方案，确保数据与调整分录页面一致。
    """
    svc = TrialBalanceService(db)
    rows = await svc.get_summary_with_adjustments(project_id, year, report_type, company_code)
    return {"rows": rows}


@router.get("/consistency-check")
async def consistency_check(
    project_id: UUID,
    year: int = Query(...),
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """数据一致性校验"""
    svc = TrialBalanceService(db)
    issues = await svc.check_consistency(project_id, year, company_code)
    return {"consistent": len(issues) == 0, "issues": issues}
