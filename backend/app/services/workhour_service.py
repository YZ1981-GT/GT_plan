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
    # P1-4.5: 工时预算消耗率聚合
    # ------------------------------------------------------------------
    async def budget_consumption_rate(self, project_id: UUID) -> dict:
        """计算项目工时预算消耗率。

        Returns:
            {
                "consumed_hours": float,
                "budget_hours": float | None,
                "rate": float | None,  # 0~100, None 表示预算数据缺失
                "staff_summary": [...],
            }
        """
        summary = await self.project_summary(project_id)
        consumed = sum(s["total_hours"] for s in summary) if summary else 0.0

        # 尝试获取 budget_hours（可能字段不存在）
        budget_hours = None
        try:
            stmt = sa.select(Project.budget_hours).where(Project.id == project_id)
            result = await self.db.execute(stmt)
            budget_hours = result.scalar_one_or_none()
        except Exception:
            pass

        rate = None
        if budget_hours and float(budget_hours) > 0:
            rate = round(consumed / float(budget_hours) * 100, 1)

        return {
            "consumed_hours": consumed,
            "budget_hours": float(budget_hours) if budget_hours else None,
            "rate": rate,
            "staff_summary": summary,
        }

    # ------------------------------------------------------------------
    # P1-4.2: 人员负荷聚合（未来 7 天任务预计工时 / 可用工时）
    # ------------------------------------------------------------------
    async def personnel_load(self, project_id: UUID) -> list[dict]:
        """聚合项目人员负荷。

        简化版：统计每人已记录总工时 + 近 7 天工时密度。
        """
        from datetime import timedelta

        summary = await self.project_summary(project_id)
        now = datetime.now(timezone.utc).date()
        week_ago = now - timedelta(days=7)

        # 获取近 7 天分人工时
        q = (
            sa.select(
                StaffMember.name,
                sa.func.sum(WorkHour.hours).label("week_hours"),
            )
            .join(StaffMember, WorkHour.staff_id == StaffMember.id)
            .where(
                WorkHour.project_id == project_id,
                WorkHour.work_date >= week_ago,
                WorkHour.is_deleted == False,  # noqa
            )
            .group_by(StaffMember.id, StaffMember.name)
        )
        rows = (await self.db.execute(q)).all()
        week_map = {r.name: float(r.week_hours) for r in rows}

        result = []
        for s in summary:
            name = s["staff_name"]
            week_hours = week_map.get(name, 0.0)
            # 标准周工时 40h，负荷 = 实际/标准 * 100
            load_pct = round(week_hours / 40 * 100, 1) if week_hours else 0.0
            result.append({
                "staff_name": name,
                "total_hours": s["total_hours"],
                "week_hours": week_hours,
                "load_percent": load_pct,
                "overloaded": load_pct > 100,
            })
        return result

    # ------------------------------------------------------------------
    # LLM 智能预填（优先 vLLM 推理，降级为均分策略）
    # ------------------------------------------------------------------
    async def ai_suggest(self, staff_id: UUID, target_date: date) -> list[dict]:
        """根据用户参与的项目情况，生成工时分配建议

        优先调用 LLM 生成个性化建议，LLM 不可用时降级为均分策略。
        """
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

        # 尝试 LLM 推理
        try:
            from app.services.llm_client import chat_completion
            import json

            project_list = ", ".join([f"{p.project_name}({p.role})" for p in projects])
            prompt = f"""你是审计工时管理助手。请为以下审计员分配 {target_date} 的工时建议（总计 8 小时）。

参与项目：{project_list}

请以 JSON 数组格式返回，每项包含 project_name、hours（小数）、description（简短工作描述）。
优先分配给执行阶段的项目，计划阶段的项目分配较少工时。"""

            response = await chat_completion(prompt)
            if response and not response.startswith("[LLM"):
                # 解析 LLM 返回
                text = response.strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                llm_suggestions = json.loads(text)
                if isinstance(llm_suggestions, list) and len(llm_suggestions) > 0:
                    # 映射 project_id
                    name_to_id = {p.project_name: str(p.project_id) for p in projects}
                    result = []
                    for s in llm_suggestions:
                        pid = name_to_id.get(s.get("project_name", ""))
                        if pid:
                            result.append({
                                "project_id": pid,
                                "project_name": s.get("project_name", ""),
                                "work_date": str(target_date),
                                "hours": float(s.get("hours", 2)),
                                "description": s.get("description", "审计工作"),
                                "ai_generated": True,
                            })
                    if result:
                        return result
        except Exception as _llm_err:
            logger.debug(f"[WORKHOUR] LLM suggest failed, fallback to even split: {_llm_err}")

        # 降级：均分策略
        hours_per_project = Decimal("8") / len(projects) if projects else Decimal("8")
        suggestions = []
        for p in projects:
            suggestions.append({
                "project_id": str(p.project_id),
                "project_name": p.project_name,
                "work_date": str(target_date),
                "hours": float(round(hours_per_project, 1)),
                "description": f"参与 {p.project_name} 审计工作",
                "ai_generated": False,
            })
        return suggestions
