"""公式历史经 HTTP 读写的共用夹具（非测试模块；spec formula-hub-integrity-closure 第 2 轮 D-1 / D-2）。

按生产注册挂 router（``tests.authz_world.build_app``，前缀与注册时的依赖与生产相同），只替换
``get_current_user`` / ``get_db``（``assert_world_overrides`` 校验键集合），鉴权链 ``require_project_access`` /
``require_role`` / ``assert_project_permission`` 真实运行；请求经 ASGI 发在本用例的事件循环里，会话即用例的 SQLite 会话。
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_log_models import AuditLogEntry
from app.models.core import User
from tests.authz_world import assert_gates_are_production, assert_world_overrides, build_app


@asynccontextmanager
async def http_client(db, user: User, *routers: APIRouter) -> AsyncIterator[AsyncClient]:
    if not routers:
        from app.routers import formula_audit_log

        routers = (formula_audit_log.router,)
    api = build_app(*routers)

    async def _db():
        yield db

    user_id = user.id

    async def _user() -> User:
        # 与生产 get_current_user 一样每个请求按 id 重新取（端点 rollback 后同一会话里的旧对象已过期）
        return await db.get(User, user_id)

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    assert_world_overrides(api)
    assert_gates_are_production()
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://fhic-history") as http:
        yield http


async def history(http: AsyncClient, project_id: uuid.UUID, year: int, **params: Any) -> list[dict[str, Any]]:
    """``GET /api/formula-audit-log/{pid}/{year}``（与 FormulaHistoryTab 同一请求，limit 200）。"""
    resp = await http.get(f"/api/formula-audit-log/{project_id}/{year}", params={"limit": 200, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def payload_of(db, entry_id: str) -> dict[str, Any]:
    """按历史条目 id 读审计链原始载荷（核对 ``year`` 的落库形态）。"""
    raw = (await db.execute(sa.select(AuditLogEntry.payload).where(AuditLogEntry.id == uuid.UUID(entry_id)))).scalar_one()
    return raw if isinstance(raw, dict) else json.loads(raw)
