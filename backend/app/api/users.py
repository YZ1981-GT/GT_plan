"""用户路由 — 创建用户 / 获取当前用户信息

Validates: Requirements 3.12, 3.13
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.schemas.auth import UserCreate, UserResponse
from app.services import auth_service

router = APIRouter(tags=["用户"])


@router.get("/")
async def list_users(
    db: AsyncSession = Depends(get_db),
):
    """获取用户列表（用于底稿分配、复核人选择等下拉框）"""
    from sqlalchemy import select
    result = await db.execute(
        select(User).where(User.is_deleted == False).order_by(User.username)  # noqa: E712
    )
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "username": u.username,
            "full_name": u.full_name if hasattr(u, 'full_name') else u.username,
            "email": u.email if hasattr(u, 'email') else None,
            "role": u.role if hasattr(u, 'role') else "auditor",
        }
        for u in users
    ]


@router.post("/", response_model=UserResponse)
async def create_user(
    body: UserCreate,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """创建用户（仅 admin 角色）。

    Validates: Requirements 3.12
    """
    return await auth_service.create_user(user_data=body, db=db)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """获取当前用户信息（含角色权限列表，供前端权限检查使用）。

    Validates: Requirements 3.13
    """
    profile = await auth_service.get_current_user_profile(
        user_id=str(current_user.id),
        db=db,
    )
    # 注入权限列表（从后端权限矩阵派生，防止前后端权限表不同步）
    from app.services.permission_service import ROLE_PERMISSION_MATRIX
    role_str = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    perms = ROLE_PERMISSION_MATRIX.get(role_str, set())
    profile.permissions = [p.value if hasattr(p, 'value') else str(p) for p in perms]
    return profile
