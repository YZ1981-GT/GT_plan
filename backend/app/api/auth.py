"""认证路由 — 登录/刷新/登出

Validates: Requirements 3.1, 3.2, 3.11
"""

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserRegister
from app.services import auth_service

router = APIRouter(tags=["认证"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenResponse:
    """用户登录，返回 access_token + refresh_token。

    Validates: Requirements 3.1
    """
    return await auth_service.login(
        username=body.username,
        password=body.password,
        db=db,
        redis=redis,
    )


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    redis: Redis = Depends(get_redis),
) -> dict:
    """使用 refresh_token 获取新的 access_token。

    Validates: Requirements 3.2
    """
    new_access_token = await auth_service.refresh(
        refresh_token=body.refresh_token,
        redis=redis,
    )
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    redis: Redis = Depends(get_redis),
) -> dict:
    """登出，将 refresh_token 加入黑名单使其失效。

    Validates: Requirements 3.11
    """
    await auth_service.logout(
        refresh_token=body.refresh_token,
        redis=redis,
    )
    return {"message": "登出成功"}


@router.post("/register", response_model=dict)
async def register(
    body: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """用户注册（公开接口，不需要认证）。

    注册成功后返回用户信息，但不会自动登录。
    """
    # 将 UserRegister 转换为 UserCreate，设置默认角色为审计员
    from app.schemas.auth import UserCreate
    from app.models.base import UserRole

    user_data = UserCreate(
        username=body.username,
        email=body.email,
        password=body.password,
        role=UserRole.auditor,
    )

    user = await auth_service.create_user(user_data=user_data, db=db)
    return {
        "message": "注册成功",
        "user_id": str(user.id),
        "username": user.username,
    }
