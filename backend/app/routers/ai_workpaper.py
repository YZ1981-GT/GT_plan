"""AI 底稿填充路由

提供底稿 AI 填充任务的创建、查询和管理接口。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.workpaper_fill_service import WorkpaperFillService
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai/workpaper", tags=["AI-底稿填充"])

# 请求模型
_fill_template_types = [
    "description",
    "calculation",
    "verification",
    "anomaly",
    "conclusion",
]


class FillTaskCreate(BaseModel):
    """创建填充任务"""
    project_id: str
    workpaper_id: str
    workpaper_item_id: Optional[str] = None
    template_type: str
    context_data: dict[str, Any]
    fill_mode: str = "auto"


class FillTaskResponse(BaseModel):
    """填充任务响应"""
    task_id: str
    status: str
    template_type: str
    fill_mode: str
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[Any] = None
    started_at: Optional[Any] = None
    completed_at: Optional[Any] = None


class FillResultResponse(BaseModel):
    """填充结果响应"""
    task_id: str
    filled_content: str
    confidence: float
    model_used: str
    token_usage: dict[str, Any]
    processing_time: float


def _get_fill_service(db: AsyncSession = Depends(get_db)) -> WorkpaperFillService:
    return WorkpaperFillService(db)


def _get_ai_service(db: AsyncSession = Depends(get_db)) -> AIService:
    return AIService(db)


@router.post("/tasks")
async def create_fill_task(
    task_data: FillTaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    创建并执行底稿填充任务

    Args:
        task_data: 任务配置，包含项目ID、底稿ID、模板类型、上下文数据

    Returns:
        任务 ID、状态和填充结果
    """
    if task_data.template_type not in _fill_template_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的模板类型: {task_data.template_type}，支持: {_fill_template_types}",
        )

    from uuid import UUID

    service = WorkpaperFillService(db)

    task = await service.create_fill_task(
        project_id=UUID(task_data.project_id),
        workpaper_id=task_data.workpaper_id,
        workpaper_item_id=task_data.workpaper_item_id,
        template_type=task_data.template_type,
        context_data=task_data.context_data,
        fill_mode=task_data.fill_mode,
        user_id=str(user.id),
    )

    # 立即执行任务（同步模式）
    ai_service = AIService(db)
    try:
        fill_result = await service.execute_fill_task(task.id, ai_service)
        await db.refresh(task)
        return {
            "task_id": str(task.id),
            "status": task.status,
            "result": {
                "filled_content": fill_result.filled_content,
                "confidence": fill_result.confidence,
                "model_used": fill_result.model_used,
            },
        }
    except Exception as e:
        logger.exception(f"Fill task execution failed")
        return {
            "task_id": str(task.id),
            "status": "failed",
            "error": str(e),
        }


@router.get("/tasks/{task_id}")
async def get_fill_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """获取填充任务详情"""
    from uuid import UUID

    service = WorkpaperFillService(db)
    task = await service.get_task(UUID(task_id))

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "task_id": str(task.id),
        "status": task.status,
        "template_type": task.template_type,
        "fill_mode": task.fill_mode,
        "result_summary": task.result_summary,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.get("/tasks/{task_id}/result")
async def get_fill_result(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """获取填充结果"""
    from uuid import UUID

    service = WorkpaperFillService(db)
    fill = await service.get_fill_result(UUID(task_id))

    if not fill:
        raise HTTPException(status_code=404, detail="填充结果不存在")

    return {
        "task_id": str(fill.task_id),
        "filled_content": fill.filled_content,
        "confidence": fill.confidence,
        "model_used": fill.model_used,
        "token_usage": fill.token_usage or {},
        "processing_time": fill.processing_time,
    }


@router.get("/tasks")
async def list_fill_tasks(
    project_id: str,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """列出项目的填充任务"""
    from uuid import UUID

    service = WorkpaperFillService(db)
    tasks = await service.list_tasks(
        project_id=UUID(project_id),
        status=status,
        skip=skip,
        limit=limit,
    )

    return [
        {
            "task_id": str(t.id),
            "status": t.status,
            "template_type": t.template_type,
            "fill_mode": t.fill_mode,
            "result_summary": t.result_summary,
            "error_message": t.error_message,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in tasks
    ]


from uuid import UUID

from app.services.ai_content_service import AIContentService
from app.models.ai_models import AIContent


class AnalyticalReviewRequest(BaseModel):
    project_id: str
    account_code: str
    year: str


class NoteDraftRequest(BaseModel):
    project_id: str
    note_section: str  # 资产类/负债类/权益类/损益类/重要会计政策/或有事项/关联披露


class WorkpaperReviewRequest(BaseModel):
    project_id: str
    workpaper_id: str


@router.post("/analytical-review")
async def create_analytical_review(
    req: AnalyticalReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """生成分析性复核"""
    service = WorkpaperFillService(db)
    ai_service = AIService(db)
    result = await service.generate_analytical_review(
        project_id=UUID(req.project_id),
        account_code=req.account_code,
        year=req.year,
        ai_service=ai_service,
    )
    return {"success": True, "data": result}


@router.post("/note-draft")
async def create_note_draft(
    req: NoteDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """生成附注初稿"""
    service = WorkpaperFillService(db)
    ai_service = AIService(db)
    result = await service.generate_note_draft(
        project_id=UUID(req.project_id),
        note_section=req.note_section,
        ai_service=ai_service,
    )
    return {"success": True, "data": result}


@router.post("/workpaper-review")
async def create_workpaper_review(
    req: WorkpaperReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提示词驱动的底稿AI智能复核"""
    service = WorkpaperFillService(db)
    ai_service = AIService(db)
    result = await service.review_workpaper_with_prompt(
        project_id=UUID(req.project_id),
        workpaper_id=UUID(req.workpaper_id),
        ai_service=ai_service,
    )
    return {"success": True, "data": result}


# --- AI Content management endpoints ---


@router.get("/projects/{project_id}/ai-content")
async def list_ai_content(
    project_id: str,
    workpaper_id: Optional[str] = None,
    content_type: Optional[str] = None,
    confirmation_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI内容列表"""
    from sqlalchemy import select

    query = select(AIContent).where(
        AIContent.project_id == UUID(project_id),
        AIContent.is_deleted == False  # noqa: E712
    )
    if workpaper_id:
        query = query.where(AIContent.workpaper_id == UUID(workpaper_id))
    if content_type:
        query = query.where(AIContent.content_type == content_type)
    if confirmation_status:
        query = query.where(AIContent.confirmation_status == confirmation_status)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "content_type": i.content_type,
            "content_text": i.content_text,
            "confirmation_status": i.confirmation_status,
            "confidence_level": i.confidence_level,
            "generation_time": i.generation_time.isoformat() if i.generation_time else None,
        }
        for i in items
    ]


class ConfirmRequest(BaseModel):
    action: str  # accept / modify / reject / regenerate
    modification_note: Optional[str] = None


@router.put("/projects/{project_id}/ai-content/{content_id}/confirm")
async def confirm_ai_content(
    project_id: str,
    content_id: str,
    req: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """确认AI内容"""
    service = AIContentService(db)
    result = await service.confirm_content(
        content_id=UUID(content_id),
        user_id=user.id,
        action=req.action,
        modification_note=req.modification_note,
    )
    return {"success": True, "data": {"id": str(result.id), "confirmation_status": result.confirmation_status}}


@router.get("/projects/{project_id}/ai-content/summary")
async def get_ai_content_summary(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI内容汇总统计"""
    service = AIContentService(db)
    summary = await service.get_project_summary(UUID(project_id))
    return {"success": True, "data": summary}


@router.get("/projects/{project_id}/ai-content/pending-count")
async def get_pending_count(
    project_id: str,
    workpaper_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """未确认AI内容数量"""
    service = AIContentService(db)
    count = await service.get_pending_count(
        project_id=UUID(project_id),
        workpaper_id=UUID(workpaper_id) if workpaper_id else None,
    )
    return {"success": True, "pending_count": count}
