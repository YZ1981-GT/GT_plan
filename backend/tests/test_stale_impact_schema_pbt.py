"""Property test for GET /api/linkage-bus/impact-by-addr response schema (P11).

Task 3.8 (acnr-consumer-wiring): Property-Based Test for the stale_impact-by-addr
endpoint response-shaping logic implemented in task 3.7.

**Property 11: stale_impact Response Schema Completeness**
使用 Hypothesis 生成随机合法 addr_id 输入 + 随机 BFS 结果，验证 200 响应 schema
始终包含所有必需字段且类型正确：
- 顶层 ``addr_id`` (str)、``total_affected`` (int)、``affected`` (list)
- ``affected`` 每项含 ``addr_id`` (str)、``depth`` (int)、``via_ref``、``match_type`` (str)

Validates: Requirements 5.4

测试方式（approach b）：构造最小 FastAPI app 挂载 linkage_bus router，override
``get_current_user`` 提供 stub 用户，并将模块级 ``stale_engine`` 替换为受控 fake
（``is_degraded=False`` + ``on_change`` 返回受控 ``{"affected": [...], "total": N}``），
从而在无 DB / 完整 app 的情况下 hermetic 地检验响应整形逻辑。引擎不处于降级路径。
"""

from __future__ import annotations

import asyncio
import string
import uuid

from hypothesis import given, settings
from hypothesis import strategies as st
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.models.core import UserRole
from app.routers import linkage_bus
from app.routers.linkage_bus import router


# ─── Stub 用户 / app 构造 ─────────────────────────────────────────────────────

_PROJECT_ID = str(uuid.uuid4())


class _FakeUser:
    id = uuid.uuid4()
    username = "test_user"
    role = UserRole.admin


class _FakeStaleEngine:
    """受控的 StalePropagationEngine 替身：非降级 + 可控 on_change 返回。"""

    is_degraded = False

    def __init__(self, affected: list[str], total: int) -> None:
        self._affected = affected
        self._total = total

    async def on_change(self, *, source_uri, project_id, year):  # noqa: D401
        # addr_id 直通作为 source_uri（Req 5.2），返回受控 BFS 结果
        return {"affected": list(self._affected), "total": self._total}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    async def _user():
        return _FakeUser()

    app.dependency_overrides[get_current_user] = _user
    return app


async def _call_endpoint(app: FastAPI, addr_id: str, max_depth: int):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(
            "/api/linkage-bus/impact-by-addr",
            params={
                "addr_id": addr_id,
                "project_id": _PROJECT_ID,
                "max_depth": max_depth,
            },
        )


# ─── 生成器（智能约束到输入空间） ─────────────────────────────────────────────

# addr_id 段：大写字母 / 数字 / 连字符，非空——构造 `{wp_code}/{sheet_code}/{cell}`
_seg = st.text(
    alphabet=string.ascii_uppercase + string.digits + "-",
    min_size=1,
    max_size=8,
).filter(lambda s: s.strip() != "")

_addr_id = st.builds(lambda a, b, c: f"{a}/{b}/{c}", _seg, _seg, _seg)

# BFS 结果里的受影响 URI 列表（可能为空），及独立生成的 total（验证 int 类型透传）
_affected_list = st.lists(_addr_id, max_size=10)


# ─── Property 11 ─────────────────────────────────────────────────────────────


@settings(max_examples=150)
@given(
    addr_id=_addr_id,
    affected=_affected_list,
    total=st.integers(min_value=0, max_value=100_000),
    max_depth=st.integers(min_value=1, max_value=10),
)
def test_stale_impact_response_schema_completeness(addr_id, affected, total, max_depth):
    """P11：任意合法 addr_id + 任意 BFS 结果 → 200 响应 schema 完整且类型正确。

    Validates: Requirements 5.4
    """
    app = _make_app()

    # 以受控 fake 替换模块级 stale_engine（非降级路径），逐 example 恢复
    original_engine = linkage_bus.stale_engine
    linkage_bus.stale_engine = _FakeStaleEngine(affected, total)
    try:
        resp = asyncio.run(_call_endpoint(app, addr_id, max_depth))
    finally:
        linkage_bus.stale_engine = original_engine

    # 合法 addr_id 非降级 → 必须 200
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # 顶层字段完整性 + 类型
    assert set(["addr_id", "total_affected", "affected"]).issubset(data.keys())
    assert isinstance(data["addr_id"], str)
    assert data["addr_id"] == addr_id
    assert isinstance(data["total_affected"], int)
    assert data["total_affected"] == total
    assert isinstance(data["affected"], list)

    # affected 条目数与引擎返回一致
    assert len(data["affected"]) == len(affected)

    # 每项 schema：addr_id(str) / depth(int) / via_ref(present) / match_type(str)
    for i, item in enumerate(data["affected"]):
        assert set(item.keys()) == {"addr_id", "depth", "via_ref", "match_type"}
        assert isinstance(item["addr_id"], str)
        assert item["addr_id"] == affected[i]
        assert isinstance(item["depth"], int)
        # depth 近似 = min(i+1, max_depth)，恒在 [1, max_depth] 区间
        assert 1 <= item["depth"] <= max_depth
        assert item["depth"] == min(i + 1, max_depth)
        # via_ref 键必须存在（此实现下为 None）
        assert "via_ref" in item
        assert item["via_ref"] is None
        assert isinstance(item["match_type"], str)
        assert item["match_type"] == "graph_edge"
