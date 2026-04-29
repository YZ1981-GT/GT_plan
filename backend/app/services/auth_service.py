"""认证服务 — 登录/刷新/登出/用户管理"""

from fastapi import HTTPException
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.core import User
from app.schemas.auth import TokenResponse, UserCreate, UserResponse


# ---------------------------------------------------------------------------
# Redis key helpers
# ---------------------------------------------------------------------------

def _login_fail_key(username: str) -> str:
    return f"login_fail:{username}"


def _refresh_token_key(token: str) -> str:
    return f"refresh_token:{token}"


def _blacklist_key(token: str) -> str:
    return f"blacklist:{token}"


# ---------------------------------------------------------------------------
# is_token_blacklisted（公开函数，供 deps.py 使用）
# ---------------------------------------------------------------------------

async def is_token_blacklisted(token: str, redis: Redis) -> bool:
    """检查 access/refresh token 是否在黑名单中。"""
    bl_key = _blacklist_key(token)
    return bool(await redis.exists(bl_key))


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

async def login(
    username: str,
    password: str,
    db: AsyncSession,
    redis: Redis,
) -> TokenResponse:
    """验证用户名密码，检查锁定状态，成功后生成 token 对。"""

    fail_key = _login_fail_key(username)

    # 检查账号锁定
    fail_count = await redis.get(fail_key)
    if fail_count is not None and int(fail_count) >= settings.LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=423, detail="账号已锁定，请30分钟后重试")

    # 查询用户
    result = await db.execute(
        select(User).where(
            User.username == username,
            User.is_deleted == False,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()

    # 用户不存在或密码错误
    if user is None or not verify_password(password, user.hashed_password):
        # 递增失败计数
        await redis.incr(fail_key)
        await redis.expire(fail_key, settings.LOGIN_LOCK_MINUTES * 60)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 登录成功 — 清除失败计数
    await redis.delete(fail_key)

    # 生成 token 对
    token_data = {"sub": str(user.id)}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # 存储 refresh_token 到 Redis
    rt_key = _refresh_token_key(refresh_token)
    rt_ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis.set(rt_key, str(user.id), ex=rt_ttl)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------

async def refresh(refresh_token: str, redis: Redis) -> dict:
    """验证 refresh_token 有效性，实现 token rotation。

    Token Rotation 安全机制：
    - 每次刷新时废弃旧 refresh_token（加入黑名单）
    - 签发全新的 access_token + refresh_token 对
    - 旧 token 立即失效，防止泄露后被持续利用
    """

    # 检查 refresh_token 是否存在于 Redis
    rt_key = _refresh_token_key(refresh_token)
    if not await redis.exists(rt_key):
        raise HTTPException(status_code=401, detail="refresh_token 无效或已过期")

    # 检查是否在黑名单中
    bl_key = _blacklist_key(refresh_token)
    if await redis.exists(bl_key):
        raise HTTPException(status_code=401, detail="refresh_token 已失效")

    # 解码并验证 token
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="refresh_token 无效")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="token 类型错误")

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="token 缺少用户信息")

    # --- Token Rotation: 废弃旧 token，签发新 token 对 ---

    # 1. 将旧 refresh_token 加入黑名单
    old_ttl = await redis.ttl(rt_key)
    if old_ttl <= 0:
        old_ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis.set(bl_key, "1", ex=old_ttl)

    # 2. 删除旧 refresh_token 记录
    await redis.delete(rt_key)

    # 3. 生成新 token 对
    token_data = {"sub": sub}
    new_access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    # 4. 存储新 refresh_token 到 Redis
    new_rt_key = _refresh_token_key(new_refresh_token)
    new_rt_ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis.set(new_rt_key, sub, ex=new_rt_ttl)

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
    }


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------

async def logout(refresh_token: str, redis: Redis) -> None:
    """将 refresh_token 加入黑名单并删除 Redis 中的存储。"""

    # 尝试获取 token 剩余有效期作为黑名单 TTL
    rt_key = _refresh_token_key(refresh_token)
    ttl = await redis.ttl(rt_key)
    if ttl <= 0:
        ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400

    # 加入黑名单
    bl_key = _blacklist_key(refresh_token)
    await redis.set(bl_key, "1", ex=ttl)

    # 删除 refresh_token 记录
    await redis.delete(rt_key)


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------

async def create_user(user_data: UserCreate, db: AsyncSession) -> UserResponse:
    """创建用户，密码 bcrypt 哈希存储。"""

    # 检查用户名是否已存在
    existing_username = await db.execute(
        select(User).where(User.username == user_data.username, User.is_deleted == False)  # noqa: E712
    )
    if existing_username.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 检查邮箱是否已存在
    existing_email = await db.execute(
        select(User).where(User.email == user_data.email, User.is_deleted == False)  # noqa: E712
    )
    if existing_email.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        role=user_data.role,
        office_code=user_data.office_code,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# get_current_user_profile
# ---------------------------------------------------------------------------

async def get_current_user_profile(
    user_id: str,
    db: AsyncSession,
) -> UserResponse:
    """查询当前用户信息。"""

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_deleted == False,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserResponse.model_validate(user)
