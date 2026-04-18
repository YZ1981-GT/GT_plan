"""合并报表增强服务 — Phase 10 Task 7.1-7.3"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

logger = logging.getLogger(__name__)


class ConsolLockService:
    """合并锁定同步"""

    async def lock_project(
        self, db: AsyncSession, project_id: UUID, locked_by: UUID,
    ) -> dict[str, Any]:
        """锁定单体试算表"""
        await db.execute(sa.text(
            "UPDATE projects SET consol_lock = true, consol_lock_by = :by, "
            "consol_lock_at = :at WHERE id = :pid"
        ), {"by": str(locked_by), "at": datetime.utcnow(), "pid": str(project_id)})
        await db.flush()
        return {"locked": True, "project_id": str(project_id)}

    async def unlock_project(
        self, db: AsyncSession, project_id: UUID,
    ) -> dict[str, Any]:
        """解锁"""
        await db.execute(sa.text(
            "UPDATE projects SET consol_lock = false, consol_lock_by = NULL, "
            "consol_lock_at = NULL WHERE id = :pid"
        ), {"pid": str(project_id)})
        await db.flush()
        return {"locked": False, "project_id": str(project_id)}

    async def check_lock(
        self, db: AsyncSession, project_id: UUID,
    ) -> dict[str, Any]:
        """检查锁定状态"""
        result = await db.execute(sa.text(
            "SELECT consol_lock, consol_lock_by, consol_lock_at "
            "FROM projects WHERE id = :pid"
        ), {"pid": str(project_id)})
        row = result.first()
        if not row:
            return {"locked": False}
        return {
            "locked": bool(row.consol_lock) if row.consol_lock else False,
            "locked_by": str(row.consol_lock_by) if row.consol_lock_by else None,
            "locked_at": row.consol_lock_at.isoformat() if row.consol_lock_at else None,
        }


class ExternalReportImportService:
    """外部单位报表导入"""

    async def import_external_report(
        self, db: AsyncSession, project_id: UUID, data: dict[str, Any],
    ) -> dict[str, Any]:
        """导入其他审计师审计的单位报表"""
        # stub — 实际需解析 Excel 并写入 trial_balance
        return {
            "project_id": str(project_id),
            "imported": True,
            "message": "外部报表导入成功（stub）",
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
            name=f"临时项目-{module}-{datetime.utcnow().strftime('%Y%m%d%H%M')}",
            client_name="临时",
            manager_id=user_id,
        )
        # 标记为自动创建
        project.wizard_state = {"auto_created": True, "module": module}
        db.add(project)
        await db.flush()
        return {"project_id": str(project.id), "module": module, "auto_created": True}
