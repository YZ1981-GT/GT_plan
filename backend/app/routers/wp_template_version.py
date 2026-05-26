"""底稿模板版本查询端点

GET /api/wp-template-versions          — 列出所有模板版本（按 release_date DESC）
GET /api/wp-template-versions/current  — 获取当前活跃版本（is_current=TRUE）

Requirements: 3.0.4
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.wp_template_version_service import WpTemplateVersionService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/wp-template-versions",
    tags=["wp-template-versions"],
)


# ─── Response schemas ────────────────────────────────────────────────────────


class TemplateVersionItem(BaseModel):
    id: UUID
    version: str
    release_date: date
    source: str
    is_current: bool
    changelog: str | None = None
    created_at: datetime


class TemplateVersionsResponse(BaseModel):
    versions: list[TemplateVersionItem]


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/current", response_model=TemplateVersionItem)
async def get_current_template_version(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前活跃模板版本（is_current=TRUE）。

    EARS:
    - WHEN 存在 is_current=TRUE 的版本 THEN 返回该版本详情
    - IF 不存在 THEN 返回 404
    """
    service = WpTemplateVersionService(db)
    version = await service.get_current_version()

    return TemplateVersionItem(
        id=version.id,
        version=version.version,
        release_date=version.release_date,
        source=version.source,
        is_current=version.is_current,
        changelog=version.changelog,
        created_at=version.created_at,
    )


@router.get("", response_model=TemplateVersionsResponse)
async def list_template_versions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出所有模板版本，按 release_date 降序排列。

    EARS:
    - WHEN 请求列表 THEN 返回所有版本（最新在前）
    - IF 无版本记录 THEN 返回空列表
    """
    service = WpTemplateVersionService(db)
    versions = await service.list_versions()

    return TemplateVersionsResponse(
        versions=[
            TemplateVersionItem(
                id=v.id,
                version=v.version,
                release_date=v.release_date,
                source=v.source,
                is_current=v.is_current,
                changelog=v.changelog,
                created_at=v.created_at,
            )
            for v in versions
        ]
    )
