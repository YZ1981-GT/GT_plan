"""管理看板服务

Phase 9 Task 1.10: 看板聚合 API
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, ProjectStatus
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour

logger = logging.getLogger(__name__)


class DashboardService:
    """管理看板数据聚合"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_overview(self) -> dict:
        """关键指标聚合（带 Redis 缓存）"""
        # 尝试 Redis 缓存
        try:
            from app.core.redis import redis_client
            cached = await redis_client.get("dashboard:global:overview")
            if cached:
                import json
                return json.loads(cached)
        except Exception:
            pass

        # 在审项目数
        active_q = sa.select(sa.func.count()).select_from(Project).where(
            Project.is_deleted == False,  # noqa
            Project.status.in_([ProjectStatus.planning, ProjectStatus.execution, ProjectStatus.completion]),
        )
        active_count = (await self.db.execute(active_q)).scalar() or 0

        # 本周工时总量
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_hours_q = sa.select(sa.func.coalesce(sa.func.sum(WorkHour.hours), 0)).where(
            WorkHour.is_deleted == False,  # noqa
            WorkHour.work_date >= week_start,
            WorkHour.work_date <= today,
        )
        week_hours = float((await self.db.execute(week_hours_q)).scalar() or 0)

        # 人员总数
        staff_q = sa.select(sa.func.count()).select_from(StaffMember).where(StaffMember.is_deleted == False)  # noqa
        staff_count = (await self.db.execute(staff_q)).scalar() or 0

        result = {
            "active_projects": active_count,
            "week_hours": week_hours,
            "staff_count": staff_count,
            "overdue_projects": await self._get_overdue_projects(),
            "pending_review_workpapers": await self._get_pending_review_workpapers(),
        }

        # 写入 Redis 缓存
        try:
            from app.core.redis import redis_client
            import json
            await redis_client.set("dashboard:global:overview", json.dumps(result), ex=30)
        except Exception:
            pass

        return result

    async def get_project_progress(self) -> list[dict]:
        """项目进度列表——从 wp_index 实际编制状态派生真实完成率"""
        from app.models.workpaper_models import WorkingPaper

        q = (
            sa.select(Project.id, Project.name, Project.client_name, Project.status)
            .where(Project.is_deleted == False)  # noqa
            .order_by(Project.created_at.desc())
            .limit(50)
        )
        rows = (await self.db.execute(q)).all()

        # 批量查询每个项目的底稿完成率（一次 SQL 聚合全部项目）
        project_ids = [r.id for r in rows]
        wp_stats: dict[str, dict] = {}
        if project_ids:
            wp_q = (
                sa.select(
                    WorkingPaper.project_id,
                    sa.func.count(WorkingPaper.id).label("total"),
                    sa.func.count(
                        sa.case(
                            (WorkingPaper.review_status.in_(["level1_passed", "level2_passed"]), WorkingPaper.id),
                            else_=None,
                        )
                    ).label("completed"),
                )
                .where(
                    WorkingPaper.is_deleted == sa.false(),
                    WorkingPaper.project_id.in_(project_ids),
                )
                .group_by(WorkingPaper.project_id)
            )
            wp_rows = (await self.db.execute(wp_q)).all()
            for wr in wp_rows:
                total = wr.total or 0
                completed = wr.completed or 0
                wp_stats[str(wr.project_id)] = {
                    "total": total,
                    "completed": completed,
                    "pct": round(completed / total * 100) if total > 0 else 0,
                }

        # 状态兜底（无底稿时按阶段估算）
        status_pct_fallback = {
            "created": 5, "planning": 15, "execution": 40,
            "completion": 75, "reporting": 90, "archived": 100,
        }

        results = []
        for r in rows:
            pid = str(r.id)
            ws = wp_stats.get(pid)
            if ws and ws["total"] > 0:
                progress = ws["pct"]
            else:
                progress = status_pct_fallback.get(r.status, 0)
            results.append({
                "project_id": pid,
                "project_name": r.name,
                "client_name": r.client_name,
                "status": r.status,
                "progress": progress,
                "wp_total": ws["total"] if ws else 0,
                "wp_completed": ws["completed"] if ws else 0,
            })
        return results

    async def get_staff_workload(self) -> list[dict]:
        """人员负荷排行——工时 + 底稿分配数量双维度"""
        from app.models.workpaper_models import WorkingPaper

        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        q = (
            sa.select(
                StaffMember.id,
                StaffMember.name,
                StaffMember.title,
                sa.func.count(sa.distinct(ProjectAssignment.project_id)).label("project_count"),
                sa.func.coalesce(
                    sa.select(sa.func.sum(WorkHour.hours))
                    .where(
                        WorkHour.staff_id == StaffMember.id,
                        WorkHour.work_date >= week_start,
                        WorkHour.work_date <= today,
                        WorkHour.is_deleted == False,  # noqa
                    )
                    .correlate(StaffMember)
                    .scalar_subquery(),
                    0,
                ).label("week_hours"),
                # 底稿分配数量（该人作为编制人 assigned_to 的活跃底稿数）
                sa.func.coalesce(
                    sa.select(sa.func.count(WorkingPaper.id))
                    .where(
                        WorkingPaper.assigned_to == StaffMember.user_id,
                        WorkingPaper.is_deleted == False,  # noqa
                    )
                    .correlate(StaffMember)
                    .scalar_subquery(),
                    0,
                ).label("wp_count"),
            )
            .outerjoin(ProjectAssignment, sa.and_(
                ProjectAssignment.staff_id == StaffMember.id,
                ProjectAssignment.is_deleted == False,  # noqa
            ))
            .where(StaffMember.is_deleted == False)  # noqa
            .group_by(StaffMember.id, StaffMember.name, StaffMember.title)
            .order_by(sa.desc("wp_count"), sa.desc("week_hours"))
            .limit(20)
        )
        rows = (await self.db.execute(q)).all()
        return [
            {
                "staff_id": str(r.id),
                "name": r.name,
                "title": r.title,
                "project_count": r.project_count,
                "week_hours": float(r.week_hours),
                "wp_count": r.wp_count,
            }
            for r in rows
        ]

    async def get_schedule(self) -> list[dict]:
        """人员排期甘特图数据（简化版）"""
        q = (
            sa.select(
                StaffMember.name,
                Project.name.label("project_name"),
                ProjectAssignment.assigned_at,
                ProjectAssignment.role,
            )
            .join(ProjectAssignment, ProjectAssignment.staff_id == StaffMember.id)
            .join(Project, ProjectAssignment.project_id == Project.id)
            .where(
                StaffMember.is_deleted == False,  # noqa
                ProjectAssignment.is_deleted == False,  # noqa
                Project.is_deleted == False,  # noqa
                Project.status.in_(["planning", "execution", "completion"]),
            )
            .order_by(StaffMember.name, ProjectAssignment.assigned_at)
            .limit(100)
        )
        rows = (await self.db.execute(q)).all()
        return [
            {
                "staff_name": r.name,
                "project_name": r.project_name,
                "assigned_at": str(r.assigned_at) if r.assigned_at else None,
                "role": r.role,
            }
            for r in rows
        ]

    async def get_hours_heatmap(self, days: int = 30) -> list[dict]:
        """工时热力图数据"""
        start = date.today() - timedelta(days=days)
        q = (
            sa.select(
                StaffMember.name,
                WorkHour.work_date,
                sa.func.sum(WorkHour.hours).label("total_hours"),
            )
            .join(StaffMember, WorkHour.staff_id == StaffMember.id)
            .where(
                WorkHour.is_deleted == False,  # noqa
                WorkHour.work_date >= start,
            )
            .group_by(StaffMember.name, WorkHour.work_date)
            .order_by(WorkHour.work_date)
        )
        rows = (await self.db.execute(q)).all()
        return [
            {"staff_name": r.name, "date": str(r.work_date), "hours": float(r.total_hours)}
            for r in rows
        ]

    async def get_risk_alerts(self) -> list[dict]:
        """风险预警——多维度聚合"""
        from app.models.workpaper_models import WorkingPaper, WpReviewStatus

        alerts = []

        # 1. 超期项目（创建超 180 天仍处于 planning/execution）
        cutoff = datetime.now(timezone.utc) - timedelta(days=180)
        overdue_q = sa.select(sa.func.count()).select_from(Project).where(
            Project.is_deleted == False,  # noqa
            Project.status.notin_(["archived", "created"]),
            Project.created_at <= cutoff,
        )
        overdue = (await self.db.execute(overdue_q)).scalar() or 0
        if overdue > 0:
            alerts.append({
                "type": "overdue_project",
                "level": "critical",
                "count": overdue,
                "message": f"{overdue} 个项目可能超期（创建超180天未归档）",
            })

        # 2. 待复核底稿超期（submitted 超7天无复核操作）
        review_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        stale_review_q = sa.select(sa.func.count()).select_from(WorkingPaper).where(
            WorkingPaper.is_deleted == sa.false(),
            WorkingPaper.review_status.in_([
                WpReviewStatus.pending_level1,
                WpReviewStatus.pending_level2,
            ]),
            WorkingPaper.updated_at < review_cutoff,
        )
        stale_review = (await self.db.execute(stale_review_q)).scalar() or 0
        if stale_review > 0:
            alerts.append({
                "type": "stale_review",
                "level": "warning",
                "count": stale_review,
                "message": f"{stale_review} 份底稿待复核超过7天",
            })

        # 3. 未分配编制人的底稿
        unassigned_q = sa.select(sa.func.count()).select_from(WorkingPaper).where(
            WorkingPaper.is_deleted == sa.false(),
            WorkingPaper.assigned_to.is_(None),
        )
        unassigned = (await self.db.execute(unassigned_q)).scalar() or 0
        if unassigned > 0:
            alerts.append({
                "type": "unassigned_wp",
                "level": "warning",
                "count": unassigned,
                "message": f"{unassigned} 份底稿未分配编制人",
            })

        # 4. 未更正错报
        try:
            from app.models.audit_platform_models import UnadjustedMisstatement
            misstatement_q = sa.select(sa.func.count()).select_from(UnadjustedMisstatement).where(
                UnadjustedMisstatement.is_deleted == sa.false(),
            )
            misstatement_count = (await self.db.execute(misstatement_q)).scalar() or 0
            if misstatement_count > 0:
                alerts.append({
                    "type": "unadjusted_misstatement",
                    "level": "warning" if misstatement_count <= 5 else "critical",
                    "count": misstatement_count,
                    "message": f"{misstatement_count} 笔未更正错报",
                })
        except Exception:
            pass  # 表可能不存在

        return alerts

    async def get_quality_metrics(self) -> dict:
        """审计质量指标"""
        from app.models.workpaper_models import WorkingPaper, WpReviewStatus, WpQcResult
        from app.models.audit_platform_models import Adjustment

        # qc_pass_rate — 从 wp_qc_results 计算通过率
        total_qc = (await self.db.execute(
            sa.select(sa.func.count()).select_from(WpQcResult)
        )).scalar() or 0
        passed_qc = (await self.db.execute(
            sa.select(sa.func.count()).select_from(WpQcResult).where(WpQcResult.passed == True)  # noqa
        )).scalar() or 0
        qc_pass_rate = round(passed_qc / total_qc * 100, 1) if total_qc > 0 else 0

        # review_completion_rate — 从 working_paper 计算复核完成率
        total_wp = (await self.db.execute(
            sa.select(sa.func.count()).select_from(WorkingPaper).where(
                WorkingPaper.is_deleted == sa.false(),
            )
        )).scalar() or 0
        reviewed_wp = (await self.db.execute(
            sa.select(sa.func.count()).select_from(WorkingPaper).where(
                WorkingPaper.is_deleted == sa.false(),
                WorkingPaper.review_status.in_([
                    WpReviewStatus.level1_passed, WpReviewStatus.level2_passed,
                ]),
            )
        )).scalar() or 0
        review_completion_rate = round(reviewed_wp / total_wp * 100, 1) if total_wp > 0 else 0

        # adjustment_count — 从 adjustments 表查询活跃数量
        adj_count = (await self.db.execute(
            sa.select(sa.func.count()).select_from(Adjustment).where(
                Adjustment.is_deleted == sa.false(),
            )
        )).scalar() or 0

        return {
            "qc_pass_rate": qc_pass_rate,
            "review_completion_rate": review_completion_rate,
            "adjustment_count": adj_count,
        }

    # ------------------------------------------------------------------
    # 看板指标辅助方法
    # ------------------------------------------------------------------

    async def _get_overdue_projects(self) -> int:
        """逾期项目数：创建超 180 天仍处于 planning/execution 状态且未归档"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=180)
        result = await self.db.execute(
            sa.select(sa.func.count()).select_from(Project).where(
                Project.status.in_([ProjectStatus.execution, ProjectStatus.planning]),
                Project.is_deleted == sa.false(),
                Project.created_at < cutoff,
            )
        )
        return result.scalar() or 0

    async def _get_pending_review_workpapers(self) -> int:
        """待复核底稿数：review_status 为 pending_level1 或 pending_level2"""
        from app.models.workpaper_models import WorkingPaper, WpReviewStatus

        result = await self.db.execute(
            sa.select(sa.func.count()).select_from(WorkingPaper).where(
                WorkingPaper.is_deleted == sa.false(),
                WorkingPaper.review_status.in_([
                    WpReviewStatus.pending_level1,
                    WpReviewStatus.pending_level2,
                ]),
            )
        )
        return result.scalar() or 0

    async def get_group_progress(self) -> list[dict]:
        """集团审计子公司进度对比——从底稿实际复核通过率派生"""
        from app.models.workpaper_models import WorkingPaper

        q = (
            sa.select(Project.id, Project.name, Project.client_name, Project.status, Project.parent_project_id)
            .where(
                Project.is_deleted == False,  # noqa
                Project.parent_project_id.isnot(None),
            )
            .order_by(Project.client_name)
            .limit(50)
        )
        rows = (await self.db.execute(q)).all()

        # 批量查询底稿完成率
        project_ids = [r.id for r in rows]
        wp_stats: dict[str, int] = {}
        if project_ids:
            wp_q = (
                sa.select(
                    WorkingPaper.project_id,
                    sa.func.count(WorkingPaper.id).label("total"),
                    sa.func.count(
                        sa.case(
                            (WorkingPaper.review_status.in_(["level1_passed", "level2_passed"]), WorkingPaper.id),
                            else_=None,
                        )
                    ).label("completed"),
                )
                .where(
                    WorkingPaper.is_deleted == sa.false(),
                    WorkingPaper.project_id.in_(project_ids),
                )
                .group_by(WorkingPaper.project_id)
            )
            for wr in (await self.db.execute(wp_q)).all():
                total = wr.total or 0
                wp_stats[str(wr.project_id)] = round(wr.completed / total * 100) if total > 0 else 0

        status_pct_fallback = {"created": 5, "planning": 15, "execution": 40, "completion": 75, "reporting": 90, "archived": 100}
        return [
            {
                "project_id": str(r.id),
                "name": r.client_name or r.name,
                "status": r.status,
                "progress": wp_stats.get(str(r.id), status_pct_fallback.get(r.status, 0)),
            }
            for r in rows
        ]

    async def get_stats_trend(self, project_id: str | None, days: int = 7) -> dict:
        """近 N 天各状态底稿数量趋势（单次 SQL 聚合，避免 N 次查询）"""
        from app.models.workpaper_models import WorkingPaper
        from datetime import date, timedelta
        import sqlalchemy as sa

        start_date = date.today() - timedelta(days=days - 1)

        q = (
            sa.select(
                sa.func.date(WorkingPaper.updated_at).label("day"),
                WorkingPaper.status,
                sa.func.count(WorkingPaper.id).label("cnt"),
            )
            .where(
                WorkingPaper.is_deleted == sa.false(),
                sa.func.date(WorkingPaper.updated_at) >= start_date,
            )
            .group_by(sa.func.date(WorkingPaper.updated_at), WorkingPaper.status)
            .order_by(sa.func.date(WorkingPaper.updated_at))
        )
        if project_id:
            from uuid import UUID
            try:
                q = q.where(WorkingPaper.project_id == UUID(project_id))
            except ValueError:
                pass

        rows = (await self.db.execute(q)).all()

        # 预填所有日期（补全无数据的日期）
        trend: dict[str, dict[str, int]] = {}
        for i in range(days):
            d = (date.today() - timedelta(days=days - 1 - i)).isoformat()
            trend[d] = {}
        for r in rows:
            day_str = str(r.day)
            if day_str in trend:
                trend[day_str][r.status] = r.cnt

        return {"days": days, "trend": trend}

    async def get_stats_compare(self, project_id: str | None = None, window: int = 7) -> dict:
        """统计卡环比：最近 N 天 vs 前 N 天，按 Project.status 维度聚合。

        返回：
          {
            "window": 7,
            "current": {total, in_progress, pending_review, completed},
            "previous": {同上},
            "delta_pct": {同上, float|null（前期为 0 时返回 null 避免除零）},
          }

        Validates: 仪表盘 KPI 真实环比（替代上一轮被删的硬编码假百分比）。
        """
        from app.models.core import Project, ProjectStatus
        from datetime import date, timedelta
        import sqlalchemy as sa

        today = date.today()
        cur_start = today - timedelta(days=window - 1)
        prev_start = today - timedelta(days=2 * window - 1)
        prev_end = today - timedelta(days=window)

        async def _bucket(start: date, end: date) -> dict[str, int]:
            q = (
                sa.select(Project.status, sa.func.count(Project.id))
                .where(
                    Project.is_deleted == sa.false(),
                    sa.func.date(Project.updated_at) >= start,
                    sa.func.date(Project.updated_at) <= end,
                )
                .group_by(Project.status)
            )
            if project_id:
                from uuid import UUID
                try:
                    q = q.where(Project.id == UUID(project_id))
                except ValueError:
                    pass
            rows = (await self.db.execute(q)).all()
            counts: dict[str, int] = {"total": 0, "in_progress": 0, "pending_review": 0, "completed": 0}
            for status, cnt in rows:
                counts["total"] += cnt
                # 与前端 stats 字段映射保持一致
                if status in (ProjectStatus.execution, ProjectStatus.planning):
                    counts["in_progress"] += cnt
                elif status == ProjectStatus.completion:
                    counts["pending_review"] += cnt
                elif status == ProjectStatus.archived:
                    counts["completed"] += cnt
            return counts

        cur = await _bucket(cur_start, today)
        prev = await _bucket(prev_start, prev_end)

        delta_pct: dict[str, float | None] = {}
        for k in ("total", "in_progress", "pending_review", "completed"):
            base = prev.get(k, 0)
            if base == 0:
                # 前期为 0：当期>0 显示 +100%，当期=0 显示 None（前端展示 —）
                delta_pct[k] = 100.0 if cur.get(k, 0) > 0 else None
            else:
                delta_pct[k] = round((cur.get(k, 0) - base) / base * 100, 1)

        return {
            "window": window,
            "current": cur,
            "previous": prev,
            "delta_pct": delta_pct,
        }
