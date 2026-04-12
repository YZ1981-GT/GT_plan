"""依赖注入 — get_current_user, require_role, require_project_access

Validates: Requirements 3.7, 3.8, 3.9, 3.10
"""

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token

# Alias for routers that use "db" as the Depends name
db = get_db
from app.models.core import ProjectUser, User

security = HTTPBearer()

# ---------------------------------------------------------------------------
# 权限层级常量
# ---------------------------------------------------------------------------

PERMISSION_HIERARCHY: dict[str, int] = {"edit": 3, "review": 2, "readonly": 1}


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization header 解析 JWT，查询用户，验证 is_active 和 is_deleted。

    未认证或 token 无效时返回 401。
    """
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的认证凭据")

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="无效的认证凭据")

    # 仅接受 access token
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="无效的认证凭据")

    result = await db.execute(
        select(User).where(
            User.id == UUID(user_id),
            User.is_active == True,   # noqa: E712
            User.is_deleted == False,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")

    return user


# ---------------------------------------------------------------------------
# require_role
# ---------------------------------------------------------------------------


def require_role(allowed_roles: list[str]) -> Callable:
    """角色校验依赖工厂。

    用户角色不在 allowed_roles 列表中时返回 403 "权限不足"。
    """

    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role.value not in allowed_roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return current_user

    return dependency


# ---------------------------------------------------------------------------
# require_project_access
# ---------------------------------------------------------------------------


def require_project_access(min_permission: str = "readonly") -> Callable:
    """项目级权限校验依赖工厂。

    - admin 角色跳过检查
    - 其他角色查询 project_users 表，按 edit > review > readonly 层级比较
    - 权限不足返回 403
    """

    async def dependency(
        project_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # admin 跳过项目权限检查
        if current_user.role.value == "admin":
            return current_user

        # 查询 project_users 表
        result = await db.execute(
            select(ProjectUser).where(
                ProjectUser.project_id == project_id,
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
        project_user = result.scalar_one_or_none()

        if project_user is None:
            raise HTTPException(status_code=403, detail="权限不足")

        # 比较权限层级
        user_level = PERMISSION_HIERARCHY.get(
            project_user.permission_level.value, 0
        )
        required_level = PERMISSION_HIERARCHY.get(min_permission, 0)

        if user_level < required_level:
            raise HTTPException(status_code=403, detail="权限不足")

        return current_user

    return dependency
