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
    """FastAPI 依赖：创建不含用户的服务容器（公开端点使用）

    认证端点请直接使用 app.deps.get_current_user（已支持嵌套 Depends），
    需要 db/redis 时再各自 Depends 注入即可。
    """
    return ServiceContainer(db=db, redis=redis)
