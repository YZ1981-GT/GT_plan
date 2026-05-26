"""底稿模板版本管理服务

管理致同底稿模板版本（v2024 → v2025 → v2026 年度修订），支持多版本共存。
Requirements: 3.0.4（模板版本管理）
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_template_version import WorkpaperTemplateVersion

logger = logging.getLogger(__name__)


class WpTemplateVersionService:
    """底稿模板版本服务

    提供模板版本的查询能力：
    - get_current_version: 获取当前活跃版本（is_current=TRUE）
    - list_versions: 列出所有版本（按 release_date DESC）
    - get_version_by_id: 按 ID 获取指定版本
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_current_version(self) -> WorkpaperTemplateVersion:
        """获取当前活跃模板版本（is_current=TRUE）。

        Returns:
            当前活跃的 WorkpaperTemplateVersion 记录

        Raises:
            HTTPException 404: 没有找到 is_current=TRUE 的版本记录
        """
        query = sa.select(WorkpaperTemplateVersion).where(
            WorkpaperTemplateVersion.is_current == True  # noqa: E712
        )
        result = await self.db.execute(query)
        version = result.scalars().first()

        if version is None:
            logger.error("No current template version found (is_current=TRUE)")
            raise HTTPException(
                status_code=404,
                detail="当前没有活跃的模板版本（is_current=TRUE），请联系管理员初始化模板版本数据。",
            )

        return version

    async def list_versions(self) -> list[WorkpaperTemplateVersion]:
        """列出所有模板版本，按 release_date 降序排列。

        Returns:
            WorkpaperTemplateVersion 列表（最新版本在前）
        """
        query = (
            sa.select(WorkpaperTemplateVersion)
            .order_by(WorkpaperTemplateVersion.release_date.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_version_by_id(self, version_id: UUID) -> WorkpaperTemplateVersion:
        """按 ID 获取指定模板版本。

        Args:
            version_id: 模板版本 UUID

        Returns:
            对应的 WorkpaperTemplateVersion 记录

        Raises:
            HTTPException 404: 指定 ID 的版本不存在
        """
        query = sa.select(WorkpaperTemplateVersion).where(
            WorkpaperTemplateVersion.id == version_id
        )
        result = await self.db.execute(query)
        version = result.scalars().first()

        if version is None:
            logger.warning(f"Template version not found: {version_id}")
            raise HTTPException(
                status_code=404,
                detail=f"模板版本不存在：{version_id}",
            )

        return version
