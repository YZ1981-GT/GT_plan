"""GET /api/linkage-bus/impact-by-addr 边界条件单测。

原 Task 3.9（acnr-consumer-wiring）。spec acnr-foundation-defect-closure D8 把该端点由「会写库的 GET」
改为只读预览（``stale_engine.preview_impact``，不写库 / 不推 SSE / 不记审计）并加 ``require_project_access("readonly")``
鉴权，故本文件改用权限世界 fixtures（真实成员行 + 生产门禁）发请求，并把被观测的引擎入口换成 ``preview_impact``。

覆盖：
1. 空 / 纯空白 addr_id → 400（鉴权通过后，函数体首句判定）
2. 引擎降级 → 503
3. 正常 addr_id + 非降级 → 200，响应 schema 正确；preview_impact 被调、on_change 不被调（只读）
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.routers import linkage_bus
from app.services import stale_propagation_engine as stale_module
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

_PROJECT_ID = str(TARGET_PROJECT_ID)


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


def _stub_preview(world, returns):
    if "preview_impact" in vars(stale_module.stale_engine):
        world.monkeypatch.delattr(stale_module.stale_engine, "preview_impact")
    return world.stub(stale_module.StalePropagationEngine, "preview_impact", returns=returns, awaitable=False)


async def _get(world, user, **params):
    async with world.client(linkage_bus.router, user=user) as client:
        return await client.get("/api/linkage-bus/impact-by-addr", params=params)


# ─── Case 1: 空 / 纯空白 addr_id → 400 ──────────────────────────────────────


@pytest.mark.parametrize("addr_id", ["", "   "])
async def test_blank_addr_id_returns_400(world, addr_id: str):
    """空 / 纯空白 addr_id → 400（鉴权通过后，函数体首句 strip 判定）。"""
    user = (await world.admin_non_member()).user  # admin 过项目鉴权
    world.monkeypatch.setattr(linkage_bus.stale_engine, "_degraded", False, raising=False)
    resp = await _get(world, user, addr_id=addr_id, project_id=_PROJECT_ID)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "addr_id is required"


# ─── Case 2: 引擎降级 → 503 ─────────────────────────────────────────────────


async def test_engine_degraded_returns_503(world):
    """引擎降级 → 503；preview_impact 不被调用（degraded 短路在它之前）。"""
    user = (await world.admin_non_member()).user
    world.monkeypatch.setattr(linkage_bus.stale_engine, "_degraded", True, raising=False)
    preview = _stub_preview(world, {"affected": [], "total": 0, "degraded": True})
    resp = await _get(world, user, addr_id="D2/D2-2/E100", project_id=_PROJECT_ID)
    assert resp.status_code == 503, resp.text
    assert preview.count == 0


# ─── Case 3: 正常 addr_id + 非降级 → 200，只读 preview ────────────────────────


async def test_valid_addr_id_returns_200_with_schema(world):
    """正常 addr_id + 非降级 → 200，响应 schema 正确；走只读 preview_impact（不是 on_change）。"""
    user = (await world.admin_non_member()).user
    world.monkeypatch.setattr(linkage_bus.stale_engine, "_degraded", False, raising=False)
    preview = _stub_preview(world, {"affected": ["D3/D3-1/A1", "D4/D4-1/B2"], "total": 2, "degraded": False})
    resp = await _get(world, user, addr_id="D2/D2-2/E100", project_id=_PROJECT_ID, max_depth=3)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["addr_id"] == "D2/D2-2/E100"
    assert data["total_affected"] == 2
    assert isinstance(data["affected"], list) and len(data["affected"]) == 2
    for item in data["affected"]:
        assert set(item.keys()) == {"addr_id", "depth", "via_ref", "match_type"}
        assert isinstance(item["addr_id"], str) and isinstance(item["depth"], int)
        assert item["match_type"] == "graph_edge"
    assert data["affected"][0]["addr_id"] == "D3/D3-1/A1" and data["affected"][0]["depth"] == 1
    # 只读：preview 被调 1 次，且传入的是请求里的 addr_id 与 max_depth
    assert preview.count == 1
    (args, kwargs) = preview.calls[0]
    called = {**dict(zip(("source_uri", "max_depth"), args)), **kwargs}
    assert called["source_uri"] == "D2/D2-2/E100"
    assert called["max_depth"] == 3


async def test_valid_addr_id_empty_affected_returns_200(world):
    """正常 addr_id 但无下游影响 → 200，affected 空列表、total_affected=0。"""
    user = (await world.admin_non_member()).user
    world.monkeypatch.setattr(linkage_bus.stale_engine, "_degraded", False, raising=False)
    _stub_preview(world, {"affected": [], "total": 0, "degraded": False})
    resp = await _get(world, user, addr_id="D2/D2-2/E100", project_id=_PROJECT_ID)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["addr_id"] == "D2/D2-2/E100"
    assert data["total_affected"] == 0
    assert data["affected"] == []
