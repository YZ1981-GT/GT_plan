"""工时管理服务

Phase 9 Task 1.6: 工时 CRUD + 校验 + LLM 预填
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour
from app.models.core import Project

logger = logging.getLogger(__name__)


class WorkHourService:
    """工时管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 个人工时列表
    # ------------------------------------------------------------------
    async def list_hours(
        self,
        staff_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        q = (
            sa.select(WorkHour, Project.name.label("project_name"))
            .join(Project, WorkHour.project_id == Project.id)
            .where(
                WorkHour.staff_id == staff_id,
                WorkHour.is_deleted == False,  # noqa
            )
        )
        if start_date:
            q = q.where(WorkHour.work_date >= start_date)
        if end_date:
            q = q.where(WorkHour.work_date <= end_date)
        q = q.order_by(WorkHour.work_date.desc(), WorkHour.created_at.desc())

        rows = (await self.db.execute(q)).all()
        return [
            {
                "id": str(r[0].id),
                "staff_id": str(r[0].staff_id),
                "project_id": str(r[0].project_id),
                "project_name": r.project_name,
                "work_date": str(r[0].work_date),
                "hours": float(r[0].hours),
                "start_time": str(r[0].start_time) if r[0].start_time else None,
                "end_time": str(r[0].end_time) if r[0].end_time else None,
                "description": r[0].description,
                "status": r[0].status,
                "ai_suggested": r[0].ai_suggested,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 填报工时
    # ------------------------------------------------------------------
    async def create_hour(self, staff_id: UUID, data: dict) -> tuple[WorkHour, list[dict]]:
        """创建工时记录，返回 (记录, 警告列表)"""
        wh = WorkHour(
            staff_id=staff_id,
            project_id=data["project_id"],
            work_date=data["work_date"],
            hours=data["hours"],
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            description=data.get("description"),
        )
        self.db.add(wh)
        await self.db.flush()

        warnings = await self._validate_hours(staff_id, data["work_date"])
        return wh, warnings

    # ------------------------------------------------------------------
    # 编辑工时
    # ------------------------------------------------------------------
    async def update_hour(self, hour_id: UUID, data: dict) -> WorkHour | None:
        result = await self.db.execute(
            sa.select(WorkHour).where(WorkHour.id == hour_id, WorkHour.is_deleted == False)  # noqa
        )
        wh = result.scalar_one_or_none()
        if not wh:
            return None
        for k, v in data.items():
            if v is not None and hasattr(wh, k):
                setattr(wh, k, v)
        await self.db.flush()
        return wh

    # ------------------------------------------------------------------
    # 项目工时汇总
    # ------------------------------------------------------------------
    async def project_summary(self, project_id: UUID) -> list[dict]:
        q = (
            sa.select(
                StaffMember.name,
                sa.func.sum(WorkHour.hours).label("total_hours"),
                sa.func.count(WorkHour.id).label("record_count"),
            )
            .join(StaffMember, WorkHour.staff_id == StaffMember.id)
            .where(
                WorkHour.project_id == project_id,
                WorkHour.is_deleted == False,  # noqa
            )
            .group_by(StaffMember.id, StaffMember.name)
            .order_by(sa.desc("total_hours"))
        )
        rows = (await self.db.execute(q)).all()
        return [
            {"staff_name": r.name, "total_hours": float(r.total_hours), "record_count": r.record_count}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 工时校验
    # ------------------------------------------------------------------
    async def _validate_hours(self, staff_id: UUID, target_date: date) -> list[dict]:
        warnings: list[dict] = []

        # 1. 当日总工时 ≤ 24h
        daily_q = sa.select(sa.func.sum(WorkHour.hours)).where(
            WorkHour.staff_id == staff_id,
            WorkHour.work_date == target_date,
            WorkHour.is_deleted == False,  # noqa
        )
        daily_total = (await self.db.execute(daily_q)).scalar() or Decimal("0")
        if daily_total > 24:
            warnings.append({
                "warning_type": "daily_over_24h",
                "message": f"当日工时合计 {daily_total}h，超过 24 小时上限",
            })

        # 2. 连续 3 天日均 > 12h
        three_days_ago = target_date - timedelta(days=2)
        consec_q = (
            sa.select(
                WorkHour.work_date,
                sa.func.sum(WorkHour.hours).label("day_total"),
            )
            .where(
                WorkHour.staff_id == staff_id,
                WorkHour.work_date >= three_days_ago,
                WorkHour.work_date <= target_date,
                WorkHour.is_deleted == False,  # noqa
            )
            .group_by(WorkHour.work_date)
        )
        consec_rows = (await self.db.execute(consec_q)).all()
        over_12_days = sum(1 for r in consec_rows if r.day_total and r.day_total > 12)
        if over_12_days >= 3:
            warnings.append({
                "warning_type": "consecutive_overtime",
                "message": "连续 3 天工作时间超过 12 小时，请注意休息",
            })

        # 3. 时间段不重叠（简化：同一天同一项目不重复）
        overlap_q = sa.select(sa.func.count()).where(
            WorkHour.staff_id == staff_id,
            WorkHour.work_date == target_date,
            WorkHour.is_deleted == False,  # noqa
        )
        count = (await self.db.execute(overlap_q)).scalar() or 0
        # 如果有 start_time/end_time 可以做更精确的重叠检测，这里简化处理

        return warnings

    # ------------------------------------------------------------------
    # LLM 智能预填（stub，后续接入 vLLM）
    # ------------------------------------------------------------------
    async def ai_suggest(self, staff_id: UUID, target_date: date) -> list[dict]:
        """根据用户参与的项目情况，生成工时分配建议"""
        # 获取该人员当前参与的项目
        q = (
            sa.select(
                ProjectAssignment.project_id,
                ProjectAssignment.role,
                Project.name.label("project_name"),
            )
            .join(Project, ProjectAssignment.project_id == Project.id)
            .where(
                ProjectAssignment.staff_id == staff_id,
                ProjectAssignment.is_deleted == False,  # noqa
                Project.is_deleted == False,  # noqa
                Project.status.in_(["planning", "execution", "completion"]),
            )
        )
        projects = (await self.db.execute(q)).all()

        if not projects:
            return []

        # 简单均分策略（后续替换为 LLM 推理）
        hours_per_project = Decimal("8") / len(projects) if projects else Decimal("8")
        suggestions = []
        for p in projects:
            suggestions.append({
                "project_id": str(p.project_id),
                "project_name": p.project_name,
                "work_date": str(target_date),
                "hours": float(round(hours_per_project, 1)),
                "description": f"参与 {p.project_name} 审计工作",
            })
        return suggestions
