"""权限服务 — 角色权限矩阵与项目级权限校验

Validates: Requirements 1.3, 1.4
"""

from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from app.models.base import ProjectUserRole
from app.models.core import User, ProjectUser


class Permission(str, Enum):
    """系统权限枚举"""
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    PROJECT_ADMIN = "project:admin"
    WORKPAPER_READ = "workpaper:read"
    WORKPAPER_WRITE = "workpaper:write"
    WORKPAPER_SIGN = "workpaper:sign"
    REPORT_READ = "report:read"
    REPORT_WRITE = "report:write"
    REPORT_SIGN = "report:sign"
    REVIEW_SIGN = "review:sign"
    QC_PERFORM = "qc:perform"
    USER_MANAGE = "user:manage"
    ARCHIVE_MANAGE = "archive:manage"
    SYNC_MANAGE = "sync:manage"


# 角色 → 权限矩阵
ROLE_PERMISSION_MATRIX = {
    "admin": {
        Permission.PROJECT_READ, Permission.PROJECT_WRITE, Permission.PROJECT_ADMIN,
        Permission.WORKPAPER_READ, Permission.WORKPAPER_WRITE, Permission.WORKPAPER_SIGN,
        Permission.REPORT_READ, Permission.REPORT_WRITE, Permission.REPORT_SIGN,
        Permission.REVIEW_SIGN, Permission.QC_PERFORM,
        Permission.USER_MANAGE, Permission.ARCHIVE_MANAGE, Permission.SYNC_MANAGE,
    },
    "partner": {
        Permission.PROJECT_READ, Permission.PROJECT_WRITE, Permission.PROJECT_ADMIN,
        Permission.WORKPAPER_READ, Permission.WORKPAPER_WRITE, Permission.WORKPAPER_SIGN,
        Permission.REPORT_READ, Permission.REPORT_WRITE, Permission.REPORT_SIGN,
        Permission.REVIEW_SIGN, Permission.QC_PERFORM,
        Permission.ARCHIVE_MANAGE, Permission.SYNC_MANAGE,
    },
    "manager": {
        Permission.PROJECT_READ, Permission.PROJECT_WRITE, Permission.PROJECT_ADMIN,
        Permission.WORKPAPER_READ, Permission.WORKPAPER_WRITE, Permission.WORKPAPER_SIGN,
        Permission.REPORT_READ, Permission.REPORT_WRITE,
        Permission.REVIEW_SIGN, Permission.SYNC_MANAGE,
    },
    "auditor": {
        Permission.PROJECT_READ,
        Permission.WORKPAPER_READ, Permission.WORKPAPER_WRITE,
        Permission.REPORT_READ,
    },
    "qc_reviewer": {
        Permission.PROJECT_READ,
        Permission.WORKPAPER_READ, Permission.WORKPAPER_SIGN,
        Permission.REPORT_READ, Permission.REPORT_SIGN,
        Permission.QC_PERFORM, Permission.REVIEW_SIGN,
    },
    "readonly": {
        Permission.PROJECT_READ,
        Permission.WORKPAPER_READ,
        Permission.REPORT_READ,
    },
}


def check_permission(user_role: str, permission: Permission) -> bool:
    """检查角色是否拥有指定权限"""
    return permission in ROLE_PERMISSION_MATRIX.get(user_role, set())


def check_project_permission(
    db: Session,
    user_id: str,
    project_id: str,
    permission: Permission
) -> bool:
    """检查用户在项目级别是否拥有指定权限"""
    pu = db.query(ProjectUser).filter(
        ProjectUser.user_id == user_id,
        ProjectUser.project_id == project_id,
        ProjectUser.is_deleted == False,  # noqa: E712
    ).first()
    if not pu:
        return False
    role = pu.role.value if hasattr(pu.role, 'value') else str(pu.role)
    return check_permission(role, permission)


def check_cycle_scope(
    db: Session,
    user_id: str,
    project_id: str,
    cycle: str
) -> bool:
    """检查用户是否有权访问指定审计循环"""
    pu = db.query(ProjectUser).filter(
        ProjectUser.user_id == user_id,
        ProjectUser.project_id == project_id,
        ProjectUser.is_deleted == False,  # noqa: E712
    ).first()
    if not pu or not pu.scope_cycles:
        return False
    cycles = [c.strip() for c in pu.scope_cycles.split(",") if c.strip()]
    return cycle in cycles
