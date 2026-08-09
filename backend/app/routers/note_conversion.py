"""附注国企版与上市版互转端点

POST /api/projects/{pid}/notes/conversion/preview          — 报表行次影响预览
GET  /api/projects/{pid}/notes/conversion/{year}/preview   — 附注章节映射预览（只读）
POST /api/projects/{pid}/notes/conversion/execute          — 执行转换
POST /api/projects/{pid}/notes/conversion/rollback         — 撤销转换

Requirements: 47.1, 47.2, 47.3, 47.4, 47.5, 47.6, 47.7
spec soe-listed-note-conversion-correctness: Requirements 9.1, 9.2（章节映射预览）

🔴 路径口径说明：spec 的 design/tasks 写作
``GET /note-conversion/{project_id}/{year}/preview?target_type=``，那是**简写**
（同一份 spec 把既有执行入口写作 ``POST /note-conversion/execute``，其真实路径
是 ``POST /api/projects/{pid}/notes/conversion/execute``）。本端点挂在既有 router
的前缀下 ⇒ 形状 ``{project_id}/{year}/preview?target_type=`` 与 design 一致，
同时保持平台 ``/api/projects/{project_id}/...`` 的既有约定，不新建 router。
"""
from __future__ import annotations

import logging
from uuid import UUID

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
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


class NoteSectionPreviewResponse(BaseModel):
    """附注章节转换预览响应

    spec: soe-listed-note-conversion-correctness / Requirements 9.1, 9.2

    六个业务键按 design 的端点契约：``mapped`` / ``archived`` / ``created`` /
    ``user_edits_preserved`` / ``forbidden_hits`` / ``details``。
    """

    status: str = Field(..., description="preview / no_change")
    from_type: str = Field(..., description="当前模板类型")
    to_type: str = Field(..., description="目标模板类型")
    mapped: int = Field(0, description="将改写的章节数")
    archived: int = Field(0, description="将归档的章节数（源侧独有）")
    created: int = Field(0, description="将新建的空章节数（目标侧独有）")
    user_edits_preserved: int = Field(0, description="将保留的人工编辑单元格数")
    forbidden_hits: list[str] = Field(
        default_factory=list,
        description="命中禁止匹配对（故意不配对）的章节，供审计师核对",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="可追溯明细：skipped / failed / skipped_reasons / 别名桥接 / 禁止对",
    )


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
        raise HTTPException(status_code=400, detail={"message": "target_type 必须是 soe 或 listed", "message_en": "target_type must be 'soe' or 'listed'"})

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


@router.get("/{year}/preview", response_model=NoteSectionPreviewResponse)
async def preview_note_section_conversion(
    project_id: UUID,
    year: int,
    target_type: str = Query(..., description="目标类型 (soe/listed)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """附注**章节映射**预览：将改写 X 个 / 归档 Y 个 / 新建 Z 个 / 保留 N 处人工编辑。

    spec: soe-listed-note-conversion-correctness / Requirements 9.1, 9.2

    与上方 ``POST /preview`` 的分工：那个是**报表行次**口径（added/removed/preserved
    行名计数，Requirement 47.4 的历史入口）；本端点是**附注章节**口径，且**复用
    真实执行的同一个映射函数** ``_map_disclosure_notes`` —— savepoint 内真跑一遍
    再显式回滚，故预览计数与真实执行计数由构造保证相等，不存在「另写一份只读版
    映射逻辑」导致的预览与实际漂移。

    **不产生任何写入**（Requirement 9.2），也不改
    ``template_type`` / ``report_scope`` / ``applicable_standard_v2``（Requirement 10.6）。
    """
    if target_type not in ("soe", "listed"):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "target_type 必须是 soe 或 listed",
                "message_en": "target_type must be 'soe' or 'listed'",
            },
        )

    from app.services.note_conversion_service import NoteConversionService

    service = NoteConversionService(db)
    try:
        payload = await service.preview_note_conversion(
            project_id=project_id,
            year=year,
            target_type=target_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(
            "Note section conversion preview failed for project %s year %s",
            project_id,
            year,
        )
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")

    return NoteSectionPreviewResponse(**payload)


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
        raise HTTPException(status_code=400, detail={"message": "target_type 必须是 soe 或 listed", "message_en": "target_type must be 'soe' or 'listed'"})

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
