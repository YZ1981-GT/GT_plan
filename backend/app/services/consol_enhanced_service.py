"""合并报表增强服务 — Phase 10 Task 7.1-7.3

Phase 0 修复（consol-phase0-core-pipeline Task 8.2）：
ConsolLockService 改用 ORM select/update 替代裸 SQL（ADR-CONSOL-002）。
状态机不变量：
  locked  <=> consol_lock == True AND consol_lock_by != None AND consol_lock_at != None
  unlocked <=> consol_lock == False AND consol_lock_by == None AND consol_lock_at == None
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

logger = logging.getLogger(__name__)


class ConsolLockService:
    """合并锁定同步 — ORM 实现，保证状态机不变量（三字段原子设置）"""

    async def lock_project(
        self, db: AsyncSession, project_id: UUID, locked_by: UUID,
    ) -> dict[str, Any]:
        """锁定项目 — 原子设置三字段（consol_lock + consol_lock_by + consol_lock_at）"""
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if project is None:
            return {"locked": False, "project_id": str(project_id), "error": "项目不存在"}

        now = datetime.now(timezone.utc)
        project.consol_lock = True
        project.consol_lock_by = locked_by
        project.consol_lock_at = now
        await db.flush()
        return {
            "locked": True,
            "project_id": str(project_id),
            "locked_by": str(locked_by),
            "locked_at": now.isoformat(),
        }

    async def unlock_project(
        self, db: AsyncSession, project_id: UUID,
    ) -> dict[str, Any]:
        """解锁项目 — 原子清除三字段"""
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if project is None:
            return {"locked": False, "project_id": str(project_id), "error": "项目不存在"}

        project.consol_lock = False
        project.consol_lock_by = None
        project.consol_lock_at = None
        await db.flush()
        return {"locked": False, "project_id": str(project_id)}

    async def check_lock(
        self, db: AsyncSession, project_id: UUID,
    ) -> dict[str, Any]:
        """检查锁定状态 — 使用 ORM select"""
        result = await db.execute(
            select(
                Project.consol_lock,
                Project.consol_lock_by,
                Project.consol_lock_at,
            ).where(Project.id == project_id)
        )
        row = result.first()
        if not row:
            return {"locked": False}
        return {
            "locked": bool(row[0]) if row[0] else False,
            "locked_by": str(row[1]) if row[1] else None,
            "locked_at": row[2].isoformat() if row[2] else None,
        }


class IndependentModuleService:
    """独立模块使用"""

    async def create_temp_project(
        self, db: AsyncSession, module: str, user_id: UUID,
    ) -> dict[str, Any]:
        """创建临时项目（仅合并/报告复核/排版模块）"""
        valid_modules = {"consolidation", "report_review", "report_format"}
        if module not in valid_modules:
            raise ValueError(f"不支持的模块: {module}")
        project = Project(
            name=f"临时项目-{module}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
            client_name="临时",
            manager_id=user_id,
        )
        # 标记为自动创建
        project.wizard_state = {"auto_created": True, "module": module}
        db.add(project)
        await db.flush()
        return {"project_id": str(project.id), "module": module, "auto_created": True}
