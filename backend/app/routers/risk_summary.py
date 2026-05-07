"""风险摘要端点 [R8-S2-07]

GET /api/projects/{project_id}/risk-summary
聚合项目签字前的风险摘要，供合伙人签字决策面板使用。

R8 复盘修正：增加 year 查询参数（可选，不传则取项目最新年度）
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.risk_summary_service import RiskSummaryService

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["risk-summary"],
)


@router.get("/risk-summary")
async def get_risk_summary(
    project_id: UUID,
    year: int | None = Query(None, description="年度（可选，不传则取项目最新年度）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回项目的风险摘要（签字决策面板用）

    结构见 services/risk_summary_service.py::RiskSummaryService.aggregate 注释。
    """
    svc = RiskSummaryService(db)
    return await svc.aggregate(project_id, year=year)
