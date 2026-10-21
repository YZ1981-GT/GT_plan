"""角色上下文服务 — 解决多角色×多项目×多重身份问题

核心职责：
1. 获取用户在特定项目中的有效角色（打通三层身份）
2. 获取用户的全局角色上下文（跨项目汇总）
3. 根据角色返回可见的功能菜单
4. 首页个性化内容
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User, Project, ProjectUser, ProjectUserRole, PermissionLevel
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpFileStatus, WpReviewStatus
from app.services.assignment_service import resolve_member_mapping

_logger = logging.getLogger(__name__)

# 角色优先级（高→低）
# R5 任务 2：eqcr 与 partner 同级（5），与 design.md "架构决策一览" 对齐。
_ROLE_PRIORITY = {"partner": 5, "eqcr": 5, "qc": 4, "manager": 3, "auditor": 2, "readonly": 1}

# 委派角色 → 项目角色与级别：两处委派兜底都经 assignment_service.resolve_member_mapping
# （ROLE_MAP 单一真源），本模块不另存映射；未登记的委派角色得 (readonly, readonly)。


class RoleContextService:
    """角色上下文服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_project_role(self, user_id: uuid.UUID, project_id: uuid.UUID) -> dict[str, Any]:
        """
        获取用户在特定项目中的有效角色。
        优先级：project_users > project_assignments > users.role 降级

        委派兜底（该项目没有未删除成员行时）：取该用户全部未删除人员库记录在本项目的现行委派，
        委派角色经 resolve_member_mapping 合并（EQCR 优先，否则取最高级别），以字符串返回；
        scope_cycles 取 assigned_at 最早的一条委派。
        """
        # 1. 查 project_users（最权威）
        pu = (await self.db.execute(
            select(ProjectUser).where(
                ProjectUser.project_id == project_id,
                ProjectUser.user_id == user_id,
                ProjectUser.is_deleted == False,
            )
        )).scalar_one_or_none()

        if pu:
            return {
                "source": "project_users",
                "role": pu.role.value if pu.role else "readonly",
                "permission_level": pu.permission_level.value if pu.permission_level else "readonly",
                "scope_cycles": pu.scope_cycles,
            }

        # 2. 查 project_assignments（委派表）：该用户全部未删除人员库记录的现行委派，不只看第一条人员库记录
        assignments = (await self.db.execute(
            select(ProjectAssignment.role, ProjectAssignment.assigned_cycles)
            .select_from(ProjectAssignment)
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .where(
                StaffMember.user_id == user_id,
                StaffMember.is_deleted == False,  # noqa: E712
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.is_deleted == False,  # noqa: E712
            )
            # 首行即 assigned_at 最早的一条（空值排最后；同刻按委派 id 定序，结论确定）
            .order_by(ProjectAssignment.assigned_at.asc().nulls_last(), ProjectAssignment.id.asc())
        )).all()

        if assignments:
            mapped_role, mapped_level = resolve_member_mapping([a.role for a in assignments])
            return {
                "source": "project_assignments",
                "role": mapped_role.value,
                "permission_level": mapped_level.value,
                "scope_cycles": assignments[0].assigned_cycles,
            }

        # 3. 降级到系统角色
        user = (await self.db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user:
            sys_role = user.role.value if user.role else "readonly"
            if sys_role == "admin":
                return {"source": "system_admin", "role": "admin", "permission_level": "edit", "scope_cycles": None}
            return {"source": "system_role_fallback", "role": sys_role, "permission_level": "readonly", "scope_cycles": None}

        return {"source": "none", "role": "readonly", "permission_level": "readonly", "scope_cycles": None}

    async def get_global_context(self, user_id: uuid.UUID) -> dict[str, Any]:
        """
        获取用户的全局角色上下文：
        - 系统角色
        - 参与的所有项目及各项目角色
        - 最高角色（决定导航菜单）
        - 各角色维度的统计
        """
        user = (await self.db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user:
            return {"system_role": "readonly", "projects": [], "effective_role": "readonly"}

        sys_role = user.role.value if user.role else "readonly"

        # 获取所有项目角色
        pu_q = (
            select(ProjectUser.project_id, ProjectUser.role, ProjectUser.permission_level, Project.name, Project.client_name)
            .join(Project, ProjectUser.project_id == Project.id)
            .where(ProjectUser.user_id == user_id, ProjectUser.is_deleted == False, Project.is_deleted == False)
        )
        pu_rows = (await self.db.execute(pu_q)).all()

        projects = []
        roles_seen = set()
        for pid, role, perm, pname, cname in pu_rows:
            r = role.value if role else "readonly"
            roles_seen.add(r)
            projects.append({
                "project_id": str(pid),
                "project_name": pname,
                "client_name": cname,
                "role": r,
                "permission_level": perm.value if perm else "readonly",
            })

        # 也查委派表补充：该用户全部未删除人员库记录的现行委派（不只看第一条人员库记录）；
        # 已有成员行的项目不补，其余按项目收集委派角色，经 resolve_member_mapping 合并为一组取值
        pa_q = (
            select(ProjectAssignment.project_id, ProjectAssignment.role, Project.name, Project.client_name)
            .select_from(ProjectAssignment)
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .join(Project, ProjectAssignment.project_id == Project.id)
            .where(
                StaffMember.user_id == user_id,
                StaffMember.is_deleted == False,  # noqa: E712
                ProjectAssignment.is_deleted == False,  # noqa: E712
                Project.is_deleted == False,  # noqa: E712
            )
        )
        member_project_ids = {p["project_id"] for p in projects}
        delegated: dict[str, tuple[str, str | None, list[str]]] = {}
        for pid, role, pname, cname in (await self.db.execute(pa_q)).all():
            pid_str = str(pid)
            if pid_str not in member_project_ids:
                delegated.setdefault(pid_str, (pname, cname, []))[2].append(role)
        for pid_str, (pname, cname, assignment_roles) in delegated.items():
            mapped_role, mapped_level = resolve_member_mapping(assignment_roles)
            roles_seen.add(mapped_role.value)
            projects.append({
                "project_id": pid_str,
                "project_name": pname,
                "client_name": cname,
                "role": mapped_role.value,
                "permission_level": mapped_level.value,
            })

        # 确定最高角色
        if sys_role == "admin":
            effective_role = "admin"
        else:
            all_roles = list(roles_seen) + [sys_role]
            effective_role = max(all_roles, key=lambda r: _ROLE_PRIORITY.get(r, 0))

        return {
            "system_role": sys_role,
            "effective_role": effective_role,
            "projects": projects,
            "project_count": len(projects),
            "roles_in_projects": list(roles_seen),
        }

    async def get_nav_items(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """根据用户有效角色返回可见的导航菜单项"""
        ctx = await self.get_global_context(user_id)
        role = ctx["effective_role"]

        # 基础导航（所有人可见）
        items = [
            {"key": "dashboard", "label": "仪表盘", "icon": "Odometer", "path": "/"},
            {"key": "projects", "label": "项目情况", "icon": "FolderOpened", "path": "/projects"},
        ]

        # 角色特定导航
        if role in ("admin", "partner"):
            items.append({"key": "partner-dashboard", "label": "合伙人看板", "icon": "TrendCharts", "path": "/dashboard/partner"})
            items.append({"key": "team", "label": "人员委派", "icon": "User", "path": "/settings/staff"})
            items.append({"key": "mgmt-dashboard", "label": "管理看板", "icon": "DataAnalysis", "path": "/dashboard/management"})

        if role in ("admin", "partner", "manager"):
            items.append({"key": "manager-dashboard", "label": "项目经理工作台", "icon": "Monitor", "path": "/dashboard/manager"})
            items.append({"key": "workhours", "label": "工时管理", "icon": "Timer", "path": "/work-hours"})

        if role in ("admin", "partner", "qc"):
            items.append({"key": "qc-rules", "label": "QC 规则管理", "icon": "SetUp", "path": "/qc/rules"})
            items.append({"key": "qc-inspections", "label": "质控抽查", "icon": "Search", "path": "/qc/inspections"})
            items.append({"key": "qc-cases", "label": "案例库", "icon": "Collection", "path": "/qc/cases"})

        if role in ("admin", "partner", "manager"):
            items.append({"key": "consolidation", "label": "合并项目", "icon": "Connection", "path": "/consolidation"})

        # 通用功能
        items.append({"key": "archive", "label": "归档管理", "icon": "Box", "path": "/archive"})

        if role in ("admin",):
            items.append({"key": "users", "label": "用户管理", "icon": "UserFilled", "path": "/settings/users"})

        return items

    async def get_homepage_content(self, user_id: uuid.UUID) -> dict[str, Any]:
        """根据角色返回首页个性化内容"""
        ctx = await self.get_global_context(user_id)
        role = ctx["effective_role"]

        content: dict[str, Any] = {
            "role": role,
            "greeting_type": _greeting_type(role),
            "quick_actions": [],
            "stats": {},
        }

        if role in ("admin", "partner"):
            # 合伙人：风险预警 + 待签字
            content["quick_actions"] = [
                {"label": "合伙人看板", "path": "/dashboard/partner", "icon": "TrendCharts"},
                {"label": "管理看板", "path": "/dashboard/management", "icon": "DataAnalysis"},
                {"label": "人员委派", "path": "/settings/staff", "icon": "User"},
            ]
            # 统计
            risk_q = select(func.count()).select_from(Project).where(
                Project.is_deleted == False,
                Project.status.in_(["execution", "completion"]),
            )
            content["stats"]["active_projects"] = (await self.db.execute(risk_q)).scalar() or 0

        elif role == "manager":
            # 项目经理：待复核 + 进度
            pending_q = select(func.count()).select_from(WorkingPaper).where(
                WorkingPaper.is_deleted == False,
                WorkingPaper.reviewer == user_id,
                WorkingPaper.review_status.in_([WpReviewStatus.pending_level1, WpReviewStatus.pending_level2]),
            )
            pending = (await self.db.execute(pending_q)).scalar() or 0
            content["stats"]["pending_review"] = pending
            content["quick_actions"] = [
                {"label": f"待复核 ({pending})", "path": "/review-inbox-global", "icon": "Stamp", "badge": pending},
                {"label": "管理看板", "path": "/dashboard/management", "icon": "DataAnalysis"},
            ]

        elif role == "qc":
            content["quick_actions"] = [
                {"label": "管理看板", "path": "/dashboard/management", "icon": "DataAnalysis"},
            ]

        elif role == "auditor":
            # 审计助理：我的待编底稿
            assigned_q = select(func.count()).select_from(WorkingPaper).where(
                WorkingPaper.is_deleted == False,
                WorkingPaper.assigned_to == user_id,
                WorkingPaper.status.in_([WpFileStatus.draft, WpFileStatus.revision_required]),
            )
            assigned = (await self.db.execute(assigned_q)).scalar() or 0
            content["stats"]["my_pending_workpapers"] = assigned
            content["quick_actions"] = [
                {"label": f"我的底稿 ({assigned})", "path": "/projects", "icon": "Document", "badge": assigned},
            ]

        return content


def _greeting_type(role: str) -> str:
    m = {
        "admin": "admin",
        "partner": "partner",
        "manager": "manager",
        "qc": "qc",
        "auditor": "auditor",
        "readonly": "viewer",
    }
    return m.get(role, "viewer")
