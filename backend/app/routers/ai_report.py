"""AI 审计报告生成路由

提供 AI 辅助审计报告生成的接口：
- 审计报告生成
- 管理建议书摘要生成
- 报告生成状态查询
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

# 项目级报告路由
project_router = APIRouter(prefix="/api/projects/{project_id}/ai/report", tags=["AI-报告生成"])


# ============================================================================
# 请求/响应模型
# ============================================================================


class ReportGenerateRequest(BaseModel):
    """报告生成请求"""
    report_type: str = "audit_report"  # audit_report / management_letter / summary
    year: Optional[int] = None
    parameters: dict = {}


class ReportSummaryRequest(BaseModel):
    """管理建议书摘要请求"""
    sections: list[str] = []  # 需要摘要的章节列表
    year: Optional[int] = None


class ReportGenerateResponse(BaseModel):
    """报告生成响应"""
    task_id: str
    status: str  # pending / processing / completed / failed
    message: str


# ============================================================================
# AI 报告生成服务
# ============================================================================


class AIReportService:
    """AI 报告生成服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_audit_report(
        self,
        project_id: UUID,
        user_id: str,
        report_type: str = "audit_report",
        parameters: dict = None,
    ) -> dict:
        """
        生成审计报告

        Args:
            project_id: 项目ID
            user_id: 用户ID
            report_type: 报告类型 (audit_report / management_letter / summary)
            parameters: 额外参数

        Returns:
            任务信息
        """
        parameters = parameters or {}

        # 根据报告类型调用不同的生成方法
        if report_type == "audit_report":
            return await self._generate_audit_report_content(project_id, user_id, parameters)
        elif report_type == "management_letter":
            return await self._generate_management_letter(project_id, user_id, parameters)
        elif report_type == "summary":
            return await self._generate_summary(project_id, user_id, parameters)
        else:
            return {
                "success": False,
                "message": f"不支持的报告类型: {report_type}",
            }

    async def _generate_audit_report_content(
        self,
        project_id: UUID,
        user_id: str,
        parameters: dict,
    ) -> dict:
        """生成审计报告内容"""
        from app.services.report_engine import ReportEngine

        report_engine = ReportEngine(self.db)
        year = parameters.get("year")

        try:
            # 生成报告内容
            content = await report_engine.generate_audit_report(
                project_id=project_id,
                year=year,
            )

            # 保存到数据库
            from app.models.ai_models import AIAnalysisReport, AnalysisReportStatus

            report = AIAnalysisReport(
                project_id=project_id,
                document_type="audit_report",
                summary=content.get("summary", ""),
                key_findings=content.get("findings", []),
                risk_indicators=content.get("risks", {}),
                status=AnalysisReportStatus.completed,
            )
            self.db.add(report)
            await self.db.commit()

            return {
                "success": True,
                "task_id": str(report.id),
                "status": "completed",
                "content": content,
                "message": "审计报告生成完成",
            }
        except Exception as e:
            logger.exception("Audit report generation failed")
            return {
                "success": False,
                "message": f"审计报告生成失败: {str(e)}",
            }

    async def _generate_management_letter(
        self,
        project_id: UUID,
        user_id: str,
        parameters: dict,
    ) -> dict:
        """生成管理建议书"""
        from app.services.management_letter_service import ManagementLetterService

        service = ManagementLetterService(self.db)
        year = parameters.get("year")

        try:
            # 生成管理建议书内容
            content = await service.generate_letter_draft(
                project_id=project_id,
                year=year,
            )

            # 保存到数据库
            from app.models.ai_models import AIAnalysisReport, AnalysisReportStatus

            report = AIAnalysisReport(
                project_id=project_id,
                document_type="management_letter",
                summary=content.get("summary", ""),
                key_findings=content.get("findings", []),
                status=AnalysisReportStatus.completed,
            )
            self.db.add(report)
            await self.db.commit()

            return {
                "success": True,
                "task_id": str(report.id),
                "status": "completed",
                "content": content,
                "message": "管理建议书生成完成",
            }
        except Exception as e:
            logger.exception("Management letter generation failed")
            return {
                "success": False,
                "message": f"管理建议书生成失败: {str(e)}",
            }

    async def _generate_summary(
        self,
        project_id: UUID,
        user_id: str,
        parameters: dict,
    ) -> dict:
        """生成审计汇总摘要"""
        from app.services.workpaper_fill_service import WorkpaperFillService

        wp_service = WorkpaperFillService(self.db)
        year = parameters.get("year")

        try:
            # 生成汇总摘要
            summary = await wp_service.generate_workpaper_summary(
                project_id=project_id,
                year=year,
            )

            # 保存到数据库
            from app.models.ai_models import AIAnalysisReport, AnalysisReportStatus

            report = AIAnalysisReport(
                project_id=project_id,
                document_type="summary",
                summary=summary.get("summary", ""),
                key_findings=summary.get("key_points", []),
                status=AnalysisReportStatus.completed,
            )
            self.db.add(report)
            await self.db.commit()

            return {
                "success": True,
                "task_id": str(report.id),
                "status": "completed",
                "content": summary,
                "message": "汇总摘要生成完成",
            }
        except Exception as e:
            logger.exception("Summary generation failed")
            return {
                "success": False,
                "message": f"汇总摘要生成失败: {str(e)}",
            }

    async def get_task_status(self, task_id: str) -> dict:
        """
        查询报告生成状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态
        """
        from app.models.ai_models import AIAnalysisReport

        try:
            result = await self.db.execute(
                select(AIAnalysisReport).where(AIAnalysisReport.id == UUID(task_id))
            )
            report = result.scalars().first()

            if not report:
                return {
                    "success": False,
                    "message": "任务不存在",
                }

            return {
                "success": True,
                "task_id": str(report.id),
                "status": report.status.value if hasattr(report.status, "value") else str(report.status),
                "document_type": report.document_type,
                "summary": report.summary,
                "key_findings": report.key_findings,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "updated_at": report.updated_at.isoformat() if report.updated_at else None,
            }
        except Exception as e:
            logger.warning(f"Failed to get task status: {e}")
            return {
                "success": False,
                "message": f"查询失败: {str(e)}",
            }

    async def generate_summary_by_sections(
        self,
        project_id: UUID,
        user_id: str,
        sections: list[str],
        year: Optional[int] = None,
    ) -> dict:
        """
        按章节生成管理建议书摘要

        Args:
            project_id: 项目ID
            user_id: 用户ID
            sections: 需要摘要的章节列表
            year: 审计年度

        Returns:
            各章节摘要
        """
        from app.services.ai_service import AIService
        from app.services.management_letter_service import ManagementLetterService

        ai_service = AIService(self.db)
        ml_service = ManagementLetterService(self.db)

        try:
            # 获取管理建议书数据
            letter_data = await ml_service.get_letter_data(project_id, year)

            # 构建提示词
            sections_text = "\n".join([f"- {s}" for s in sections])
            prompt = f"""请根据以下管理建议书内容，为以下章节生成摘要：
{sections_text}

管理建议书内容：
{letter_data.get('content', '')}

请为每个章节生成简洁的摘要，包含：
1. 主要发现
2. 关键风险点
3. 改进建议
"""

            messages = [{"role": "user", "content": prompt}]
            response = await ai_service.chat_completion(messages, stream=False)

            # 保存到数据库
            from app.models.ai_models import AIAnalysisReport, AnalysisReportStatus

            report = AIAnalysisReport(
                project_id=project_id,
                document_type="section_summary",
                summary=response,
                key_findings={"sections": sections},
                status=AnalysisReportStatus.completed,
            )
            self.db.add(report)
            await self.db.commit()

            return {
                "success": True,
                "task_id": str(report.id),
                "status": "completed",
                "content": {
                    "summary": response,
                    "sections": sections,
                },
                "message": "章节摘要生成完成",
            }
        except Exception as e:
            logger.exception("Section summary generation failed")
            return {
                "success": False,
                "message": f"章节摘要生成失败: {str(e)}",
            }


# SQLAlchemy select 需要导入
from sqlalchemy import select


# ============================================================================
# API 路由
# ============================================================================


@project_router.post("/generate", response_model=ReportGenerateResponse)
async def generate_report(
    project_id: UUID,
    request: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    生成审计报告

    支持的 report_type:
    - audit_report: 审计报告
    - management_letter: 管理建议书
    - summary: 汇总摘要
    """
    service = AIReportService(db)

    result = await service.generate_audit_report(
        project_id=project_id,
        user_id=str(user.id),
        report_type=request.report_type,
        parameters={
            "year": request.year,
            **request.parameters,
        },
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "生成失败"))

    return ReportGenerateResponse(
        task_id=result.get("task_id", ""),
        status=result.get("status", "pending"),
        message=result.get("message", ""),
    )


@project_router.post("/summary")
async def generate_summary(
    project_id: UUID,
    request: ReportSummaryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    生成管理建议书章节摘要

    按指定章节生成摘要内容。
    """
    service = AIReportService(db)

    if request.sections:
        # 按章节生成摘要
        result = await service.generate_summary_by_sections(
            project_id=project_id,
            user_id=str(user.id),
            sections=request.sections,
            year=request.year,
        )
    else:
        # 生成完整摘要
        result = await service.generate_audit_report(
            project_id=project_id,
            user_id=str(user.id),
            report_type="summary",
            parameters={"year": request.year},
        )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "生成失败"))

    return {
        "success": True,
        "task_id": result.get("task_id"),
        "content": result.get("content", {}),
        "message": result.get("message", ""),
    }


@project_router.get("/status/{task_id}")
async def get_report_status(
    project_id: UUID,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    查询报告生成状态

    通过 task_id 查询报告生成进度和结果。
    """
    service = AIReportService(db)

    result = await service.get_task_status(task_id)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message", "任务不存在"))

    return result


@project_router.get("/list")
async def list_reports(
    project_id: UUID,
    document_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    获取项目报告列表

    返回该项目生成的所有 AI 报告。
    """
    from app.models.ai_models import AIAnalysisReport

    query = select(AIAnalysisReport).where(
        AIAnalysisReport.project_id == project_id
    )

    if document_type:
        query = query.where(AIAnalysisReport.document_type == document_type)

    query = query.order_by(AIAnalysisReport.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    reports = result.scalars().all()

    return {
        "success": True,
        "reports": [
            {
                "task_id": str(r.id),
                "document_type": r.document_type,
                "summary": r.summary,
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
        "total": len(reports),
    }


@project_router.get("/{task_id}")
async def get_report_detail(
    project_id: UUID,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    获取报告详情

    返回完整报告内容和元数据。
    """
    service = AIReportService(db)

    result = await service.get_task_status(task_id)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message", "任务不存在"))

    return result
