"""连续审计 API — Phase 10 Task 2.1-2.2

- POST /api/projects/{id}/create-next-year  一键创建当年项目
- GET  /api/projects/{id}/prior-year-data   跨年数据对比
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.phase10_schemas import CreateNextYearRequest, CreateNextYearResponse
from app.services.continuous_audit_service import ContinuousAuditService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["continuous-audit"])


@router.post("/create-next-year")
async def create_next_year(
    project_id: UUID,
    body: CreateNextYearRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """一键创建当年项目（继承上年配置和数据）"""
    svc = ContinuousAuditService()
    req = body or CreateNextYearRequest()
    try:
        result = await svc.create_next_year(
            db=db,
            prior_project_id=project_id,
            copy_team=req.copy_team,
            copy_mapping=req.copy_mapping,
            copy_procedures=req.copy_procedures,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/prior-year-data")
async def get_prior_year_data(
    project_id: UUID,
    account_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取上年同科目数据（跨年对比）"""
    import sqlalchemy as sa
    from app.models.core import Project
    from app.models.audit_platform_models import TrialBalance

    # 查找当前项目的 prior_year_project_id
    result = await db.execute(
        sa.text("SELECT prior_year_project_id FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )
    row = result.first()
    if not row or not row[0]:
        return {"has_prior_year": False, "rows": []}

    prior_pid = row[0]

    # 查询上年试算表数据
    query = sa.select(TrialBalance).where(
        TrialBalance.project_id == prior_pid,
        TrialBalance.is_deleted == sa.false(),
    )
    if account_code:
        query = query.where(TrialBalance.standard_account_code == account_code)
    query = query.order_by(TrialBalance.standard_account_code)

    result = await db.execute(query)
    rows = result.scalars().all()

    return {
        "has_prior_year": True,
        "prior_project_id": str(prior_pid),
        "rows": [
            {
                "account_code": r.standard_account_code,
                "account_name": r.account_name,
                "opening_balance": float(r.opening_balance) if r.opening_balance else None,
                "unadjusted_amount": float(r.unadjusted_amount) if r.unadjusted_amount else None,
                "audited_amount": float(r.audited_amount) if r.audited_amount else None,
            }
            for r in rows
        ],
    }
