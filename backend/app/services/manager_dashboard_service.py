"""项目经理看板聚合服务 — ManagerDashboardService

Round 2 需求 1：聚合 PM 名下所有项目的进度、待办、团队负载。
整合 ReviewInboxService + WorkingPaperService + AssignmentService + WorkHourService，
不新建底层表，只做聚合端点。

Redis 缓存 5 分钟，带 project_id 列表作为缓存键。
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, User
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
)

logger = logging.getLogger(__name__)

# Cache TTL: 5 minutes
CACHE_TTL_SECONDS = 300
CACHE_NAMESPACE = "manager_dashboard"


class ManagerDashboardService:
    """项目经理看板数据聚合服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_overview(self, user: User, project_ids: list[uuid.UUID] | None = None) -> dict[str, Any]:
        """获取经理看板总览数据。

        Args:
            user: 当前用户
            project_ids: 可选预计算好的项目 ID 列表（Batch 1 P1.1：避免路由已算过再重算）

        返回:
            {
                projects: [...],          # 项目卡片列表
                cross_todos: {...},       # 跨项目待办汇总
                team_load: [...],         # 团队负载
            }
        """
        # 1. 获取用户可见的项目 ID 列表（基于权限守卫）
        if project_ids is None:
            project_ids = await self._get_manager_project_ids(user)
        if not project_ids:
            return {"projects": [], "cross_todos": _empty_cross_todos(), "team_load": []}

        # 2. 尝试从 Redis 缓存读取
        cache_key = self._build_cache_key(user.id, project_ids)
        cached = await self._get_cache(cache_key)
        if cached is not None:
            return cached

        # 3. 聚合数据（并发执行三个独立聚合，减少总延迟）
        import asyncio
        projects, cross_todos, team_load = await asyncio.gather(
            self._aggregate_projects(project_ids),
            self._aggregate_cross_todos(project_ids, user.id),
            self._aggregate_team_load(project_ids),
        )

        result = {
            "projects": projects,
            "cross_todos": cross_todos,
            "team_load": team_load,
        }

        # 4. 写入缓存
        await self._set_cache(cache_key, result)

        return result

    async def get_assignment_status(
        self,
        user: User,
        days: int = 7,
        project_id: uuid.UUID | None = None,
        project_ids: list[uuid.UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """获取近 N 天委派记录的已读回执状态。

        联合 Notification(type=ASSIGNMENT_CREATED) + WorkingPaper + WpIndex + User/StaffMember
        查询时实时计算 48 小时未读标记。

        Args:
            user: 当前用户
            days: 查询天数
            project_id: 可选单项目筛选
            project_ids: 可选预计算好的项目 ID 列表（Batch 1 P1.1）

        返回:
            [{wp_code, assignee_name, assigned_at, notification_read_at|null, is_overdue_unread}]
        """
        from app.models.core import Notification
        from app.services.notification_types import ASSIGNMENT_CREATED

        # 获取用户可见的项目 ID 列表
        if project_ids is None:
            project_ids = await self._get_manager_project_ids(user)
        if not project_ids:
            return []

        # 如果指定了 project_id，限制范围
        if project_id is not None:
            if project_id not in project_ids:
                return []
            project_ids = [project_id]

        # 时间范围（Batch 1 P1.2: UTC naive 与 DB 存储一致，
        # SQLite 存 naive TIMESTAMP，PG 默认 TIMESTAMP WITHOUT TIME ZONE）
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        since = now_utc - timedelta(days=days)
        overdue_threshold = now_utc - timedelta(hours=48)

        from app.models.workpaper_models import WorkingPaper, WpIndex
        from app.models.staff_models import StaffMember

        # Step 1: 查询近 N 天的 ASSIGNMENT_CREATED 通知
        # 跨轮约束 1：所有 message_type 走 notification_types.py 常量（小写）
        # assignment_service.py:143 已统一为 ASSIGNMENT_CREATED 常量（Batch 1 P0.1）
        notif_q = (
            sa.select(
                Notification.id.label("notif_id"),
                Notification.recipient_id,
                Notification.created_at.label("assigned_at"),
                Notification.is_read,
                Notification.read_at,
                Notification.related_object_id.label("notif_project_id"),
            )
            .where(
                Notification.message_type == ASSIGNMENT_CREATED,
                Notification.created_at >= since,
            )
        )
        # 限定项目范围：related_object_id 是 project_id
        notif_q = notif_q.where(
            Notification.related_object_id.in_(project_ids)
        )
        notif_rows = (await self.db.execute(notif_q)).all()

        if not notif_rows:
            return []

        # Step 2: 对每条通知，找到对应的底稿分配信息
        # 通知的 recipient_id = WorkingPaper.assigned_to，且 WorkingPaper.project_id = notif.related_object_id
        results = []
        # 收集所有 recipient_ids 和 project_ids 用于批量查询
        recipient_ids = list(set(r.recipient_id for r in notif_rows))
        notif_project_ids = list(set(r.notif_project_id for r in notif_rows if r.notif_project_id))

        # 批量查询：被分配人的底稿（当前 assigned_to 匹配）
        wp_q = (
            sa.select(
                WorkingPaper.id.label("wp_id"),
                WorkingPaper.project_id,
                WorkingPaper.assigned_to,
                WpIndex.wp_code,
                WpIndex.wp_name,
            )
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id.in_(notif_project_ids),
                WorkingPaper.assigned_to.in_(recipient_ids),
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
        wp_rows = (await self.db.execute(wp_q)).all()

        # 构建 (project_id, assigned_to) → [wp_code, ...] 映射
        wp_by_assignee: dict[tuple[uuid.UUID, uuid.UUID], list[dict]] = {}
        for wp in wp_rows:
            key = (wp.project_id, wp.assigned_to)
            if key not in wp_by_assignee:
                wp_by_assignee[key] = []
            wp_by_assignee[key].append({
                "wp_code": wp.wp_code,
                "wp_name": wp.wp_name,
            })

        # 批量查询：获取 assignee 姓名（优先 StaffMember.name，回退 User.username）
        from app.models.core import User as UserModel

        staff_q = (
            sa.select(StaffMember.user_id, StaffMember.name)
            .where(
                StaffMember.user_id.in_(recipient_ids),
                StaffMember.is_deleted == False,  # noqa: E712
            )
        )
        staff_rows = (await self.db.execute(staff_q)).all()
        staff_name_map: dict[uuid.UUID, str] = {r.user_id: r.name for r in staff_rows}

        # 回退：查 User.username
        missing_user_ids = [uid for uid in recipient_ids if uid not in staff_name_map]
        if missing_user_ids:
            user_q = sa.select(UserModel.id, UserModel.username).where(
                UserModel.id.in_(missing_user_ids)
            )
            user_rows = (await self.db.execute(user_q)).all()
            for r in user_rows:
                staff_name_map[r.id] = r.username

        # Step 3: 组装结果
        for notif in notif_rows:
            assignee_name = staff_name_map.get(notif.recipient_id, "未知")
            key = (notif.notif_project_id, notif.recipient_id)
            wp_list = wp_by_assignee.get(key, [])

            # 计算 is_overdue_unread：未读且超过 48 小时
            is_overdue_unread = (not notif.is_read) and (notif.assigned_at <= overdue_threshold)

            if wp_list:
                # 每张底稿一条记录
                for wp_info in wp_list:
                    results.append({
                        "wp_code": wp_info["wp_code"],
                        "assignee_name": assignee_name,
                        "assigned_at": notif.assigned_at.isoformat() if notif.assigned_at else None,
                        "notification_read_at": notif.read_at.isoformat() if notif.read_at else None,
                        "is_overdue_unread": is_overdue_unread,
                    })
            else:
                # 通知存在但底稿可能已被重新分配，仍展示通知记录
                results.append({
                    "wp_code": None,
                    "assignee_name": assignee_name,
                    "assigned_at": notif.assigned_at.isoformat() if notif.assigned_at else None,
                    "notification_read_at": notif.read_at.isoformat() if notif.read_at else None,
                    "is_overdue_unread": is_overdue_unread,
                })

        # 排序：overdue_unread 在前（0 < 1），同组内按 assigned_at 降序
        results.sort(key=lambda x: (
            0 if x["is_overdue_unread"] else 1,
            -(datetime.fromisoformat(x["assigned_at"]).timestamp() if x["assigned_at"] else 0),
        ))

        return results

    # ------------------------------------------------------------------
    # Permission: 获取经理可见项目
    # ------------------------------------------------------------------

    async def _get_manager_project_ids(self, user: User) -> list[uuid.UUID]:
        """获取当前用户作为 manager 或 signing_partner 参与的项目 ID 列表。

        权限规则:
        - role='admin' → 所有未删除项目
        - role='manager' → project_assignment.role IN ('manager', 'signing_partner')
        - 其他角色 → 同样检查 project_assignment
        """
        # admin 可见所有项目
        if user.role.value == "admin":
            q = sa.select(Project.id).where(Project.is_deleted == False)  # noqa: E712
            rows = (await self.db.execute(q)).all()
            return [r[0] for r in rows]

        # 通过 StaffMember.user_id 找到 staff_id，再查 ProjectAssignment
        staff_q = sa.select(StaffMember.id).where(
            StaffMember.user_id == user.id,
            StaffMember.is_deleted == False,  # noqa: E712
        )
        staff_row = (await self.db.execute(staff_q)).first()

        if not staff_row:
            # 回退：直接用 user.role 判断
            if user.role.value == "manager":
                # 尝试通过 Project.manager_id 查找
                q = sa.select(Project.id).where(
                    Project.manager_id == user.id,
                    Project.is_deleted == False,  # noqa: E712
                )
                rows = (await self.db.execute(q)).all()
                return [r[0] for r in rows]
            return []

        staff_id = staff_row[0]

        # 查询 project_assignments 中 role 为 manager 或 signing_partner 的项目
        q = (
            sa.select(ProjectAssignment.project_id)
            .join(Project, ProjectAssignment.project_id == Project.id)
            .where(
                ProjectAssignment.staff_id == staff_id,
                ProjectAssignment.role.in_(["manager", "signing_partner"]),
                ProjectAssignment.is_deleted == False,  # noqa: E712
                Project.is_deleted == False,  # noqa: E712
            )
        )
        rows = (await self.db.execute(q)).all()
        project_ids = [r[0] for r in rows]

        # 补充：通过 Project.manager_id 直接关联的项目
        q2 = sa.select(Project.id).where(
            Project.manager_id == user.id,
            Project.is_deleted == False,  # noqa: E712
        )
        rows2 = (await self.db.execute(q2)).all()
        extra_ids = {r[0] for r in rows2}

        # 合并去重
        all_ids = list(set(project_ids) | extra_ids)
        return all_ids

    # ------------------------------------------------------------------
    # 聚合：项目卡片
    # ------------------------------------------------------------------

    async def _aggregate_projects(self, project_ids: list[uuid.UUID]) -> list[dict]:
        """聚合每个项目的卡片数据：完成率、待复核、逾期、风险等级"""
        if not project_ids:
            return []

        # 获取项目基本信息
        proj_q = sa.select(Project).where(
            Project.id.in_(project_ids),
            Project.is_deleted == False,  # noqa: E712
        )
        projects = (await self.db.execute(proj_q)).scalars().all()

        # 按项目聚合底稿状态 + 逾期数（合并为单次查询，减少 DB 往返）
        # Batch 2 P1: 合并 overdue 查询到 wp_stats 使用 CASE WHEN
        overdue_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        wp_stats_q = (
            sa.select(
                WorkingPaper.project_id,
                sa.func.count().label("total"),
                sa.func.count(
                    sa.case(
                        (WorkingPaper.status.in_([
                            WpFileStatus.review_passed,
                            WpFileStatus.archived,
                        ]), 1),
                    )
                ).label("passed"),
                sa.func.count(
                    sa.case(
                        (WorkingPaper.review_status.in_([
                            WpReviewStatus.pending_level1,
                            WpReviewStatus.pending_level2,
                        ]), 1),
                    )
                ).label("pending_review"),
                sa.func.count(
                    sa.case(
                        (sa.and_(
                            WorkingPaper.created_at <= overdue_threshold,
                            WorkingPaper.status.notin_([
                                WpFileStatus.review_passed,
                                WpFileStatus.archived,
                            ]),
                        ), 1),
                    )
                ).label("overdue_count"),
            )
            .where(
                WorkingPaper.project_id.in_(project_ids),
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
            .group_by(WorkingPaper.project_id)
        )
        wp_stats_rows = (await self.db.execute(wp_stats_q)).all()
        wp_stats_map = {
            r.project_id: {
                "total": r.total,
                "passed": r.passed,
                "pending_review": r.pending_review,
            }
            for r in wp_stats_rows
        }
        overdue_map = {r.project_id: r.overdue_count for r in wp_stats_rows}

        # 按项目聚合已批准工时（Batch 1 Fix 1.7: 避免前端 N+1 cost-overview 请求）
        approved_hours_q = (
            sa.select(
                WorkHour.project_id,
                sa.func.coalesce(sa.func.sum(WorkHour.hours), 0).label("approved_hours"),
            )
            .where(
                WorkHour.project_id.in_(project_ids),
                WorkHour.status == "approved",
                WorkHour.is_deleted == False,  # noqa: E712
            )
            .group_by(WorkHour.project_id)
        )
        approved_rows = (await self.db.execute(approved_hours_q)).all()
        approved_map = {r.project_id: float(r.approved_hours) for r in approved_rows}

        # 组装卡片
        cards = []
        for proj in projects:
            stats = wp_stats_map.get(proj.id, {"total": 0, "passed": 0, "pending_review": 0})
            total = stats["total"]
            passed = stats["passed"]
            completion_rate = round(passed / total * 100, 1) if total > 0 else 0
            overdue_count = overdue_map.get(proj.id, 0)

            # 风险等级：基于完成率和逾期数
            risk_level = self._compute_risk_level(completion_rate, overdue_count, total)

            cards.append({
                "id": str(proj.id),
                "name": proj.name,
                "client_name": proj.client_name,
                "status": proj.status.value if proj.status else "created",
                "completion_rate": completion_rate,
                "total_workpapers": total,
                "passed_workpapers": passed,
                "pending_review": stats["pending_review"],
                "overdue_count": overdue_count,
                "risk_level": risk_level,
                "budget_hours": proj.budget_hours,
                "actual_hours": approved_map.get(proj.id, 0),
                "audit_period_start": str(proj.audit_period_start) if proj.audit_period_start else None,
                "audit_period_end": str(proj.audit_period_end) if proj.audit_period_end else None,
            })

        # 按风险等级排序（高风险在前）
        risk_order = {"high": 0, "medium": 1, "low": 2}
        cards.sort(key=lambda c: risk_order.get(c["risk_level"], 3))

        return cards

    # ------------------------------------------------------------------
    # 聚合：跨项目待办
    # ------------------------------------------------------------------

    async def _aggregate_cross_todos(
        self, project_ids: list[uuid.UUID], user_id: uuid.UUID
    ) -> dict[str, Any]:
        """聚合跨项目待办：待复核、待分配、待审批工时"""
        # 待复核数量（reviewer == user_id）
        # 先找 staff_id
        staff_q = sa.select(StaffMember.id).where(
            StaffMember.user_id == user_id,
            StaffMember.is_deleted == False,  # noqa: E712
        )
        staff_row = (await self.db.execute(staff_q)).first()

        pending_review = 0
        if staff_row:
            # 待复核：reviewer 是当前用户
            review_q = sa.select(sa.func.count()).select_from(WorkingPaper).where(
                WorkingPaper.project_id.in_(project_ids),
                WorkingPaper.is_deleted == False,  # noqa: E712
                WorkingPaper.reviewer == user_id,
                WorkingPaper.review_status.in_([
                    WpReviewStatus.pending_level1,
                    WpReviewStatus.pending_level2,
                ]),
            )
            pending_review = (await self.db.execute(review_q)).scalar() or 0

        # 待分配：assigned_to IS NULL
        pending_assign_q = sa.select(sa.func.count()).select_from(WorkingPaper).where(
            WorkingPaper.project_id.in_(project_ids),
            WorkingPaper.is_deleted == False,  # noqa: E712
            WorkingPaper.assigned_to == None,  # noqa: E711
        )
        pending_assign = (await self.db.execute(pending_assign_q)).scalar() or 0

        # 待审批工时：status='confirmed' 的工时记录数
        pending_approve_q = sa.select(sa.func.count()).select_from(WorkHour).where(
            WorkHour.project_id.in_(project_ids),
            WorkHour.is_deleted == False,  # noqa: E712
            WorkHour.status == "confirmed",
        )
        pending_approve = (await self.db.execute(pending_approve_q)).scalar() or 0

        return {
            "pending_review": pending_review,
            "pending_assign": pending_assign,
            "pending_approve": pending_approve,
        }

    # ------------------------------------------------------------------
    # 聚合：团队负载
    # ------------------------------------------------------------------

    async def _aggregate_team_load(self, project_ids: list[uuid.UUID]) -> list[dict]:
        """聚合团队成员本周工时分布"""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        # 获取项目团队成员
        team_q = (
            sa.select(
                StaffMember.id.label("staff_id"),
                StaffMember.name.label("staff_name"),
                StaffMember.title,
                sa.func.count(sa.distinct(ProjectAssignment.project_id)).label("project_count"),
            )
            .join(ProjectAssignment, ProjectAssignment.staff_id == StaffMember.id)
            .where(
                ProjectAssignment.project_id.in_(project_ids),
                ProjectAssignment.is_deleted == False,  # noqa: E712
                StaffMember.is_deleted == False,  # noqa: E712
            )
            .group_by(StaffMember.id, StaffMember.name, StaffMember.title)
        )
        team_rows = (await self.db.execute(team_q)).all()

        if not team_rows:
            return []

        staff_ids = [r.staff_id for r in team_rows]

        # 本周工时
        week_hours_q = (
            sa.select(
                WorkHour.staff_id,
                sa.func.coalesce(sa.func.sum(WorkHour.hours), 0).label("week_hours"),
            )
            .where(
                WorkHour.staff_id.in_(staff_ids),
                WorkHour.project_id.in_(project_ids),
                WorkHour.work_date >= week_start,
                WorkHour.is_deleted == False,  # noqa: E712
            )
            .group_by(WorkHour.staff_id)
        )
        week_hours_rows = (await self.db.execute(week_hours_q)).all()
        week_hours_map = {r.staff_id: float(r.week_hours) for r in week_hours_rows}

        # 总工时（项目范围内）
        total_hours_q = (
            sa.select(
                WorkHour.staff_id,
                sa.func.coalesce(sa.func.sum(WorkHour.hours), 0).label("total_hours"),
            )
            .where(
                WorkHour.staff_id.in_(staff_ids),
                WorkHour.project_id.in_(project_ids),
                WorkHour.is_deleted == False,  # noqa: E712
            )
            .group_by(WorkHour.staff_id)
        )
        total_hours_rows = (await self.db.execute(total_hours_q)).all()
        total_hours_map = {r.staff_id: float(r.total_hours) for r in total_hours_rows}

        # 组装
        team_load = []
        for row in team_rows:
            team_load.append({
                "staff_id": str(row.staff_id),
                "staff_name": row.staff_name,
                "title": row.title,
                "project_count": row.project_count,
                "week_hours": week_hours_map.get(row.staff_id, 0),
                "total_hours": total_hours_map.get(row.staff_id, 0),
            })

        # 按本周工时降序排列
        team_load.sort(key=lambda x: x["week_hours"], reverse=True)

        return team_load

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_risk_level(completion_rate: float, overdue_count: int, total: int) -> str:
        """计算项目风险等级"""
        if total == 0:
            return "low"
        overdue_ratio = overdue_count / total if total > 0 else 0
        if overdue_ratio > 0.3 or (completion_rate < 30 and overdue_count > 5):
            return "high"
        if overdue_ratio > 0.1 or overdue_count > 3:
            return "medium"
        return "low"

    @staticmethod
    def _build_cache_key(user_id: uuid.UUID, project_ids: list[uuid.UUID]) -> str:
        """构建缓存键：基于用户 ID + 项目 ID 列表的哈希"""
        sorted_ids = sorted(str(pid) for pid in project_ids)
        raw = f"{user_id}:{','.join(sorted_ids)}"
        key_hash = hashlib.md5(raw.encode()).hexdigest()[:16]
        return f"{CACHE_NAMESPACE}:overview:{key_hash}"

    @staticmethod
    async def _get_cache(key: str) -> dict | None:
        """从 Redis 获取缓存，不可用时返回 None"""
        try:
            from app.core.redis import redis_client
            if redis_client is None:
                return None
            raw = await redis_client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.debug("Redis cache get failed for key=%s", key)
            return None

    @staticmethod
    async def _set_cache(key: str, data: dict) -> None:
        """写入 Redis 缓存，TTL 5 分钟"""
        try:
            from app.core.redis import redis_client
            if redis_client is None:
                return
            serialized = json.dumps(data, ensure_ascii=False, default=str)
            await redis_client.setex(key, CACHE_TTL_SECONDS, serialized)
        except Exception:
            logger.debug("Redis cache set failed for key=%s", key)


def _empty_cross_todos() -> dict:
    """空的跨项目待办"""
    return {
        "pending_review": 0,
        "pending_assign": 0,
        "pending_approve": 0,
    }
