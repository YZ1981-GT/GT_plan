"""``/api/ai-chat/metrics`` 只给管理员（spec llm-linkage-audit-practice-closure 任务 4 / ADR-LLM-010）。

该端点在 ``/api/`` 下、经网关对外可达，原实现零鉴权：任何人可读运行容量与模型路由状态。
内网 Prometheus 抓取走根路径 ``/metrics``（网关只代理 ``/api/``，见 frontend/docker/default.conf.template）。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app


def _user(role: str):
    return SimpleNamespace(id="u-1", username=role, role=SimpleNamespace(value=role))


async def _get(user=None):
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/api/ai-chat/metrics")
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_anonymous_request_is_rejected():
    resp = await _get()
    assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["auditor", "manager", "partner", "qc", "eqcr"])
async def test_non_admin_roles_are_forbidden(role):
    resp = await _get(_user(role))
    assert resp.status_code == 403
    assert "管理员" in resp.text


@pytest.mark.asyncio
async def test_admin_gets_prometheus_text():
    resp = await _get(_user("admin"))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
