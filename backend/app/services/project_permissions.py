"""项目权限解析服务。

权限映射是项目权限接口与写端点门禁的共同真源。该模块只依赖模型和数据库，
不依赖 FastAPI router 或 deps，避免权限查询在路由与依赖之间形成循环导入。
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, User
from app.models.staff_models import ProjectAssignment, StaffMember


PROJECT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "manager": [
        "project:view", "project:edit",
        "review_config:edit",
        "review:approve_l1",
        "assignment:manage",
        "workpaper:view", "workpaper:edit", "workpaper:export",
        "workpaper:review_approve", "workpaper:review_reject",
        "workpaper:submit_review", "workpaper:escalate",
        "adjustment:view", "adjustment:edit", "adjustment:create", "adjustment:delete", "adjustment:review",
        "report:view", "report:edit", "report:export",
        "sampling:execute",
        "report_config:edit",
        "ticket:close",
        "send_reminder",
        "batch_brief",
        "approve_workhours",
        "view_dashboard_manager",
    ],
    "signing_partner": [
        "project:view", "project:edit", "project:delete",
        "sign:execute",
        "archive:execute",
        "review:approve_l2",
        "review_config:edit",
        "assignment:manage",
        "workpaper:view", "workpaper:edit", "workpaper:export",
        "workpaper:review_approve", "workpaper:review_reject",
        "workpaper:submit_review",
        "adjustment:view", "adjustment:edit", "adjustment:create", "adjustment:delete", "adjustment:review",
        "report:view", "report:edit", "report:export", "report:export_final",
        "sampling:execute",
        "report_config:edit",
        "view_dashboard_manager",
    ],
    "auditor": [
        "project:view",
        "workpaper:view", "workpaper:edit",
        "workpaper:submit_review",
        "adjustment:view", "adjustment:edit", "adjustment:create",
        "adjustment:convert_to_misstatement",
        "report:view",
        "independence:edit",
    ],
    "eqcr": [
        "project:view",
        "workpaper:view",
        "report:view",
        "adjustment:view",
        "eqcr:approve",
        "shadow_compute",
        "view_eqcr",
        "record_opinion",
        "approve_eqcr",
        "independence:edit",
    ],
    "qc": [
        "project:view",
        "workpaper:view", "workpaper:edit",
        "workpaper:submit_review",
        "adjustment:view", "adjustment:edit", "adjustment:create",
        "report:view",
        "qc:initiate",
        "qc:publish_report",
        "sampling:execute",
        "independence:edit",
    ],
    "readonly": [
        "project:view",
        "workpaper:view",
        "report:view",
    ],
}

SYSTEM_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": [],
    "partner": [
        "project:view", "project:edit", "project:create", "project:delete",
        "sign:execute", "archive:execute",
        "report:view", "report:edit", "report:export", "report:export_final",
        "workpaper:view", "workpaper:edit", "workpaper:export",
        "workpaper:submit_review", "workpaper:review_approve", "workpaper:review_reject", "workpaper:escalate",
        "adjustment:view", "adjustment:edit", "adjustment:create", "adjustment:delete", "adjustment:review",
        "adjustment:convert_to_misstatement",
        "user:view", "qc:initiate",
        "assignment:batch", "template:delete", "staff:delete",
        "view_dashboard_manager", "approve_workhours", "send_reminder", "batch_brief",
        "recycle:restore", "recycle:purge",
        "sampling:execute", "report_config:edit", "ticket:close",
        "independence:edit",
    ],
    "manager": [
        "project:view", "project:edit", "project:create",
        "report:view", "report:edit", "report:export",
        "workpaper:view", "workpaper:edit", "workpaper:export",
        "workpaper:submit_review", "workpaper:review_approve", "workpaper:review_reject", "workpaper:escalate",
        "adjustment:view", "adjustment:edit", "adjustment:create", "adjustment:delete", "adjustment:review",
        "adjustment:convert_to_misstatement",
        "assignment:batch", "template:delete", "staff:delete",
        "view_dashboard_manager", "approve_workhours", "send_reminder", "batch_brief",
        "recycle:restore", "recycle:purge",
        "sampling:execute", "report_config:edit", "ticket:close",
        "independence:edit",
    ],
    "auditor": [
        "project:view",
        "workpaper:view", "workpaper:edit", "workpaper:submit_review",
        "adjustment:view", "adjustment:edit", "adjustment:create",
        "adjustment:convert_to_misstatement",
        "report:view",
        "independence:edit",
    ],
    "qc": [
        "project:view",
        "workpaper:view", "workpaper:edit", "workpaper:submit_review",
        "adjustment:view", "adjustment:edit", "adjustment:create",
        "adjustment:convert_to_misstatement",
        "report:view",
        "qc:initiate", "qc:publish_report",
        "sampling:execute",
        "independence:edit",
    ],
    "readonly": [
        "project:view",
        "workpaper:view",
        "report:view",
    ],
}

ALL_PERMISSIONS: list[str] = sorted({
    permission
    for permissions in [*PROJECT_ROLE_PERMISSIONS.values(), *SYSTEM_ROLE_PERMISSIONS.values()]
    for permission in permissions
})


@dataclass(frozen=True)
class ProjectPermissionContext:
    """项目权限解析结果，供 API 同时返回角色和权限。"""

    permissions: frozenset[str]
    project_role: str | None
    system_role: str


async def resolve_project_context(
    db: AsyncSession,
    current_user: User,
    project_id: UUID,
) -> ProjectPermissionContext:
    """解析用户在项目中的系统角色、项目角色和合并权限。"""
    project_exists = await db.scalar(
        select(Project.id).where(
            Project.id == project_id,
            Project.is_deleted.is_(False),
        )
    )
    if project_exists is None:
        raise HTTPException(
            status_code=404,
            detail={"message": "项目不存在", "message_en": "Project not found"},
        )

    system_role = current_user.role.value
    if system_role == "admin":
        return ProjectPermissionContext(
            permissions=frozenset(ALL_PERMISSIONS),
            project_role="admin",
            system_role=system_role,
        )

    project_role = await db.scalar(
        select(ProjectAssignment.role)
        .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
        .where(
            ProjectAssignment.project_id == project_id,
            StaffMember.user_id == current_user.id,
            ProjectAssignment.is_deleted.is_(False),
            StaffMember.is_deleted.is_(False),
        )
    )
    project_permissions = set(PROJECT_ROLE_PERMISSIONS.get(project_role, []))
    system_permissions = set(SYSTEM_ROLE_PERMISSIONS.get(system_role, []))
    return ProjectPermissionContext(
        permissions=frozenset(project_permissions | system_permissions),
        project_role=project_role,
        system_role=system_role,
    )


async def resolve_project_permissions(
    db: AsyncSession,
    current_user: User,
    project_id: UUID,
) -> set[str]:
    """返回用户在项目中的合并权限集合。"""
    context = await resolve_project_context(db, current_user, project_id)
    return set(context.permissions)
