"""报表格式配置 API

覆盖：
- GET  列表（按 report_type / applicable_standard 筛选）
- GET  详情
- POST 克隆标准配置到项目
- PUT  修改配置行
- POST 加载种子数据
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.report_models import FinancialReportType
from app.models.report_schemas import ReportConfigCloneRequest, ReportConfigRow
from app.services.report_config_service import ReportConfigService

router = APIRouter(
    prefix="/api/report-config",
    tags=["report-config"],
)


@router.get("")
async def list_report_configs(
    report_type: FinancialReportType | None = Query(None),
    applicable_standard: str = Query("enterprise"),
    db: AsyncSession = Depends(get_db),
):
    """查询报表配置列表"""
    svc = ReportConfigService(db)
    rows = await svc.list_configs(
        report_type=report_type,
        applicable_standard=applicable_standard,
    )
    return [ReportConfigRow.model_validate(r) for r in rows]


@router.get("/{config_id}")
async def get_report_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """查询单行配置详情"""
    svc = ReportConfigService(db)
    row = await svc.get_config(config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="配置行不存在")
    return ReportConfigRow.model_validate(row)


@router.post("/clone")
async def clone_report_config(
    data: ReportConfigCloneRequest,
    db: AsyncSession = Depends(get_db),
):
    """克隆标准配置到项目"""
    svc = ReportConfigService(db)
    try:
        count = await svc.clone_report_config(
            project_id=data.project_id,
            applicable_standard=data.applicable_standard,
        )
        await db.commit()
        return {"message": f"成功克隆 {count} 行配置", "count": count}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{config_id}")
async def update_report_config(
    config_id: UUID,
    updates: dict,
    db: AsyncSession = Depends(get_db),
):
    """修改配置行"""
    svc = ReportConfigService(db)
    try:
        row = await svc.update_config(config_id, updates)
        await db.commit()
        return ReportConfigRow.model_validate(row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/seed")
async def load_seed_data(
    db: AsyncSession = Depends(get_db),
):
    """加载种子数据"""
    svc = ReportConfigService(db)
    count = await svc.load_seed_data()
    await db.commit()
    return {"message": f"成功加载 {count} 行种子数据", "count": count}
