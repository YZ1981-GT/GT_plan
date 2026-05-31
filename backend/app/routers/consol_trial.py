"""合并试算表路由"""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import require_project_access
from app.core.database import get_db
from app.models.core import User
from app.models.consolidation_schemas import ConsolTrialResponse, ConsolTrialUpdate, ConsistencyCheckResult
from app.services.consol_trial_service import (
    check_trial_consistency,
    delete_trial,
    get_trial_balance,
    get_trial_row,
    recalculate_trial,
    upsert_trial_row,
)
from app.services.consol_reconciliation_service import reconcile_worksheet_vs_trial

router = APIRouter(prefix="/api/consolidation/trial", tags=["合并试算表"])


@router.get("", response_model=list[ConsolTrialResponse])
async def get_trial_balance_list(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    return await get_trial_balance(db, project_id, year)


@router.put("/{trial_id}", response_model=ConsolTrialResponse)
async def update_trial_row(
    trial_id: UUID,
    project_id: UUID,
    data: ConsolTrialUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    trial = await get_trial_row(db, trial_id, project_id)
    if not trial:
        raise HTTPException(status_code=404, detail="试算表行不存在")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(trial, key, value)

    db.commit()
    db.refresh(trial)
    return trial


@router.post("/recalculate", response_model=list[ConsolTrialResponse])
async def trigger_recalculate(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """触发全量重算"""
    result = await recalculate_trial(db, project_id, year)
    from app.services.consol_audit_helper import log_consol_action
    await log_consol_action(
        db,
        user_id=user.id,
        project_id=project_id,
        action="consol.recalc",
        resource_type="consol_trial",
        resource_id=str(project_id),
        before=None,
        after={"year": year, "rows_recalculated": len(result)},
    )
    await db.commit()
    return result


@router.get("/consistency-check", response_model=ConsistencyCheckResult)
async def check_consistency(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """一致性校验"""
    return ConsistencyCheckResult(**check_trial_consistency(db, project_id, year))


@router.get("/stale-status")
async def get_trial_stale_status(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """合并 trial 陈旧状态（P1）：子公司 TB 变更后母公司 trial 是否需重算。

    前端据此显示"子公司数据已更新，建议重新汇总"提示 + 重算入口。
    """
    trials = await get_trial_balance(db, project_id, year)
    stale_rows = [t for t in trials if getattr(t, "is_stale", False)]
    return {
        "is_stale": len(stale_rows) > 0,
        "stale_count": len(stale_rows),
        "total_count": len(trials),
    }


@router.get("/reconciliation")
async def get_reconciliation(
    project_id: UUID,
    year: int,
    tolerance: float = 0.01,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """B2 单一事实源对账：worksheet 根节点 consolidated_amount vs consol_trial.consol_amount。

    观测手段（不阻断）：diff 超容差返回 is_reconciled=false + diffs 清单，接口仍 200。
    diff ≠ 缺陷（抵销归集维度差异是已知设计性不一致，见 ADR-CONSOL-001 / §5.4）。
    """
    result = await reconcile_worksheet_vs_trial(
        db, project_id, year, tolerance=Decimal(str(tolerance))
    )
    return {
        "is_reconciled": result.is_reconciled,
        "tolerance": str(result.tolerance),
        "max_abs_diff": str(result.max_abs_diff),
        "diff_count": len(result.diffs),
        "diffs": result.diffs,
    }


@router.delete("/{trial_id}", status_code=204)
async def delete_trial_row(
    trial_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    if not await delete_trial(db, trial_id, project_id):
        raise HTTPException(status_code=404, detail="试算表行不存在")
