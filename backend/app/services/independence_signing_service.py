"""A17-7 独立性声明书电子签署服务

为项目成员创建签署任务，跟踪签署进度，
A17-7A 按角色推送专委会委员。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_workflow_models import IndependenceSigningTask


class IndependenceSigningService:
    """独立性声明书电子签署"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def initiate_signing(
        self, project_id: UUID, template_code: str = "A17-7"
    ) -> dict[str, Any]:
        """为项目所有成员创建签署任务"""
        members = await self._get_project_members(project_id)
        created = 0
        for member_id in members:
            exists = await self._task_exists(project_id, member_id, template_code)
            if not exists:
                task = IndependenceSigningTask(
                    project_id=project_id,
                    user_id=member_id,
                    template_code=template_code,
                    status="pending",
                )
                self.db.add(task)
                created += 1
        await self.db.flush()
        return {"created": created, "total_members": len(members)}

    async def initiate_signing_for_committee(
        self, project_id: UUID
    ) -> dict[str, Any]:
        """A17-7A: 按角色推送专委会委员"""
        committee_members = await self._get_committee_members(project_id)
        created = 0
        for member_id in committee_members:
            exists = await self._task_exists(project_id, member_id, "A17-7A")
            if not exists:
                task = IndependenceSigningTask(
                    project_id=project_id,
                    user_id=member_id,
                    template_code="A17-7A",
                    status="pending",
                )
                self.db.add(task)
                created += 1
        await self.db.flush()
        return {"created": created, "total_committee": len(committee_members)}

    async def sign(self, project_id: UUID, user_id: UUID, template_code: str = "A17-7") -> dict[str, Any]:
        """成员电子签署"""
        stmt = sa.select(IndependenceSigningTask).where(
            IndependenceSigningTask.project_id == project_id,
            IndependenceSigningTask.user_id == user_id,
            IndependenceSigningTask.template_code == template_code,
        )
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            return {"success": False, "error": "未找到签署任务"}
        if task.status == "signed":
            return {"success": False, "error": "已签署，无需重复操作"}

        task.status = "signed"
        task.signed_at = datetime.now(timezone.utc)
        await self.db.flush()

        # SSE 通知签署进度更新
        try:
            from app.core.event_bus import event_bus
            event_bus.broadcast_raw(
                "signing_progress_updated",
                {"project_id": str(project_id), "template_code": template_code, "user_id": str(user_id)},
            )
        except Exception:
            pass

        return {"success": True}

    async def get_signing_progress(
        self, project_id: UUID, template_code: str = "A17-7"
    ) -> dict[str, Any]:
        """获取签署进度"""
        stmt = sa.select(IndependenceSigningTask).where(
            IndependenceSigningTask.project_id == project_id,
            IndependenceSigningTask.template_code == template_code,
        )
        result = await self.db.execute(stmt)
        tasks = result.scalars().all()

        total = len(tasks)
        signed = sum(1 for t in tasks if t.status == "signed")
        pending = [
            {"user_id": str(t.user_id), "created_at": t.created_at.isoformat() if t.created_at else None}
            for t in tasks if t.status == "pending"
        ]
        signed_list = [
            {"user_id": str(t.user_id), "signed_at": t.signed_at.isoformat() if t.signed_at else None}
            for t in tasks if t.status == "signed"
        ]

        return {
            "total": total,
            "signed": signed,
            "pending_count": total - signed,
            "complete": signed == total and total > 0,
            "pending": pending,
            "signed_list": signed_list,
        }

    async def get_my_pending_tasks(self, user_id: UUID) -> list[dict[str, Any]]:
        """获取当前用户待签署的任务列表"""
        stmt = sa.select(IndependenceSigningTask).where(
            IndependenceSigningTask.user_id == user_id,
            IndependenceSigningTask.status == "pending",
        )
        result = await self.db.execute(stmt)
        tasks = result.scalars().all()
        return [
            {
                "id": str(t.id),
                "project_id": str(t.project_id),
                "template_code": t.template_code,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_project_members(self, project_id: UUID) -> list[UUID]:
        """获取项目所有成员 user_id"""
        from app.models.audit_platform_models import ProjectAssignment
        stmt = sa.select(ProjectAssignment.staff_id).where(
            ProjectAssignment.project_id == project_id,
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def _get_committee_members(self, project_id: UUID) -> list[UUID]:
        """获取专委会委员（quality_reviewer + eqcr 角色）"""
        from app.models.audit_platform_models import ProjectAssignment
        stmt = sa.select(ProjectAssignment.staff_id).where(
            ProjectAssignment.project_id == project_id,
            ProjectAssignment.role.in_(["quality_reviewer", "eqcr"]),
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def _task_exists(self, project_id: UUID, user_id: UUID, template_code: str) -> bool:
        stmt = sa.select(sa.func.count()).select_from(IndependenceSigningTask).where(
            IndependenceSigningTask.project_id == project_id,
            IndependenceSigningTask.user_id == user_id,
            IndependenceSigningTask.template_code == template_code,
        )
        result = await self.db.execute(stmt)
        return (result.scalar() or 0) > 0
