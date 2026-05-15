"""底稿权限粒度服务 — 项目级/循环级/单底稿级 三层权限检查

Sprint 11 Task 11.1
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class WpPermissionService:
    """三层权限检查中间件"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_project_access(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> bool:
        """项目级权限：用户是否为项目组成员"""
        from app.models.project_models import ProjectAssignment
        stmt = select(ProjectAssignment).where(
            and_(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.user_id == user_id,
                ProjectAssignment.is_deleted == False,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def check_cycle_access(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        cycle: str,
    ) -> bool:
        """循环级权限：用户是否被分配到该业务循环"""
        # 项目级权限先通过
        if not await self.check_project_access(user_id=user_id, project_id=project_id):
            return False
        # 循环级：partner/manager/qc 可访问所有循环，auditor 只能访问分配的
        from app.models.project_models import ProjectAssignment
        stmt = select(ProjectAssignment).where(
            and_(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.user_id == user_id,
                ProjectAssignment.is_deleted == False,
            )
        )
        result = await self.db.execute(stmt)
        assignment = result.scalar_one_or_none()
        if not assignment:
            return False
        # 高权限角色可访问所有循环
        if assignment.role in ("partner", "manager", "qc", "eqcr", "admin"):
            return True
        # auditor 需要检查是否分配到该循环（通过底稿分配间接判断）
        return True  # Stub: 实际实现检查 workpaper_assignments

    async def check_workpaper_access(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
    ) -> bool:
        """单底稿级权限：用户是否有权访问该底稿"""
        # 先检查项目级
        if not await self.check_project_access(user_id=user_id, project_id=project_id):
            return False
        # partner/manager 可访问所有底稿
        from app.models.project_models import ProjectAssignment
        stmt = select(ProjectAssignment).where(
            and_(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.user_id == user_id,
                ProjectAssignment.is_deleted == False,
            )
        )
        result = await self.db.execute(stmt)
        assignment = result.scalar_one_or_none()
        if not assignment:
            return False
        if assignment.role in ("partner", "manager", "qc", "eqcr", "admin"):
            return True
        # auditor 检查底稿是否分配给自己
        return True  # Stub: 实际实现检查 wp_assignments

    async def require_access(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        wp_id: Optional[uuid.UUID] = None,
        cycle: Optional[str] = None,
    ) -> None:
        """统一权限检查入口，无权限抛 403"""
        if wp_id:
            ok = await self.check_workpaper_access(
                user_id=user_id, project_id=project_id, wp_id=wp_id
            )
        elif cycle:
            ok = await self.check_cycle_access(
                user_id=user_id, project_id=project_id, cycle=cycle
            )
        else:
            ok = await self.check_project_access(user_id=user_id, project_id=project_id)

        if not ok:
            raise HTTPException(403, "无权访问该资源")
