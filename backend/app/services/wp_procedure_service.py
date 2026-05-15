"""底稿审计程序管理服务

Sprint 2 Task 2.1: CRUD + 裁剪 + 完成标记 + 完成率计算
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wp_optimization_models import WorkpaperProcedure

logger = logging.getLogger(__name__)


class WpProcedureService:
    """审计程序管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 查询 ────────────────────────────────────────────────────────────────

    async def list_procedures(
        self,
        wp_id: UUID,
        *,
        include_trimmed: bool = False,
    ) -> list[dict]:
        """获取底稿程序清单（含裁剪状态）"""
        conditions = [WorkpaperProcedure.wp_id == wp_id]
        if not include_trimmed:
            conditions.append(WorkpaperProcedure.status != "not_applicable")

        q = (
            sa.select(WorkpaperProcedure)
            .where(*conditions)
            .order_by(WorkpaperProcedure.sort_order, WorkpaperProcedure.created_at)
        )
        rows = (await self.db.execute(q)).scalars().all()
        return [self._to_dict(r) for r in rows]

    # ─── 完成标记 ─────────────────────────────────────────────────────────────

    async def mark_complete(
        self,
        proc_id: UUID,
        user_id: UUID,
    ) -> dict | None:
        """标记程序完成"""
        proc = await self._get_by_id(proc_id)
        if not proc:
            return None

        proc.status = "completed"
        proc.completed_by = user_id
        proc.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return self._to_dict(proc)

    # ─── 裁剪 ─────────────────────────────────────────────────────────────────

    async def trim_procedure(
        self,
        proc_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> dict | None:
        """裁剪程序（经理/合伙人权限）

        必做项不可裁剪。
        """
        proc = await self._get_by_id(proc_id)
        if not proc:
            return None

        if proc.is_mandatory:
            raise ValueError("必做程序不可裁剪")

        proc.status = "not_applicable"
        proc.trimmed_by = user_id
        proc.trimmed_at = datetime.now(timezone.utc)
        proc.trim_reason = reason
        await self.db.flush()
        return self._to_dict(proc)

    # ─── 自定义程序 ───────────────────────────────────────────────────────────

    async def create_custom(
        self,
        wp_id: UUID,
        project_id: UUID,
        description: str,
        category: str = "custom",
        evidence_type: Optional[str] = None,
    ) -> dict:
        """新增自定义程序"""
        # 获取当前最大 sort_order
        q = sa.select(sa.func.max(WorkpaperProcedure.sort_order)).where(
            WorkpaperProcedure.wp_id == wp_id
        )
        max_order = (await self.db.execute(q)).scalar() or 0

        proc = WorkpaperProcedure(
            id=uuid.uuid4(),
            wp_id=wp_id,
            project_id=project_id,
            procedure_id=f"CUSTOM-{uuid.uuid4().hex[:6].upper()}",
            description=description,
            category=category,
            is_mandatory=False,
            evidence_type=evidence_type,
            status="pending",
            sort_order=max_order + 1,
        )
        self.db.add(proc)
        await self.db.flush()
        return self._to_dict(proc)

    # ─── 从上年复制 ───────────────────────────────────────────────────────────

    async def copy_from_prior(
        self,
        wp_id: UUID,
        project_id: UUID,
        prior_wp_id: UUID,
    ) -> list[dict]:
        """从上年底稿复制程序清单结构到本年"""
        # 查询上年程序
        q = (
            sa.select(WorkpaperProcedure)
            .where(WorkpaperProcedure.wp_id == prior_wp_id)
            .order_by(WorkpaperProcedure.sort_order)
        )
        prior_procs = (await self.db.execute(q)).scalars().all()

        new_procs = []
        for p in prior_procs:
            new_proc = WorkpaperProcedure(
                id=uuid.uuid4(),
                wp_id=wp_id,
                project_id=project_id,
                procedure_id=p.procedure_id,
                description=p.description,
                category=p.category,
                is_mandatory=p.is_mandatory,
                applicable_project_types=p.applicable_project_types,
                depends_on=p.depends_on,
                evidence_type=p.evidence_type,
                status="pending",
                sort_order=p.sort_order,
            )
            self.db.add(new_proc)
            new_procs.append(new_proc)

        await self.db.flush()
        return [self._to_dict(p) for p in new_procs]

    # ─── 完成率计算 ───────────────────────────────────────────────────────────

    async def calc_completion_rate(self, wp_id: UUID) -> float:
        """程序完成率 = 已完成数 / (总数 - 不适用数)

        返回 0.0 ~ 1.0 之间的浮点数。
        """
        q = sa.select(
            sa.func.count(WorkpaperProcedure.id).label("total"),
            sa.func.count(
                sa.case(
                    (WorkpaperProcedure.status == "completed", WorkpaperProcedure.id),
                )
            ).label("completed"),
            sa.func.count(
                sa.case(
                    (WorkpaperProcedure.status == "not_applicable", WorkpaperProcedure.id),
                )
            ).label("not_applicable"),
        ).where(WorkpaperProcedure.wp_id == wp_id)

        row = (await self.db.execute(q)).one()
        total = row.total
        completed = row.completed
        not_applicable = row.not_applicable

        denominator = total - not_applicable
        if denominator <= 0:
            return 0.0

        return round(completed / denominator, 4)

    # ─── 内部方法 ─────────────────────────────────────────────────────────────

    async def _get_by_id(self, proc_id: UUID) -> WorkpaperProcedure | None:
        q = sa.select(WorkpaperProcedure).where(WorkpaperProcedure.id == proc_id)
        return (await self.db.execute(q)).scalar_one_or_none()

    @staticmethod
    def _to_dict(proc: WorkpaperProcedure) -> dict:
        return {
            "id": str(proc.id),
            "wp_id": str(proc.wp_id),
            "project_id": str(proc.project_id),
            "procedure_id": proc.procedure_id,
            "description": proc.description,
            "category": proc.category,
            "is_mandatory": proc.is_mandatory,
            "applicable_project_types": proc.applicable_project_types,
            "depends_on": proc.depends_on,
            "evidence_type": proc.evidence_type,
            "status": proc.status,
            "completed_by": str(proc.completed_by) if proc.completed_by else None,
            "completed_at": proc.completed_at.isoformat() if proc.completed_at else None,
            "trimmed_by": str(proc.trimmed_by) if proc.trimmed_by else None,
            "trimmed_at": proc.trimmed_at.isoformat() if proc.trimmed_at else None,
            "trim_reason": proc.trim_reason,
            "sort_order": proc.sort_order,
            "created_at": proc.created_at.isoformat() if proc.created_at else None,
        }
