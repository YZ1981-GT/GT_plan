"""自然语言命令 API

提供自然语言指令解析和执行的 REST API。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.nl_command_service import NLCommandService

router = APIRouter(prefix="/api/ai/nl", tags=["AI-自然语言命令"])


class ParseIntentRequest(BaseModel):
    """解析意图请求"""
    user_input: str


class ParseIntentResponse(BaseModel):
    """解析意图响应"""
    intent_type: str
    params: dict[str, Any]
    confidence: float


class ExecuteCommandRequest(BaseModel):
    """执行命令请求"""
    intent: dict[str, Any]
    project_id: str


class AnalyzeFileRequest(BaseModel):
    """分析文件请求"""
    file_path: str
    project_id: str


class AnalyzeFolderRequest(BaseModel):
    """分析文件夹请求"""
    folder_path: str
    project_id: str


class ComparePBCRequest(BaseModel):
    """PBC 比较请求"""
    project_id: str


# ============ 意图解析 ============


@router.post("/parse", response_model=ParseIntentResponse)
async def parse_intent(request: ParseIntentRequest):
    """
    解析自然语言输入为结构化意图

    不需要数据库会话，快速响应。
    """
    from app.core.database import async_session_maker

    async with async_session_maker() as db:
        service = NLCommandService(db)
        result = await service.parse_intent(request.user_input)

    return ParseIntentResponse(
        intent_type=result.get("intent_type", "QUERY_DATA"),
        params=result.get("params", {}),
        confidence=result.get("confidence", 0.5),
    )


# ============ 命令执行 ============


@router.post("/execute")
async def execute_command(
    request: ExecuteCommandRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    执行已解析的命令

    需要认证和数据库会话。
    """
    from uuid import UUID

    service = NLCommandService(db)
    result = await service.execute_command(
        intent=request.intent,
        project_id=UUID(request.project_id),
        user_id=str(user.id),
        db=db,
    )

    return result


# ============ 文件分析 ============


@router.post("/analyze-file")
async def analyze_file(
    request: AnalyzeFileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    分析单个文件

    根据文件类型自动路由到 OCR 或合同分析。
    """
    from uuid import UUID

    service = NLCommandService(db)
    result = await service.analyze_file(
        file_path=request.file_path,
        project_id=UUID(request.project_id),
    )

    return result


# ============ 文件夹批量分析 ============


@router.post("/analyze-folder")
async def analyze_folder(
    request: AnalyzeFolderRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    批量分析文件夹中的文件

    返回 Celery 任务 ID 用于查询进度。
    """
    from uuid import UUID

    service = NLCommandService(db)
    result = await service.analyze_folder(
        folder_path=request.folder_path,
        project_id=UUID(request.project_id),
        user_id=str(user.id),
    )

    return result


@router.get("/analyze-folder/{task_id}")
async def get_folder_analysis_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    获取文件夹批量分析的任务状态

    通过 Celery 任务 ID 查询进度。
    """
    try:
        from celery.result import AsyncResult
        from app.tasks import celery_app

        result = AsyncResult(task_id, app=celery_app)

        return {
            "task_id": task_id,
            "status": result.status,
            "result": result.result if result.ready() else None,
        }
    except Exception as e:
        return {
            "task_id": task_id,
            "status": "ERROR",
            "error": str(e),
        }


# ============ PBC 清单比较 ============


@router.post("/compare-pbc")
async def compare_pbc_list(
    request: ComparePBCRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    比较 PBC 清单与实际上传文件

    标识缺失和多余的文件。
    """
    from uuid import UUID

    service = NLCommandService(db)
    result = await service.compare_pbc_list(
        project_id=UUID(request.project_id),
        user_id=str(user.id),
    )

    return result
