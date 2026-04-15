"""认证中间件 — JWT 验证 + 用户提取 + 权限校验

代理到 deps.py 的统一 get_current_user 实现，保留 require_permission
和 require_any_permission 供路由使用。

Validates: Requirements 1.3, 1.6
"""

from fastapi import Depends, HTTPException, status

from app.deps import get_current_user  # noqa: F401 — re-export
from app.models.core import User
from app.services.permission_service import Permission, check_permission


def require_permission(permission: Permission):
    """权限校验依赖工厂：要求用户拥有指定权限"""
    def dependency(user: User = Depends(get_current_user)):
        role = user.role.value if hasattr(user.role, 'value') else str(user.role)
        if not check_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )
        return user
    return dependency


def require_any_permission(*permissions: Permission):
    """权限校验依赖工厂：要求用户拥有任一指定权限"""
    def dependency(user: User = Depends(get_current_user)):
        role = user.role.value if hasattr(user.role, 'value') else str(user.role)
        for p in permissions:
            if check_permission(role, p):
                return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    return dependency
