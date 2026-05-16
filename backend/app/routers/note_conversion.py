"""附注国企版与上市版互转端点

POST /api/projects/{pid}/notes/conversion/preview  — 转换影响预览
POST /api/projects/{pid}/notes/conversion/execute  — 执行转换
POST /api/projects/{pid}/notes/conversion/rollback — 撤销转换

Requirements: 47.1, 47.2, 47.3, 47.4, 47.5, 47.6, 47.7
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/notes/conversion",
    tags=["note-conversion"],
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ConversionPreviewRequest(BaseModel):
    """转换预览请求"""
    year: int = Field(..., description="年度")
    target_type: str = Field(..., description="目标类型 (soe/listed)")


class ConversionPreviewResponse(BaseModel):
    """转换预览响应"""
    added: int = Field(0, description="将新增的行次/章节数")
    removed: int = Field(0, description="将删除的行次/章节数")
    preserved: int = Field(0, description="将保留的行次/章节数")
    added_items: list[str] = Field(default_factory=list, description="新增项列表")
    removed_items: list[str] = Field(default_factory=list, description="删除项列表")


class ConversionExecuteRequest(BaseModel):
    """执行转换请求"""
    year: int = Field(..., description="年度")
    target_type: str = Field(..., description="目标类型 (soe/listed)")


class ConversionRollbackRequest(BaseModel):
    """撤销转换请求"""
    year: int = Field(..., description="年度")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/preview", response_model=ConversionPreviewResponse)
async def preview_conversion(
    project_id: UUID,
    body: ConversionPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """预览转换影响（新增/删除/保留数量）

    Requirements: 47.4
    """
    if body.target_type not in ("soe", "listed"):
        raise HTTPException(status_code=400, detail="target_type must be 'soe' or 'listed'")

    from app.services.note_conversion_service import NoteConversionService

    service = NoteConversionService(db)
    try:
        preview = await service.preview_conversion(
            project_id=project_id,
            year=body.year,
            target_type=body.target_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Conversion preview failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")

    return ConversionPreviewResponse(**preview.to_dict())


@router.post("/execute")
async def execute_conversion(
    project_id: UUID,
    body: ConversionExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行国企版↔上市版转换

    Steps:
    1. 保存转换前快照（30 天内可回退）
    2. 更新 project.template_type
    3. 映射报表行次 row_codes
    4. 映射附注章节（保留已填充数据）
    5. 更新公式中的 row_code 引用
    6. 自动执行全链路刷新

    Requirements: 47.2, 47.3, 47.5, 47.6
    """
    if body.target_type not in ("soe", "listed"):
        raise HTTPException(status_code=400, detail="target_type must be 'soe' or 'listed'")

    from app.services.note_conversion_service import NoteConversionService

    service = NoteConversionService(db)
    try:
        result = await service.execute_conversion(
            project_id=project_id,
            year=body.year,
            target_type=body.target_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Conversion execution failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")

    return result


@router.post("/rollback")
async def rollback_conversion(
    project_id: UUID,
    body: ConversionRollbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """撤销最近一次转换（从快照恢复）

    快照保留 30 天，超过后无法回退。

    Requirements: 47.5
    """
    from app.services.note_conversion_service import NoteConversionService

    service = NoteConversionService(db)
    try:
        result = await service.rollback_conversion(
            project_id=project_id,
            year=body.year,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Conversion rollback failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Rollback failed"))

    return result
