"""构建器真库用例共用的请求客户端（advanced-query-linkage-closure 任务 9~11）。

请求经 httpx ASGI 真发到**生产注册**的 query_builder router（``authz_world.build_app``），只替换 ``get_current_user``
（每次请求指定身份）与 ``get_db``（真库回滚事务会话 ``pg_rollback_session``，结束整体回滚）；Redis（查询缓存与
OwnershipGuard 越权审计的队列）换成独占的 fakeredis、可区分拒绝的审计写入换成空操作——只读，不在共享库与共享 Redis
留任何东西。真实账号（e2e_manager 等）按用户名从库里读出，不改它们的任何数据。
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import fakeredis
import fakeredis.aioredis
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.redis as core_redis
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.models.core import User
from app.routers import query_builder
from app.services.custom_query import audit_helper
from tests.authz_world import build_app

QB = "/api/query"


class BuilderClient:
    """按身份发构建器请求；``admin`` 是不落库的系统管理员。"""

    def __init__(self, session: AsyncSession, http: AsyncClient, api: Any) -> None:
        self.session = session
        self.http = http
        self.api = api
        self.admin = User(id=uuid.uuid4(), username="aql-b3-admin", email="aql-b3@test.invalid", hashed_password="x",
                          role=UserRole.admin, is_active=True)

    async def real_user(self, username: str) -> User:
        user = (await self.session.execute(select(User).where(User.username == username))).scalar_one_or_none()
        assert user is not None, f"真库没有账号 {username}（身份事实变了，按 design §10.2 同一口径换人）"
        return user

    async def request(self, user: User, method: str, path: str, json: Any = None) -> Response:
        async def _user() -> User:
            return user

        self.api.dependency_overrides[get_current_user] = _user
        return await self.http.request(method, f"{QB}{path}", json=json)

    async def execute(self, user: User, body: dict) -> Response:
        return await self.request(user, "POST", "/execute", body)

    async def ok(self, user: User, body: dict) -> dict:
        response = await self.execute(user, body)
        assert response.status_code == 200, response.text[:800]
        return response.json()


@asynccontextmanager
async def builder_client(session: AsyncSession, monkeypatch: Any) -> AsyncIterator[BuilderClient]:
    """真库构建器客户端（夹具 ``builder`` 用）：``session`` 是回滚事务会话。"""
    redis = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(core_redis, "redis_client", redis)
    monkeypatch.setattr(core_redis, "_redis_client", redis)

    async def _no_audit(**_kwargs):  # 可区分拒绝的审计不落真库（被测的是作用域与口径）
        return True

    monkeypatch.setattr(audit_helper, "_log_unthrottled", _no_audit)
    api = build_app(query_builder.router)

    async def _db():
        yield session

    api.dependency_overrides[get_db] = _db
    try:
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://aql-b3") as http:
            yield BuilderClient(session, http, api)
    finally:
        await redis.aclose()
