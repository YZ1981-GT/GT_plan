"""项目级权限 API 端点 — Phase 6 F4

提供基于 ProjectAssignment.role 的项目级权限映射。
前端 useProjectRole composable 消费此端点。

Validates: Requirements F4.1, F4.2, F4.3, F4.7
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.staff_models import ProjectAssignment

router = APIRouter(prefix="/api/projects", tags=["project-permissions"])

# ---------------------------------------------------------------------------
# 项目角色 → 权限映射表（6 种角色）
# ---------------------------------------------------------------------------

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

# 系统角色 → 权限映射（与前端 ROLE_PERMISSIONS 对齐）
SYSTEM_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": [],  # admin 跳过检查，返回所有权限
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

# 所有可能的权限（admin 返回此集合）
ALL_PERMISSIONS: list[str] = sorted(set(
    perm
    for perms in list(PROJECT_ROLE_PERMISSIONS.values()) + list(SYSTEM_ROLE_PERMISSIONS.values())
    for perm in perms
))


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/my-permissions
# ---------------------------------------------------------------------------


@router.get("/{project_id}/my-permissions")
async def get_my_permissions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回当前用户在该项目的权限列表。

    - admin 角色跳过项目级检查，返回所有权限
    - 未分配用户返回系统角色对应的权限
    """
    system_role = current_user.role.value

    # admin 返回所有权限
    if system_role == "admin":
        return {
            "permissions": ALL_PERMISSIONS,
            "project_role": "admin",
            "system_role": system_role,
        }

    # 验证项目存在
    project_result = await db.execute(
        select(Project.id).where(
            Project.id == project_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    if project_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail={"message": "项目不存在", "message_en": "Project not found"})

    # 查询项目角色（通过 staff_members 关联）
    from app.models.staff_models import StaffMember
    result = await db.execute(
        select(ProjectAssignment.role).join(
            StaffMember, ProjectAssignment.staff_id == StaffMember.id
        ).where(
            ProjectAssignment.project_id == project_id,
            StaffMember.user_id == current_user.id,
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )
    )
    project_role = result.scalar_one_or_none()

    # 合并权限：项目角色权限 ∪ 系统角色权限
    project_perms = set(PROJECT_ROLE_PERMISSIONS.get(project_role, [])) if project_role else set()
    system_perms = set(SYSTEM_ROLE_PERMISSIONS.get(system_role, []))
    merged_permissions = sorted(project_perms | system_perms)

    return {
        "permissions": merged_permissions,
        "project_role": project_role,
        "system_role": system_role,
    }


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/my-role
# ---------------------------------------------------------------------------


@router.get("/{project_id}/my-role")
async def get_my_role(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回当前用户在该项目的角色 + 系统角色。

    未分配用户返回 { project_role: null, system_role: "..." }
    """
    system_role = current_user.role.value

    # admin 直接返回
    if system_role == "admin":
        return {
            "project_role": "admin",
            "system_role": system_role,
        }

    # 验证项目存在
    project_result = await db.execute(
        select(Project.id).where(
            Project.id == project_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    if project_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail={"message": "项目不存在", "message_en": "Project not found"})

    # 查询项目角色
    from app.models.staff_models import StaffMember
    result = await db.execute(
        select(ProjectAssignment.role).join(
            StaffMember, ProjectAssignment.staff_id == StaffMember.id
        ).where(
            ProjectAssignment.project_id == project_id,
            StaffMember.user_id == current_user.id,
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )
    )
    project_role = result.scalar_one_or_none()

    return {
        "project_role": project_role,
        "system_role": system_role,
    }
