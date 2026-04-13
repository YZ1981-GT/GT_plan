"""底稿跨企业汇总 API 路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.workpaper_summary_service import WorkpaperSummaryService

router = APIRouter(prefix="/api/projects", tags=["workpaper-summary"])

_svc = WorkpaperSummaryService()


class SummaryRequest(BaseModel):
    year: int
    account_codes: list[str]
    company_codes: list[str]


@router.get("/{project_id}/child-companies")
async def get_child_companies(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取合并项目下的子公司列表"""
    companies = await _svc.get_child_companies(db, project_id)
    return companies


@router.post("/{project_id}/workpaper-summary")
async def generate_summary(
    project_id: UUID,
    body: SummaryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成跨企业底稿汇总"""
    if not body.account_codes:
        raise HTTPException(status_code=400, detail="请至少选择一个科目")
    if not body.company_codes:
        raise HTTPException(status_code=400, detail="请至少选择一个企业")

    result = await _svc.generate_summary(
        db, project_id, body.year, body.account_codes, body.company_codes,
    )
    return result


@router.post("/{project_id}/workpaper-summary/export")
async def export_summary_excel(
    project_id: UUID,
    body: SummaryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出跨企业汇总 Excel"""
    if not body.account_codes:
        raise HTTPException(status_code=400, detail="请至少选择一个科目")
    if not body.company_codes:
        raise HTTPException(status_code=400, detail="请至少选择一个企业")

    buf = await _svc.export_excel(
        db, project_id, body.year, body.account_codes, body.company_codes,
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=workpaper_summary.xlsx"},
    )
