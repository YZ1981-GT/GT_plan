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
from app.deps import get_current_user
from app.models.core import User
from app.models.report_models import FinancialReportType, ReportConfig
from app.models.report_schemas import ReportConfigCloneRequest, ReportConfigRow
from app.services.report_config_service import ReportConfigService

router = APIRouter(
    prefix="/api/report-config",
    tags=["report-config"],
)


@router.get("")
async def list_report_configs(
    report_type: FinancialReportType | None = Query(None),
    applicable_standard: str | None = Query(None),
    project_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询报表配置列表。
    
    优先级：applicable_standard 显式传入 > 从 project_id 自动解析 > 降级 enterprise
    """
    if not applicable_standard and project_id:
        applicable_standard = await ReportConfigService.resolve_applicable_standard(db, project_id)
    if not applicable_standard:
        applicable_standard = "enterprise"
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
):
    """修改配置行"""
    svc = ReportConfigService(db)
    try:
        row = await svc.update_config(config_id, updates, user_id=current_user.id)
        await db.commit()
        return ReportConfigRow.model_validate(row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("")
async def create_report_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新增配置行"""
    rc = ReportConfig(
        report_type=FinancialReportType(body["report_type"]),
        row_number=body.get("row_number", 0),
        row_code=body.get("row_code", ""),
        row_name=body.get("row_name", ""),
        indent_level=body.get("indent_level", 0),
        formula=body.get("formula"),
        applicable_standard=body.get("applicable_standard", "enterprise"),
        is_total_row=body.get("is_total_row", False),
        parent_row_code=body.get("parent_row_code"),
    )
    db.add(rc)
    await db.flush()
    await db.commit()
    return ReportConfigRow.model_validate(rc)


@router.delete("/{config_id}")
async def delete_report_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除配置行"""
    import sqlalchemy as sa
    result = await db.execute(
        sa.select(ReportConfig).where(ReportConfig.id == config_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="行不存在")
    row.is_deleted = True
    await db.commit()
    return {"deleted": True}


@router.post("/seed")
async def load_seed_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """加载种子数据"""
    svc = ReportConfigService(db)
    count = await svc.load_seed_data()
    await db.commit()
    return {"message": f"成功加载 {count} 行种子数据", "count": count}


@router.post("/batch-update")
async def batch_update_report_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量更新报表行的金额（从试算平衡表审定数回填）"""
    import sqlalchemy as sa

    project_id = body.get("project_id")
    report_type_str = body.get("report_type", "balance_sheet")
    applicable_standard = body.get("applicable_standard", "soe_consolidated")
    updates = body.get("updates", [])

    if not project_id or not updates:
        return {"updated": 0, "message": "无数据"}

    try:
        report_type = FinancialReportType(report_type_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的报表类型: {report_type_str}")

    updated = 0
    for upd in updates:
        row_code = upd.get("row_code")
        amount = upd.get("current_period_amount")
        if not row_code or amount is None:
            continue

        result = await db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.report_type == report_type,
                ReportConfig.applicable_standard == applicable_standard,
                ReportConfig.row_code == row_code,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.current_period_amount = float(amount)
            updated += 1

    if updated:
        await db.commit()

    return {"updated": updated, "message": f"已更新 {updated} 行"}
