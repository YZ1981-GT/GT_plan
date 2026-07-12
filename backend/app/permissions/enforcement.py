"""
Permission Enforcement — FastAPI 依赖注入 helper（安全边界层）

Feature: platform-global-hardening

本模块提供 `require_permission(action, resource)` 依赖工厂，
复用 deps.py 中的 get_current_user 并委托 permission_matrix.can() 判定。

设计原则（Req 7.4/7.5）：
- 后端 deps 层 = 安全边界（authoritative）
- 本 helper 是 require_operation() 的 action+resource 语义化封装
- 前端判定仅体验优化；不一致时后端生效（403）
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, _resolve_project_role
from app.models.core import User
from app.permissions.permission_matrix import can, normalize_role


def require_permission(action: str, resource: str) -> Callable:
    """权限校验依赖工厂 — 安全边界。

    委托 permission_matrix.can(role, action, resource, context) 判定。
    拒绝时返回 403。

    用法::

        @router.put("/{wp_id}/data")
        async def update_data(
            wp_id: UUID,
            current_user: User = Depends(require_permission("edit", "workpaper")),
        ):
            ...

    Args:
        action: 操作动作（如 "edit", "review", "sign"）
        resource: 资源类型（如 "workpaper", "report", "note"）

    Returns:
        FastAPI 依赖函数，解析后返回 current_user
    """

    async def dependency(
        current_user: User = Depends(get_current_user),
        project_id: UUID | None = None,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        system_role = current_user.role.value
        project_role = await _resolve_project_role(db, current_user.id, project_id)

        # 构建上下文（后续可扩展 locked/reviewed 等）
        context = {}
        if project_role:
            context["project_role"] = project_role

        if not can(system_role, action, resource, context):
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "PERMISSION_DENIED",
                    "action": action,
                    "resource": resource,
                    "message": f"无 {action} {resource} 权限",
                },
            )
        return current_user

    return dependency
