"""审计报告 API 路由

覆盖：
- POST /api/audit-report/generate — 从模板生成审计报告
- GET  /api/audit-report/{project_id}/{year} — 获取审计报告
- PUT  /api/audit-report/{id}/paragraphs/{section} — 更新报告段落
- GET  /api/audit-report/templates — 获取报告模板列表
- PUT  /api/audit-report/{id}/status — 更新报告状态
- POST /api/audit-report/templates/load-seed — 加载模板种子数据

Validates: Requirements 6.1-6.7
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.report_models import CompanyType, OpinionType
from app.models.report_schemas import (
    AuditReportGenerateRequest,
    AuditReportParagraph,
    AuditReportResponse,
    AuditReportStatusUpdate,
    AuditReportTemplateResponse,
)
from app.services.audit_report_service import AuditReportService

router = APIRouter(
    prefix="/api/audit-report",
    tags=["audit-report"],
)


@router.post("/templates/load-seed")
async def load_seed_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """加载审计报告模板种子数据"""
    svc = AuditReportService(db)
    try:
        count = await svc.load_seed_templates()
        await db.commit()
        return {"message": "模板加载成功", "loaded_count": count}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"模板加载失败: {str(e)}")


@router.get("/templates")
async def get_templates(
    opinion_type: OpinionType | None = Query(None),
    company_type: CompanyType | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取审计报告模板列表"""
    svc = AuditReportService(db)
    templates = await svc.get_templates(opinion_type, company_type)
    return [AuditReportTemplateResponse.model_validate(t) for t in templates]


@router.post("/generate")
async def generate_report(
    data: AuditReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从模板生成审计报告"""
    svc = AuditReportService(db)
    try:
        report = await svc.generate_report(
            data.project_id,
            data.year,
            data.opinion_type,
            data.company_type,
        )
        await db.commit()
        return AuditReportResponse.model_validate(report)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"审计报告生成失败: {str(e)}")


@router.get("/{project_id}/{year}")
async def get_report(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取审计报告"""
    svc = AuditReportService(db)
    report = await svc.get_report(project_id, year)
    if report is None:
        raise HTTPException(status_code=404, detail="审计报告不存在，请先生成")
    return AuditReportResponse.model_validate(report)


@router.put("/{report_id}/paragraphs/{section}")
async def update_paragraph(
    report_id: UUID,
    section: str,
    data: AuditReportParagraph,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新审计报告指定段落内容"""
    svc = AuditReportService(db)
    report = await svc.update_paragraph(report_id, section, data.content)
    if report is None:
        raise HTTPException(status_code=404, detail="审计报告不存在")
    await db.commit()
    return AuditReportResponse.model_validate(report)


@router.put("/{report_id}/status")
async def update_status(
    report_id: UUID,
    data: AuditReportStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新审计报告状态（draft→review→final）"""
    svc = AuditReportService(db)
    try:
        report = await svc.update_status(report_id, data.status)
        if report is None:
            raise HTTPException(status_code=404, detail="审计报告不存在")
        await db.commit()
        return AuditReportResponse.model_validate(report)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{project_id}/{year}/refresh-financial-data")
async def refresh_financial_data(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """刷新审计报告中的财务数据引用。

    从 financial_report 表拉取最新的资产总额/负债/权益/收入/净利润，
    更新到审计报告的 financial_data JSONB 字段。

    如果 financial_report 表无数据，建议先调用报表生成接口。
    """
    svc = AuditReportService(db)
    report = await svc.refresh_financial_data(project_id, year)
    if report is None:
        raise HTTPException(status_code=404, detail="审计报告不存在，请先生成")
    await db.commit()
    return {
        "message": "财务数据已刷新",
        "financial_data": report.financial_data,
    }
