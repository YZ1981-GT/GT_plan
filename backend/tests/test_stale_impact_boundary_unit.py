"""Unit tests for GET /api/linkage-bus/impact-by-addr boundary conditions.

Task 3.9 (acnr-consumer-wiring): example-based boundary tests for the
stale_impact-by-addr endpoint implemented in task 3.7.

Covers three boundary cases:
1. empty/whitespace addr_id → HTTP 400 ("addr_id is required")
2. stale_engine.is_degraded == True → HTTP 503
3. valid addr_id + non-degraded engine → HTTP 200 with correct response schema

Validates: Requirements 5.5, 5.6
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.models.core import UserRole
from app.routers import linkage_bus
from app.routers.linkage_bus import router


# ─── Fixtures ────────────────────────────────────────────────────────────────

_PROJECT_ID = str(uuid.uuid4())


class _FakeUser:
    id = uuid.uuid4()
    username = "test_user"
    role = UserRole.admin


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with the linkage-bus router + auth override."""
    app = FastAPI()
    app.include_router(router)

    async def _user():
        return _FakeUser()

    app.dependency_overrides[get_current_user] = _user
    return app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ─── Case 1: empty / whitespace addr_id → 400 ───────────────────────────────


@pytest.mark.asyncio
async def test_empty_addr_id_returns_400(monkeypatch):
    """空 addr_id → 400 且 detail 为 'addr_id is required'（Req 5.5）。"""
    # engine 状态无关紧要：400 在 degraded 检查之前触发
    # is_degraded 是只读 property，需 patch 其后端字段 _degraded
    monkeypatch.setattr(linkage_bus.stale_engine, "_degraded", False, raising=False)

    app = _make_app()
    async with _client(app) as client:
        resp = await client.get(
            "/api/linkage-bus/impact-by-addr",
            params={"addr_id": "", "project_id": _PROJECT_ID},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "addr_id is required"


@pytest.mark.asyncio
async def test_whitespace_addr_id_returns_400(monkeypatch):
    """纯空白 addr_id → 400（Req 5.5，strip 后视为空）。"""
    monkeypatch.setattr(linkage_bus.stale_engine, "_degraded", False, raising=False)

    app = _make_app()
    async with _client(app) as client:
        resp = await client.get(
            "/api/linkage-bus/impact-by-addr",
            params={"addr_id": "   ", "project_id": _PROJECT_ID},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "addr_id is required"


# ─── Case 2: engine degraded → 503 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_engine_degraded_returns_503(monkeypatch):
    """引擎降级 → 503（Req 5.6）。"""
    monkeypatch.setattr(linkage_bus.stale_engine, "_degraded", True, raising=False)
    # on_change 不应被调用（degraded 短路）
    on_change_mock = AsyncMock()
    monkeypatch.setattr(linkage_bus.stale_engine, "on_change", on_change_mock, raising=False)

    app = _make_app()
    async with _client(app) as client:
        resp = await client.get(
            "/api/linkage-bus/impact-by-addr",
            params={"addr_id": "D2/D2-2/E100", "project_id": _PROJECT_ID},
        )

    assert resp.status_code == 503
    on_change_mock.assert_not_awaited()


# ─── Case 3: valid addr_id + non-degraded → 200 with correct schema ─────────


@pytest.mark.asyncio
async def test_valid_addr_id_returns_200_with_schema(monkeypatch):
    """正常 addr_id + 非降级 → 200，响应含正确 schema（Req 5.4, 5.5）。"""
    monkeypatch.setattr(linkage_bus.stale_engine, "_degraded", False, raising=False)

    async def _fake_on_change(*, source_uri, project_id, year):
        # 直通校验：addr_id 原样作为 source_uri 传入
        assert source_uri == "D2/D2-2/E100"
        assert project_id == _PROJECT_ID
        return {
            "affected": ["D3/D3-1/A1", "D4/D4-1/B2"],
            "total": 2,
        }

    monkeypatch.setattr(linkage_bus.stale_engine, "on_change", _fake_on_change, raising=False)

    app = _make_app()
    async with _client(app) as client:
        resp = await client.get(
            "/api/linkage-bus/impact-by-addr",
            params={"addr_id": "D2/D2-2/E100", "project_id": _PROJECT_ID, "max_depth": 3},
        )

    assert resp.status_code == 200
    data = resp.json()

    # 顶层 schema
    assert data["addr_id"] == "D2/D2-2/E100"
    assert data["total_affected"] == 2
    assert isinstance(data["affected"], list)
    assert len(data["affected"]) == 2

    # 每项 schema：addr_id / depth / via_ref / match_type
    for item in data["affected"]:
        assert set(item.keys()) == {"addr_id", "depth", "via_ref", "match_type"}
        assert isinstance(item["addr_id"], str)
        assert isinstance(item["depth"], int)
        assert item["match_type"] == "graph_edge"

    # 首项内容与 depth 近似
    assert data["affected"][0]["addr_id"] == "D3/D3-1/A1"
    assert data["affected"][0]["depth"] == 1


@pytest.mark.asyncio
async def test_valid_addr_id_empty_affected_returns_200(monkeypatch):
    """正常 addr_id 但无下游影响 → 200，affected 空列表、total_affected=0。"""
    monkeypatch.setattr(linkage_bus.stale_engine, "_degraded", False, raising=False)

    async def _fake_on_change(*, source_uri, project_id, year):
        return {"affected": [], "total": 0}

    monkeypatch.setattr(linkage_bus.stale_engine, "on_change", _fake_on_change, raising=False)

    app = _make_app()
    async with _client(app) as client:
        resp = await client.get(
            "/api/linkage-bus/impact-by-addr",
            params={"addr_id": "D2/D2-2/E100", "project_id": _PROJECT_ID},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["addr_id"] == "D2/D2-2/E100"
    assert data["total_affected"] == 0
    assert data["affected"] == []
