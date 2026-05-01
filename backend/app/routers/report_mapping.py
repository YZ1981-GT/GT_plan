"""报表模板转换映射 API

POST /api/projects/{project_id}/report-mapping          — 保存映射规则
GET  /api/projects/{project_id}/report-mapping           — 获取已保存的映射规则
GET  /api/projects/{project_id}/report-mapping/preset    — 获取预设映射规则
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.report_mapping_service import ReportMappingService

router = APIRouter(
    prefix="/api/projects/{project_id}/report-mapping",
    tags=["report-mapping"],
)


@router.get("/preset")
async def get_preset_mapping(
    project_id: UUID,
    report_type: str = "balance_sheet",
    scope: str = "standalone",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取预设映射规则（按行名自动匹配）"""
    svc = ReportMappingService(db)
    return await svc.get_preset_mapping(report_type, scope)


@router.get("")
async def get_saved_mapping(
    project_id: UUID,
    report_type: str = "balance_sheet",
    scope: str = "standalone",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取已保存的映射规则"""
    svc = ReportMappingService(db)
    result = await svc.get_saved_mapping(project_id, report_type, scope)
    return result or {"rules": [], "rule_hash": None, "cached": False}


@router.post("")
async def save_mapping(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存映射规则"""
    svc = ReportMappingService(db)
    result = await svc.save_mapping(
        project_id=project_id,
        report_type=body.get("report_type", "balance_sheet"),
        scope=body.get("scope", "standalone"),
        rules=body.get("rules", []),
    )
    await db.commit()
    return result
