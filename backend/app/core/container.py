"""轻量级服务容器 — 统一依赖注入

提供 ServiceContainer 作为 FastAPI 依赖，将 db/redis/user 三个核心依赖
打包为一个对象，减少路由函数参数列表长度，便于测试时整体 mock。

用法：
    from app.core.container import get_container, ServiceContainer

    @router.post("/xxx")
    async def handler(ctx: ServiceContainer = Depends(get_container)):
        # ctx.db — 数据库会话
        # ctx.redis — Redis 客户端
        # ctx.user — 当前用户（可选）
        # ctx.user_id — 当前用户 ID 字符串
        pass

注意：这是增量引入，不强制所有路由迁移。新代码推荐使用，旧代码保持不变。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.models.core import User


@dataclass
class ServiceContainer:
    """请求级服务容器，封装 db/redis/user 三个核心依赖"""

    db: AsyncSession
    redis: Redis
    user: Optional[User] = field(default=None)

    @property
    def user_id(self) -> str:
        """当前用户 ID（字符串），未认证时返回空字符串"""
        if self.user and hasattr(self.user, "id"):
            return str(self.user.id)
        return ""

    @property
    def is_admin(self) -> bool:
        """当前用户是否为管理员"""
        if self.user and hasattr(self.user, "role"):
            return self.user.role.value == "admin" if hasattr(self.user.role, "value") else self.user.role == "admin"
        return False


async def get_container(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ServiceContainer:
    """FastAPI 依赖：创建不含用户的服务容器（公开端点使用）"""
    return ServiceContainer(db=db, redis=redis)


async def get_authenticated_container(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ServiceContainer:
    """FastAPI 依赖：创建含当前用户的服务容器（认证端点使用）

    注意：需要在路由中额外调用 get_current_user 并赋值到 ctx.user，
    或者使用 get_container_with_user 依赖。
    """
    from app.deps import get_current_user
    # 这里不能直接调用 get_current_user（它需要 Request），
    # 所以提供不含 user 的容器，路由中自行注入 user
    return ServiceContainer(db=db, redis=redis)
