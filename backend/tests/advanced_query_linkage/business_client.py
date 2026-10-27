"""业务视图真库用例共用的请求客户端（advanced-query-linkage-closure 任务 17~22）。

请求经 httpx ASGI 真发到**生产注册**的 custom_query router（``authz_world.build_app``），只替换 ``get_current_user``
（不落库的系统管理员，不触达成员判定）与 ``get_db``（真库回滚事务会话 ``pg_rollback_session``，结束整体回滚）；Redis
（查询缓存与越权审计的队列）换成独占的 fakeredis、审计写入换成空操作——只读，不在共享库与共享 Redis 留任何东西。
同一会话里用例自己造的行（只写【测试】/【UAT】项目）对被测请求可见，结束随回滚消失。
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import fakeredis
import fakeredis.aioredis
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.redis as core_redis
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.models.core import User
from app.routers import custom_query
from app.services.custom_query import audit_helper
from tests.advanced_query_linkage.gold import AUDIT_YEAR
from tests.authz_world import build_app

EXEC = "/api/custom-query/execute"
PAGE = 2000


class BusinessClient:
    """以系统管理员发业务视图请求；``session`` 即被测请求用的回滚事务会话。"""

    def __init__(self, session: AsyncSession, http: AsyncClient) -> None:
        self.session = session
        self.http = http

    async def execute(self, project_id: uuid.UUID, source: str, **body: Any) -> Response:
        payload = {"project_id": str(project_id), "year": AUDIT_YEAR, "source": source, "limit": 100, **body}
        return await self.http.post(EXEC, json=payload)

    async def ok(self, project_id: uuid.UUID, source: str, **body: Any) -> dict:
        response = await self.execute(project_id, source, **body)
        assert response.status_code == 200, response.text[:800]
        return response.json()

    async def error(self, project_id: uuid.UUID, source: str, status: int, **body: Any) -> dict:
        response = await self.execute(project_id, source, **body)
        assert response.status_code == status, response.text[:800]
        return response.json()["detail"]

    async def all_rows(self, project_id: uuid.UUID, source: str, **body: Any) -> tuple[dict, list[dict]]:
        """逐页取全量（每页 2,000 行）；返回最后一页的响应与全部行。"""
        rows: list[dict] = []
        offset = 0
        while True:
            data = await self.ok(project_id, source, limit=PAGE, offset=offset, **body)
            rows.extend(data["rows"])
            offset += PAGE
            if offset >= data["total"]:
                return data, rows


@asynccontextmanager
async def business_client(session: AsyncSession, monkeypatch: Any) -> AsyncIterator[BusinessClient]:
    """真库业务视图客户端（夹具 ``business`` 用）：``session`` 是回滚事务会话。"""
    redis = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(core_redis, "redis_client", redis)
    monkeypatch.setattr(core_redis, "_redis_client", redis)

    async def _no_audit(**_kwargs):  # 审计不落真库（被测的是取数口径，不是审计）
        return True

    monkeypatch.setattr(audit_helper, "_log_unthrottled", _no_audit)
    api = build_app(custom_query.router)
    admin = User(id=uuid.uuid4(), username="aql-b5-admin", email="aql-b5@test.invalid", hashed_password="x",
                 role=UserRole.admin, is_active=True)

    async def _db():
        yield session

    async def _user() -> User:
        return admin

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    try:
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://aql-b5") as http:
            yield BusinessClient(session, http)
    finally:
        await redis.aclose()
