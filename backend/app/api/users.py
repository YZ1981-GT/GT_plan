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
    """获取当前用户信息。

    Validates: Requirements 3.13
    """
    return await auth_service.get_current_user_profile(
        user_id=str(current_user.id),
        db=db,
    )
