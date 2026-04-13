"""多准则适配 API 路由

- GET  /api/accounting-standards          — 准则列表
- GET  /api/accounting-standards/{id}     — 准则详情
- GET  /api/accounting-standards/{id}/chart — 准则科目表
- GET  /api/accounting-standards/{id}/report-formats — 准则报表格式
- GET  /api/accounting-standards/{id}/note-templates — 准则附注模版
- POST /api/accounting-standards/seed     — 加载种子数据
- PUT  /api/projects/{project_id}/accounting-standard — 切换项目准则

Validates: Requirements 3.1-3.4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.accounting_standard_service import AccountingStandardService

router = APIRouter(tags=["accounting-standards"])


class SwitchStandardRequest(BaseModel):
    standard_id: UUID


@router.get("/api/accounting-standards")
async def list_standards(db: AsyncSession = Depends(get_db)):
    """准则列表"""
    svc = AccountingStandardService()
    return await svc.list_standards(db)


@router.get("/api/accounting-standards/{standard_id}")
async def get_standard(standard_id: UUID, db: AsyncSession = Depends(get_db)):
    """准则详情"""
    svc = AccountingStandardService()
    result = await svc.get_standard(db, standard_id)
    if result is None:
        raise HTTPException(status_code=404, detail="会计准则不存在")
    return result


@router.post("/api/accounting-standards/seed")
async def load_seed_data(db: AsyncSession = Depends(get_db)):
    """加载种子数据（幂等）"""
    svc = AccountingStandardService()
    result = await svc.load_seed_data(db)
    await db.commit()
    return result


@router.put("/api/projects/{project_id}/accounting-standard")
async def switch_project_standard(
    project_id: UUID,
    body: SwitchStandardRequest,
    db: AsyncSession = Depends(get_db),
):
    """切换项目会计准则"""
    svc = AccountingStandardService()
    try:
        result = await svc.switch_project_standard(db, project_id, body.standard_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/accounting-standards/{standard_code}/chart")
async def get_standard_chart(standard_code: str):
    """获取准则对应的标准科目表"""
    svc = AccountingStandardService()
    return svc.get_standard_chart(standard_code)


@router.get("/api/accounting-standards/{standard_code}/report-formats")
async def get_standard_report_formats(standard_code: str):
    """获取准则对应的报表格式配置"""
    svc = AccountingStandardService()
    return svc.get_standard_report_formats(standard_code)


@router.get("/api/accounting-standards/{standard_code}/note-templates")
async def get_standard_note_templates(standard_code: str):
    """获取准则对应的附注模版配置"""
    svc = AccountingStandardService()
    return svc.get_standard_note_templates(standard_code)
