"""项目级自定义附注模板 API（Sprint 3 Task 3.2）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.2
Design: D8 自定义模板存储与版本

提供 4 个端点：
- ``POST   /api/projects/{pid}/note-template/save``      保存当前 sections（产生 v{N+1}.json）
- ``GET    /api/projects/{pid}/note-template``           读当前主文件（含 history）
- ``POST   /api/projects/{pid}/note-template/restore``   回滚到指定历史版本（产生 v{N+1}.json）
- ``GET    /api/projects/{pid}/note-template/versions``  历史版本清单
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.note_custom_template_service import NoteCustomTemplateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["note-custom-template"])


# ---------------------------------------------------------------------------
# Pydantic 请求体
# ---------------------------------------------------------------------------


class SaveCustomTemplateRequest(BaseModel):
    sections: list[dict[str, Any]] = Field(
        default_factory=list,
        description="自定义 sections 数组；允许空 list（表示删除全部自定义）",
    )


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.post("/{project_id}/note-template/save")
async def save_custom_template(
    project_id: UUID,
    body: SaveCustomTemplateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """保存自定义模板（产生新版本 v{N+1}.json）."""
    svc = NoteCustomTemplateService(db)
    try:
        result = await svc.save_custom_template(
            project_id=project_id,
            sections=body.sections,
            updated_by=getattr(user, "id", None),
        )
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return result


@router.get("/{project_id}/note-template")
async def load_custom_template(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """读取当前自定义模板主文件；不存在返回 ``{}``."""
    svc = NoteCustomTemplateService(db)
    payload = await svc.load_custom_template(project_id)
    return payload or {}


@router.post("/{project_id}/note-template/restore")
async def restore_custom_template(
    project_id: UUID,
    version: int = Query(..., ge=1, description="目标历史版本号"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """回滚到指定历史版本（产生新版本，不覆盖历史快照）."""
    svc = NoteCustomTemplateService(db)
    try:
        result = await svc.restore_to_version(
            project_id=project_id,
            target_version=version,
            updated_by=getattr(user, "id", None),
        )
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return result


@router.get("/{project_id}/note-template/versions")
async def list_custom_template_versions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """历史版本清单；主文件不存在 → ``[]``."""
    svc = NoteCustomTemplateService(db)
    return await svc.list_versions(project_id)
