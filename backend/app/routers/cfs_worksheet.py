"""现金流量表工作底稿 API 路由

覆盖：
- POST /api/cfs-worksheet/generate — 生成工作底稿
- GET  /api/cfs-worksheet/{project_id}/{year} — 获取工作底稿数据
- POST /api/cfs-worksheet/adjustments — 创建CFS调整分录
- PUT  /api/cfs-worksheet/adjustments/{id} — 修改CFS调整分录
- DELETE /api/cfs-worksheet/adjustments/{id} — 删除CFS调整分录
- GET  /api/cfs-worksheet/{project_id}/{year}/adjustments — 列出调整分录
- GET  /api/cfs-worksheet/{project_id}/{year}/reconciliation — 获取平衡状态
- POST /api/cfs-worksheet/auto-generate — 自动生成常见调整项
- GET  /api/cfs-worksheet/{project_id}/{year}/indirect-method — 获取间接法补充资料
- GET  /api/cfs-worksheet/{project_id}/{year}/verify — 勾稽校验
- GET  /api/cfs-worksheet/{project_id}/{year}/main-table — 现金流量表主表

Validates: Requirements 3.1-3.12
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.report_schemas import (
    CFSAdjustmentCreate,
    CFSAdjustmentResponse,
    CFSAdjustmentUpdate,
    ReportGenerateRequest,
)
from app.services.cfs_worksheet_engine import CFSWorksheetEngine

router = APIRouter(
    prefix="/api/cfs-worksheet",
    tags=["cfs-worksheet"],
)


@router.post("/generate")
async def generate_worksheet(
    data: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """生成工作底稿"""
    engine = CFSWorksheetEngine(db)
    try:
        result = await engine.generate_worksheet(data.project_id, data.year)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"工作底稿生成失败: {str(e)}")


@router.get("/{project_id}/{year}")
async def get_worksheet(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """获取工作底稿数据"""
    engine = CFSWorksheetEngine(db)
    return await engine.generate_worksheet(project_id, year)


@router.post("/adjustments")
async def create_adjustment(
    project_id: UUID,
    data: CFSAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建CFS调整分录"""
    engine = CFSWorksheetEngine(db)
    try:
        adj = await engine.create_adjustment(
            project_id=project_id,
            year=data.year,
            description=data.description,
            debit_account=data.debit_account,
            credit_account=data.credit_account,
            amount=data.amount,
            cash_flow_category=data.cash_flow_category,
            cash_flow_line_item=data.cash_flow_line_item,
        )
        await db.commit()
        return CFSAdjustmentResponse.model_validate(adj)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/adjustments/{adjustment_id}")
async def update_adjustment(
    adjustment_id: UUID,
    data: CFSAdjustmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """修改CFS调整分录"""
    engine = CFSWorksheetEngine(db)
    try:
        update_data = data.model_dump(exclude_unset=True)
        adj = await engine.update_adjustment(adjustment_id, **update_data)
        await db.commit()
        return CFSAdjustmentResponse.model_validate(adj)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"修改失败: {str(e)}")


@router.delete("/adjustments/{adjustment_id}")
async def delete_adjustment(
    adjustment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除CFS调整分录"""
    engine = CFSWorksheetEngine(db)
    deleted = await engine.delete_adjustment(adjustment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="调整分录不存在")
    await db.commit()
    return {"message": "删除成功"}


@router.get("/{project_id}/{year}/adjustments")
async def list_adjustments(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """列出所有CFS调整分录"""
    engine = CFSWorksheetEngine(db)
    adjustments = await engine.list_adjustments(project_id, year)
    return [CFSAdjustmentResponse.model_validate(a) for a in adjustments]


@router.get("/{project_id}/{year}/reconciliation")
async def get_reconciliation(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """获取工作底稿平衡状态"""
    engine = CFSWorksheetEngine(db)
    return await engine.get_reconciliation_status(project_id, year)


@router.post("/auto-generate")
async def auto_generate_adjustments(
    data: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """自动生成常见调整项"""
    engine = CFSWorksheetEngine(db)
    try:
        created = await engine.auto_generate_adjustments(data.project_id, data.year)
        await db.commit()
        return {
            "message": f"自动生成 {len(created)} 条调整分录",
            "adjustments": created,
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"自动生成失败: {str(e)}")


@router.get("/{project_id}/{year}/indirect-method")
async def get_indirect_method(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """获取间接法补充资料"""
    engine = CFSWorksheetEngine(db)
    return await engine.generate_indirect_method(project_id, year)


@router.get("/{project_id}/{year}/verify")
async def verify_reconciliation(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """勾稽校验"""
    engine = CFSWorksheetEngine(db)
    return await engine.verify_reconciliation(project_id, year)


@router.get("/{project_id}/{year}/main-table")
async def get_main_table(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """获取现金流量表主表数据"""
    engine = CFSWorksheetEngine(db)
    return await engine.generate_cfs_main_table(project_id, year)
