"""认证服务 — 登录/刷新/登出/用户管理"""

from uuid import UUID

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
from app.models.base import UserRole
from app.models.core import User
from app.schemas.auth import TokenResponse, UserCreate, UserResponse, UserUpdate


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

async def refresh(refresh_token: str, redis: Redis, db: AsyncSession) -> dict:
    """验证 refresh_token 有效性，实现 token rotation。

    刷新前重新读取用户状态：停用 / 锁定用户的旧 refresh token 也必须立即失效，
    不能仅依赖 access token 的 ``get_current_user`` 校验。
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
    try:
        user_id = UUID(str(sub))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="refresh_token 用户信息无效")

    # 停用 / 锁定后不允许用旧 refresh token 换发新 token。
    user = (await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_active == True,  # noqa: E712
            User.is_deleted == False,  # noqa: E712
        )
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")

    # --- Token Rotation: 废弃旧 token，签发新 token 对 ---

    # 1. 将旧 refresh_token 加入黑名单
    old_ttl = await redis.ttl(rt_key)
    if old_ttl <= 0:
        old_ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis.set(bl_key, "1", ex=old_ttl)

    # 2. 删除旧 refresh_token 记录
    await redis.delete(rt_key)

    # 3. 生成新 token 对
    token_data = {"sub": str(user_id)}
    new_access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    # 4. 存储新 refresh_token 到 Redis
    new_rt_key = _refresh_token_key(new_refresh_token)
    new_rt_ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis.set(new_rt_key, str(user_id), ex=new_rt_ttl)

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
# update_user（管理员改用户：邮箱 / 角色 / 启用 / 重置密码）
# ---------------------------------------------------------------------------

async def update_user(
    db: AsyncSession,
    *,
    actor_id: UUID,
    user_id: UUID,
    data: UserUpdate,
) -> UserResponse:
    """只 flush 不 commit（router 统一提交）。

    - 不能停用自己、不能把自己降成非管理员（防止误操作把自己关在门外）；
    - 停用 / 降级一个启用中的管理员时，锁住全部启用中的管理员行再计数：改完必须仍有至少一个（并发两个管理员互相停用也挡得住）；
    - 邮箱唯一约束是全表的（含已删除用户），按全表查重；
    - 密码重置 / 启用状态变化经统一审计 logger 留痕。
    停用后该用户下一次请求即 401（``get_current_user`` 每次请求都校验 ``is_active``），登录和 refresh 也会被拒。
    """
    user = (await db.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)  # noqa: E712
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    fields = data.model_dump(exclude_unset=True)
    password = fields.pop("password", None)
    old_active = bool(user.is_active)
    old_role = user.role.value if hasattr(user.role, "value") else str(user.role)
    new_role = fields.get("role", user.role)
    new_active = fields.get("is_active", user.is_active)

    if user.id == actor_id:
        if new_active is False:
            raise HTTPException(status_code=409, detail="不能停用自己的账号")
        if user.role == UserRole.admin and new_role != UserRole.admin:
            raise HTTPException(status_code=409, detail="不能取消自己的管理员角色")

    if user.role == UserRole.admin and user.is_active and (new_role != UserRole.admin or new_active is False):
        active_admins = (await db.execute(
            select(User.id).where(
                User.role == UserRole.admin,
                User.is_active == True,  # noqa: E712
                User.is_deleted == False,  # noqa: E712
            ).with_for_update()
        )).scalars().all()
        if not [uid for uid in active_admins if uid != user.id]:
            raise HTTPException(status_code=409, detail="至少要保留一个启用的管理员")

    if "email" in fields and fields["email"] != user.email:
        taken = (await db.execute(
            select(User.id).where(User.email == fields["email"], User.id != user.id)
        )).first()
        if taken:
            raise HTTPException(status_code=409, detail="邮箱已被其他用户使用")

    for key, value in fields.items():
        setattr(user, key, value)
    if password:
        user.hashed_password = hash_password(password)
    await db.flush()
    await db.refresh(user)

    security_changes: dict[str, object] = {}
    if password:
        security_changes["password_reset"] = True
    if old_active != bool(user.is_active):
        security_changes["is_active"] = {"from": old_active, "to": bool(user.is_active)}
    new_role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    if old_role != new_role_value:
        security_changes["role"] = {"from": old_role, "to": new_role_value}
    if security_changes:
        # logger 自身对 Redis/降级队列失败是 fail-open；审计故障不能让用户管理写入回滚。
        try:
            from app.services.audit_logger_enhanced import audit_logger

            await audit_logger.log_action(
                user_id=actor_id,
                action="user.security_changed",
                object_type="user",
                object_id=user.id,
                details=security_changes,
            )
        except Exception:  # noqa: BLE001
            pass

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
