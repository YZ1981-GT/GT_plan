"""GET /api/linkage-bus/impact-by-addr 响应 schema 的属性测试（P11）。

原 Task 3.8（acnr-consumer-wiring）。spec acnr-foundation-defect-closure D8 把该端点改为只读预览
（``stale_engine.preview_impact``）并加 ``require_project_access("readonly")`` 鉴权，故本文件：
- 受控替身改实现 ``preview_impact``（同步）而非 ``on_change``；
- 用 admin 用户 + 空操作 ``get_db`` + 置空 ``set_rls_context`` 绕过项目鉴权的数据层（只测响应整形，不测鉴权）；
- 按仓库约定把 ``max_examples`` 降到 5。

**Property 11：响应 schema 完整性** —— 任意合法 addr_id + 任意 BFS 结果，200 响应恒含所有必需字段且类型正确。
Validates: Requirements 5.4
"""

from __future__ import annotations

import asyncio
import string
import uuid

from hypothesis import given, settings
from hypothesis import strategies as st
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.deps as deps
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import UserRole
from app.routers import linkage_bus
from app.routers.linkage_bus import router


_PROJECT_ID = str(uuid.uuid4())


class _FakeUser:
    id = uuid.uuid4()
    username = "test_user"
    role = UserRole.admin  # admin 过项目鉴权（下面再置空 set_rls_context / get_db 的数据层）


class _FakeStaleEngine:
    """受控替身：非降级 + 可控 preview_impact 返回（只读，不写库）。"""

    is_degraded = False

    def __init__(self, affected: list[str], total: int) -> None:
        self._affected = affected
        self._total = total

    def preview_impact(self, source_uri, max_depth=5):  # noqa: D401
        return {"affected": list(self._affected), "total": self._total, "degraded": False}


class _NoopSession:
    async def execute(self, *_a, **_k):
        return None


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    async def _user():
        return _FakeUser()

    async def _db():
        yield _NoopSession()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    return app


async def _call_endpoint(app: FastAPI, addr_id: str, max_depth: int):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(
            "/api/linkage-bus/impact-by-addr",
            params={"addr_id": addr_id, "project_id": _PROJECT_ID, "max_depth": max_depth},
        )


_seg = st.text(alphabet=string.ascii_uppercase + string.digits + "-", min_size=1, max_size=8).filter(
    lambda s: s.strip() != ""
)
_addr_id = st.builds(lambda a, b, c: f"{a}/{b}/{c}", _seg, _seg, _seg)
_affected_list = st.lists(_addr_id, max_size=10)


@settings(max_examples=5)
@given(
    addr_id=_addr_id,
    affected=_affected_list,
    total=st.integers(min_value=0, max_value=100_000),
    max_depth=st.integers(min_value=1, max_value=10),
)
def test_stale_impact_response_schema_completeness(addr_id, affected, total, max_depth):
    """P11：任意合法 addr_id + 任意 BFS 结果 → 200 响应 schema 完整且类型正确。"""
    app = _make_app()

    # admin 鉴权仍会调 set_rls_context；置空它（只读预览测的是响应整形，不是 RLS）
    async def _noop_rls(_session, _project_id):
        return None

    original_rls = deps.set_rls_context
    original_engine = linkage_bus.stale_engine
    deps.set_rls_context = _noop_rls
    linkage_bus.stale_engine = _FakeStaleEngine(affected, total)
    try:
        resp = asyncio.run(_call_endpoint(app, addr_id, max_depth))
    finally:
        linkage_bus.stale_engine = original_engine
        deps.set_rls_context = original_rls

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert set(["addr_id", "total_affected", "affected"]).issubset(data.keys())
    assert isinstance(data["addr_id"], str) and data["addr_id"] == addr_id
    assert isinstance(data["total_affected"], int) and data["total_affected"] == total
    assert isinstance(data["affected"], list) and len(data["affected"]) == len(affected)

    for i, item in enumerate(data["affected"]):
        assert set(item.keys()) == {"addr_id", "depth", "via_ref", "match_type"}
        assert isinstance(item["addr_id"], str) and item["addr_id"] == affected[i]
        assert isinstance(item["depth"], int)
        assert 1 <= item["depth"] <= max_depth
        assert item["depth"] == min(i + 1, max_depth)
        assert "via_ref" in item and item["via_ref"] is None
        assert isinstance(item["match_type"], str) and item["match_type"] == "graph_edge"
