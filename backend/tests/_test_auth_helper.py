"""Shared test helper: 标准 dep_overrides 注入

解决 `dep_overrides 闭包陷阱` + 401 Unauthorized 问题（V3 收尾测试债）。

用法：

    from tests._test_auth_helper import override_auth

    @pytest_asyncio.fixture
    async def client(db_session, seeded_db):
        from app.main import app
        async with override_auth(app, db_session=db_session) as c:
            yield c

注意：admin 角色绕过 require_project_access 项目权限检查（见 deps.py 的 admin 分支）。
"""
from __future__ import annotations

import contextlib
import uuid
from typing import AsyncIterator

import fakeredis.aioredis
import pytest_asyncio  # noqa: F401  -- ensure available for fixture wrappers

from app.models.base import UserRole


class FakeAuthUser:
    """生产 User 模型的最小测试替身（admin 角色，绕过项目权限）。

    role 字段必须是 UserRole enum（生产代码 deps.py:195 调用 `role.value`）。
    """

    def __init__(
        self,
        user_id: uuid.UUID | None = None,
        username: str = "test_admin",
        role: UserRole | str = UserRole.admin,
        is_active: bool = True,
        is_deleted: bool = False,
    ) -> None:
        self.id = user_id or uuid.UUID("00000000-0000-0000-0000-000000000099")
        self.username = username
        # 接受字符串/枚举两种传参，统一存为 enum
        self.role = role if isinstance(role, UserRole) else UserRole(role)
        self.is_active = is_active
        self.is_deleted = is_deleted
        self.email = f"{username}@test.local"


@contextlib.asynccontextmanager
async def override_auth(
    app,
    *,
    db_session,
    user: FakeAuthUser | None = None,
    fake_redis=None,
) -> AsyncIterator:
    """统一注入 get_db / get_redis / get_current_user override。

    Yields the AsyncClient ready for API testing.
    """
    from httpx import ASGITransport, AsyncClient
    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.deps import get_current_user

    user = user or FakeAuthUser()
    fake_redis = fake_redis or fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _override_db():
        yield db_session

    async def _override_redis():
        yield fake_redis

    async def _override_current_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()
