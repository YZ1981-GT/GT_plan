"""人员库服务

Phase 9 Task 1.2: 人员库 CRUD + 简历自动丰富
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff_models import ProjectAssignment, StaffMember

logger = logging.getLogger(__name__)


class StaffService:
    """全局人员库服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 列表（搜索、分页）
    # ------------------------------------------------------------------
    async def list_staff(
        self,
        search: str | None = None,
        department: str | None = None,
        partner_name: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[StaffMember], int]:
        q = sa.select(StaffMember).where(StaffMember.is_deleted == False)  # noqa: E712

        if search:
            like = f"%{search}%"
            q = q.where(
                sa.or_(
                    StaffMember.name.ilike(like),
                    StaffMember.employee_no.ilike(like),
                    StaffMember.specialty.ilike(like),
                )
            )
        if department:
            q = q.where(StaffMember.department == department)
        if partner_name:
            q = q.where(StaffMember.partner_name == partner_name)

        count_q = sa.select(sa.func.count()).select_from(q.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        q = q.order_by(StaffMember.employee_no).offset(offset).limit(limit)
        rows = (await self.db.execute(q)).scalars().all()
        return list(rows), total

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------
    async def create_staff(self, data: dict) -> StaffMember:
        staff = StaffMember(**data)
        self.db.add(staff)
        await self.db.flush()
        return staff

    # ------------------------------------------------------------------
    # 编辑
    # ------------------------------------------------------------------
    async def update_staff(self, staff_id: UUID, data: dict) -> StaffMember | None:
        result = await self.db.execute(
            sa.select(StaffMember).where(
                StaffMember.id == staff_id, StaffMember.is_deleted == False  # noqa
            )
        )
        staff = result.scalar_one_or_none()
        if not staff:
            return None
        for k, v in data.items():
            if v is not None and hasattr(staff, k):
                setattr(staff, k, v)
        await self.db.flush()
        return staff

    # ------------------------------------------------------------------
    # 获取单个
    # ------------------------------------------------------------------
    async def get_staff(self, staff_id: UUID) -> StaffMember | None:
        result = await self.db.execute(
            sa.select(StaffMember).where(
                StaffMember.id == staff_id, StaffMember.is_deleted == False  # noqa
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 自动简历（从 project_assignments 汇总）
    # ------------------------------------------------------------------
    async def get_resume(self, staff_id: UUID) -> dict:
        from app.models.core import Project

        q = (
            sa.select(
                ProjectAssignment.role,
                Project.name.label("project_name"),
                Project.client_name,
                Project.project_type,
                ProjectAssignment.assigned_cycles,
                ProjectAssignment.assigned_at,
            )
            .join(Project, ProjectAssignment.project_id == Project.id)
            .where(
                ProjectAssignment.staff_id == staff_id,
                ProjectAssignment.is_deleted == False,  # noqa
                Project.is_deleted == False,  # noqa
            )
            .order_by(ProjectAssignment.assigned_at.desc())
        )
        rows = (await self.db.execute(q)).all()

        industries: set[str] = set()
        audit_types: set[str] = set()
        recent: list[dict] = []

        for row in rows:
            if row.project_type:
                audit_types.add(row.project_type)
            if row.client_name:
                industries.add(row.client_name[:4])  # 简化：取客户名前4字作为行业标签
            recent.append({
                "project_name": row.project_name,
                "client_name": row.client_name,
                "role": row.role,
                "assigned_at": str(row.assigned_at) if row.assigned_at else None,
            })

        return {
            "total_projects": len(rows),
            "industries": sorted(industries),
            "audit_types": sorted(audit_types),
            "recent_projects": recent[:20],
        }

    # ------------------------------------------------------------------
    # 参与项目列表
    # ------------------------------------------------------------------
    async def get_projects(self, staff_id: UUID) -> list[dict]:
        from app.models.core import Project

        q = (
            sa.select(
                Project.id,
                Project.name,
                Project.client_name,
                Project.status,
                ProjectAssignment.role,
                ProjectAssignment.assigned_cycles,
                ProjectAssignment.assigned_at,
            )
            .join(Project, ProjectAssignment.project_id == Project.id)
            .where(
                ProjectAssignment.staff_id == staff_id,
                ProjectAssignment.is_deleted == False,  # noqa
                Project.is_deleted == False,  # noqa
            )
            .order_by(ProjectAssignment.assigned_at.desc())
        )
        rows = (await self.db.execute(q)).all()
        return [
            {
                "project_id": str(r.id),
                "project_name": r.name,
                "client_name": r.client_name,
                "status": r.status,
                "role": r.role,
                "assigned_cycles": r.assigned_cycles,
                "assigned_at": str(r.assigned_at) if r.assigned_at else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 简历自动丰富（项目归档时调用）
    # ------------------------------------------------------------------
    async def enrich_resume(self, staff_id: UUID) -> None:
        resume = await self.get_resume(staff_id)
        await self.db.execute(
            sa.update(StaffMember)
            .where(StaffMember.id == staff_id)
            .values(resume_data=resume)
        )
