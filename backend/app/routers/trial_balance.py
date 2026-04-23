"""试算表 API"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.core import User
from app.deps import check_consol_lock
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
    svc = TrialBalanceService(db)
    await svc.full_recalc(project_id, year, company_code)
    await db.commit()
    await event_bus.publish_immediate(EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=project_id,
        year=year,
    ))
    return {"message": "重算完成"}


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
