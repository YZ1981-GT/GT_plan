"""认证服务 — 登录/刷新/登出/用户管理（含账号锁定）

Validates: Requirements 1.3, 1.6
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis import get_redis
from app.models.core import User
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------


class TokenPair(BaseModel):
    """Token 对响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class RefreshRequest(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7
TOKEN_BLACKLIST_PREFIX = "token:blacklist:"

# ---------------------------------------------------------------------------
# 密码哈希（SHA-256 + random salt）
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """使用 SHA-256 + 随机盐哈希密码，返回格式: salt$hash"""
    import secrets
    import hashlib

    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"


def verify_password(password: str, stored: str) -> bool:
    """验证密码是否与存储的哈希匹配"""
    import hashlib

    try:
        salt, _ = stored.split("$")
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        return h == _
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# JWT Token 创建
# ---------------------------------------------------------------------------


def create_access_token(user_id: str, username: str, role: str) -> str:
    """创建 access token（包含用户信息）"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """创建 refresh token"""
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_tokens(user_id: str, username: str, role: str) -> TokenPair:
    """创建 Token 对"""
    return TokenPair(
        access_token=create_access_token(user_id, username, role),
        refresh_token=create_refresh_token(user_id),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


# ---------------------------------------------------------------------------
# 账号锁定（Redis）
# ---------------------------------------------------------------------------


async def check_lockout(username: str) -> tuple[bool, int]:
    """检查账号是否被锁定，返回 (是否锁定, 剩余秒数)"""
    redis = get_redis()
    key = f"lockout:{username}"
    attempts = await redis.get(key)
    if attempts and int(attempts) >= MAX_LOGIN_ATTEMPTS:
        ttl = await redis.ttl(key)
        return True, max(ttl, 0)
    return False, 0


async def record_failed_attempt(username: str) -> None:
    """记录登录失败，增加失败计数"""
    redis = get_redis()
    key = f"lockout:{username}"
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, LOCKOUT_DURATION_MINUTES * 60)
    await pipe.execute()


async def clear_lockout(username: str) -> None:
    """清除账号锁定"""
    redis = get_redis()
    await redis.delete(f"lockout:{username}")


# ---------------------------------------------------------------------------
# 登录 / 刷新 / 登出
# ---------------------------------------------------------------------------


async def login(db: Session, req: LoginRequest) -> TokenPair:
    """用户登录：验证凭据 + 生成 Token"""
    # 检查账号锁定
    locked, remaining = await check_lockout(req.username)
    if locked:
        raise HTTPException(
            status_code=403,
            detail=f"账号已锁定，请在 {remaining} 秒后重试"
        )

    # 查询用户（支持 hashed_password 或 password_hash 字段）
    user = db.query(User).filter(
        User.username == req.username,
        User.is_deleted == False  # noqa: E712
    ).first()

    # 密码验证（支持两种字段名）
    password_hash = getattr(user, 'hashed_password', None) or getattr(user, 'password_hash', None)
    if not user or not password_hash or not verify_password(req.password, password_hash):
        await record_failed_attempt(req.username)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 登录成功，清除锁定
    await clear_lockout(req.username)

    # 获取角色值
    role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    return create_tokens(str(user.id), user.username, role)


async def refresh_token(db: Session, req: RefreshRequest) -> TokenPair:
    """使用 refresh_token 刷新 access_token"""
    try:
        payload = jwt.decode(
            req.refresh_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="无效的 token 类型")
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的 refresh token")

    user = db.query(User).filter(
        User.id == payload["sub"],
        User.is_deleted == False  # noqa: E712
    ).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    return create_tokens(str(user.id), user.username, role)


async def logout(token: str) -> None:
    """登出：将 token 加入黑名单"""
    redis = get_redis()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        exp = payload.get("exp", 0)
        now = datetime.now(timezone.utc).timestamp()
        ttl = max(int(exp - now), 0)
        if ttl > 0:
            await redis.setex(f"{TOKEN_BLACKLIST_PREFIX}{token}", ttl, "1")
    except JWTError:
        pass


async def is_token_blacklisted(token: str) -> bool:
    """检查 token 是否在黑名单中"""
    redis = get_redis()
    return await redis.exists(f"{TOKEN_BLACKLIST_PREFIX}{token}")
