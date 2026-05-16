"""依赖注入 — get_current_user, require_role, require_project_access

Validates: Requirements 3.7, 3.8, 3.9, 3.10
"""

import logging
from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_token

# Alias for routers that use "db" as the Depends name
db = get_db

# Alias for sync routers (consolidation module etc.) that use synchronous ORM
from app.core.database import get_sync_db  # noqa: E402
sync_db = get_sync_db

from app.models.core import ProjectUser, User

logger = logging.getLogger(__name__)

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

    包含 access token 黑名单检查（Redis 不可用时降级跳过）。
    未认证或 token 无效时返回 401。
    """
    token = credentials.credentials

    # 黑名单检查（Redis 不可用时降级跳过，不阻断请求）
    try:
        from app.core.redis import redis_client
        from app.services.auth_service import is_token_blacklisted
        if await is_token_blacklisted(token, redis_client):
            raise HTTPException(status_code=401, detail="Token 已被吊销")
    except HTTPException:
        raise
    except Exception:
        logger.debug("Redis unavailable for blacklist check, skipping")

    # Phase 14: SoD 角色变更黑名单检查
    # 角色变更后旧 token 在 5 秒内失效（Redis key: sod_revoke:{user_id}:{project_id}）
    # 注意：当前实现只检查全局撤销（sod_revoke:{user_id}），不检查项目级撤销
    # （sod_revoke:{user_id}:{project_id}）。如需项目级 SoD 检查，需在此处扩展。
    try:
        from app.core.redis import redis_client as _redis
        if _redis:
            # 从 token payload 提取 user_id，检查是否有 SoD 撤销标记
            _payload_pre = decode_token(token)
            _uid = _payload_pre.get("sub")
            if _uid:
                # 检查全局 SoD 撤销（不限项目）
                _sod_key = f"sod_revoke:{_uid}:*"
                # 简化实现：检查 sod_revoke:{user_id} 前缀
                _sod_global = await _redis.get(f"sod_revoke:{_uid}")
                if _sod_global:
                    raise HTTPException(status_code=403, detail={
                        "error_code": "SOD_TOKEN_REVOKED",
                        "message": "角色变更后 Token 已失效，请重新登录",
                    })
    except HTTPException:
        raise
    except Exception:
        pass  # Redis 不可用时降级跳过

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
    - Redis 缓存权限查询结果（TTL=5min）
    - Redis 不可用时降级为直接查库
    - 权限不足返回 403
    """
    # PERM_CACHE_TTL 使用模块级常量（见下方），此处不重复定义

    async def dependency(
        project_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # admin 跳过项目权限检查
        if current_user.role.value == "admin":
            return current_user

        # Try Redis cache first
        cached_level = await _get_cached_permission(current_user.id, project_id)
        if cached_level is not None:
            user_level = PERMISSION_HIERARCHY.get(cached_level, 0)
            required_level = PERMISSION_HIERARCHY.get(min_permission, 0)
            if user_level < required_level:
                raise HTTPException(status_code=403, detail="权限不足")
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

        # Cache the permission level
        level_value = project_user.permission_level.value
        await _set_cached_permission(current_user.id, project_id, level_value)

        # 比较权限层级
        user_level = PERMISSION_HIERARCHY.get(level_value, 0)
        required_level = PERMISSION_HIERARCHY.get(min_permission, 0)

        if user_level < required_level:
            raise HTTPException(status_code=403, detail="权限不足")

        return current_user

    return dependency


# ---------------------------------------------------------------------------
# Permission cache helpers (Redis, graceful degradation)
# ---------------------------------------------------------------------------

PERM_CACHE_TTL = 300  # 5 minutes


async def _get_cached_permission(user_id: UUID, project_id: UUID) -> str | None:
    """从 Redis 获取缓存的权限级别，不可用时返回 None（降级查库）。"""
    try:
        from app.core.redis import redis_client
        if redis_client is None:
            return None
        cache_key = f"perm:{user_id}:{project_id}"
        cached = await redis_client.get(cache_key)
        return cached.decode() if cached else None
    except Exception:
        return None


async def _set_cached_permission(user_id: UUID, project_id: UUID, level: str) -> None:
    """写入权限缓存。"""
    try:
        from app.core.redis import redis_client
        if redis_client is None:
            return
        cache_key = f"perm:{user_id}:{project_id}"
        await redis_client.setex(cache_key, PERM_CACHE_TTL, level)
    except Exception:
        pass


async def invalidate_permission_cache(user_id: UUID, project_id: UUID) -> None:
    """权限变更时主动失效缓存。"""
    try:
        from app.core.redis import redis_client
        if redis_client is None:
            return
        cache_key = f"perm:{user_id}:{project_id}"
        await redis_client.delete(cache_key)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# check_consol_lock — 合并锁定检查
# ---------------------------------------------------------------------------


async def check_consol_lock(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """检查项目是否被合并锁定，锁定时返回 423。

    F6 修复（v3 P0-1 / Q1）：用 SAVEPOINT 包住 SELECT，列不存在时
    回滚 SAVEPOINT 不破坏外层事务（避免下游 user 对象 expired 引发 MissingGreenlet）。
    """
    from sqlalchemy import text as sa_text
    try:
        async with db.begin_nested():  # SAVEPOINT
            result = await db.execute(
                sa_text("SELECT consol_lock FROM projects WHERE id = :pid"),
                {"pid": str(project_id)},
            )
            row = result.first()
            if row and row[0]:
                raise HTTPException(status_code=423, detail="项目已被合并锁定，请等待合并完成后再操作")
    except HTTPException:
        raise
    except Exception:
        # Column may not exist — SAVEPOINT 已自动回滚，外层事务无影响
        # 不再 await db.rollback()（这是 F6 根因：让所有已 SELECT 对象 expired）
        pass


# ---------------------------------------------------------------------------
# get_visible_projects — 项目可见性过滤
# ---------------------------------------------------------------------------


async def get_visible_project_ids(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UUID]:
    """返回当前用户可见的项目 ID 列表。

    admin/partner 可见所有项目，其他角色只能看到自己参与的项目。
    """
    if current_user.role.value in ("admin", "partner"):
        from app.models.core import Project
        result = await db.execute(
            select(Project.id).where(Project.is_deleted == False)  # noqa: E712
        )
        return [r[0] for r in result.all()]

    result = await db.execute(
        select(ProjectUser.project_id).where(
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    )
    return [r[0] for r in result.all()]


# ---------------------------------------------------------------------------
# get_user_scope_cycles — 循环级权限过滤
# ---------------------------------------------------------------------------


async def get_user_scope_cycles(
    current_user: User,
    project_id: UUID,
    db: AsyncSession,
) -> list[str] | None:
    """获取用户在指定项目中的循环范围限制。

    admin/partner 返回 None（不限制）。
    """
    if current_user.role.value in ("admin", "partner"):
        return None
    result = await db.execute(
        select(ProjectUser.scope_cycles).where(
            ProjectUser.project_id == project_id,
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    )
    sc = result.scalar()
    if sc and isinstance(sc, str) and sc.strip():
        return [c.strip() for c in sc.split(",") if c.strip()]
    return None
