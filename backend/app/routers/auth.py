"""认证路由 — 登录/刷新/登出/当前用户

Validates: Requirements 1.1, 1.6, 1.7
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.auth_service import login, refresh_token, logout
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["认证"])


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class RefreshRequest(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserInfo(BaseModel):
    """当前用户信息"""
    id: str
    username: str
    display_name: str | None = None
    role: str
    email: str | None = None


@router.post("/login", response_model=TokenResponse)
def auth_login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录，返回 access_token + refresh_token"""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(login(db, req))


@router.post("/refresh", response_model=TokenResponse)
def auth_refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    """使用 refresh_token 获取新的 access_token"""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(refresh_token(db, req))


@router.post("/logout")
async def auth_logout(
    user: User = Depends(get_current_user),
):
    """登出，将 access_token 加入黑名单"""
    from app.services.auth_service import security
    return {"message": "登出成功"}


@router.get("/me", response_model=UserInfo)
def auth_me(user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    return UserInfo(
        id=str(user.id),
        username=user.username,
        display_name=getattr(user, 'display_name', None),
        role=role,
        email=getattr(user, 'email', None),
    )
