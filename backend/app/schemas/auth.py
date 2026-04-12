"""认证相关 Pydantic 模型"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.base import UserRole


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """登录请求"""

    username: str
    password: str


class RefreshRequest(BaseModel):
    """刷新令牌请求"""

    refresh_token: str


class UserCreate(BaseModel):
    """创建用户请求（管理员使用）"""

    username: str
    email: EmailStr
    password: str
    role: UserRole
    office_code: str | None = None


class UserRegister(BaseModel):
    """用户注册请求（公开接口）"""

    username: str
    email: EmailStr
    password: str


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """用户响应（排除密码字段）"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    role: UserRole
    office_code: str | None = None
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """登录/刷新令牌响应"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
