"""
权限矩阵 API 端点 — P0-4.4

GET /api/projects/{project_id}/permission-matrix
返回当前用户在指定项目的操作权限矩阵（operation codes）。

与 project_permissions.py 的 my-permissions 互补：
- my-permissions: 返回细粒度权限列表（兼容旧前端）
- permission-matrix: 返回 7 个标准化 operation code（新矩阵 facade）
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.permission_matrix_service import get_permission_matrix

router = APIRouter(prefix="/api/projects", tags=["permission-matrix"])


@router.get("/{project_id}/permission-matrix")
async def get_project_permission_matrix(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回当前用户在该项目的权限矩阵。

    Response:
        {
            "operations": ["project:view", "wp:edit", ...],
            "denied_operations": ["report:sign", ...],
            "system_role": "auditor",
            "project_role": "preparer",
            "all_operation_codes": [...]
        }
    """
    system_role = current_user.role.value

    # admin 返回全部权限
    if system_role == "admin":
        return get_permission_matrix("admin", None)

    # 验证项目存在
    project_result = await db.execute(
        select(Project.id).where(
            Project.id == project_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    if project_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"message": "项目不存在", "message_en": "Project not found"},
        )

    # 查询项目角色
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

    return get_permission_matrix(system_role, project_role)
