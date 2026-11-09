"""批 6.4：合并 readiness 角色视图 / readiness 端点的项目级鉴权（端点级，经真实门禁）。

用权限世界（authz_world）按生产注册挂 `consol_readiness` 路由，经 httpx 真发请求，每个请求都核对生产门禁
`require_project_access` 的代码确实执行过（GateClient）。只读端点：任何项目成员放行；未登录 401。

装载层（load_consol_readiness / load_consol_role_views）在这里打桩——本文件只验鉴权门，不验装载层逻辑
（装载层端到端在 test_readiness_role_views_wiring.py 里用真实壳 + 证据验证）。
"""
from __future__ import annotations

import pytest
import pytest_asyncio

import tests.conftest  # noqa: F401
from app.routers import consol_readiness as readiness_router
from app.services import consol_readiness_service as readiness_service
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

pytestmark = pytest.mark.asyncio

YEAR = 2025
GATE = "app.deps.require_project_access.<locals>.dependency"

_FAKE_READINESS = {"status": "ready", "domains": [], "blockers": [], "evidence": {}, "review": {}}
_FAKE_ROLE_VIEWS = {
    "views": [
        {"role": "preparer", "label": "编制", "level": "edit", "role_aliases": [], "status": "ready", "todo_count": 0, "todos": []},
        {"role": "approval", "label": "审批", "level": "edit", "role_aliases": [], "status": "ready", "todo_count": 0, "todos": []},
        {"role": "significant_judgment", "label": "重大判断", "level": "edit", "role_aliases": [], "status": "ready", "todo_count": 0, "todos": []},
        {"role": "qc", "label": "质控", "level": "review", "role_aliases": [], "status": "ready", "todo_count": 0, "todos": []},
    ],
    "readiness_status": "ready",
    "domains": [],
    "evidence": {},
    "review": {},
}


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        # 装载层打桩：只测鉴权门，不连合并业务表（装载层逻辑另有 wiring 测试覆盖）
        w.stub(readiness_service, "load_consol_readiness", returns=_FAKE_READINESS)
        w.stub(readiness_service, "load_consol_role_views", returns=_FAKE_ROLE_VIEWS)
        yield w


def _readiness_url() -> str:
    return f"/api/consolidation/readiness/{TARGET_PROJECT_ID}/{YEAR}"


def _role_views_url() -> str:
    return f"/api/consolidation/readiness/{TARGET_PROJECT_ID}/{YEAR}/role-views"


# ─── readiness：readonly ─────────────────────────────────────────────────────


async def test_readiness_allows_readonly_member(world):
    identity = await world.readonly_member()
    async with world.client(readiness_router.router, user=identity.user) as client:
        resp = await client.get(_readiness_url())
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ready"
    client.assert_passed(GATE)


async def test_readiness_unauthenticated_401(world):
    async with world.client(readiness_router.router, user=None) as client:
        resp = await client.get(_readiness_url())
    assert resp.status_code == 401, resp.text


# ─── role-views：readonly（任何成员可看四桶） ────────────────────────────────


async def test_role_views_allows_readonly_member(world):
    identity = await world.readonly_member()
    async with world.client(readiness_router.router, user=identity.user) as client:
        resp = await client.get(_role_views_url())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [v["role"] for v in body["views"]] == [
        "preparer", "approval", "significant_judgment", "qc",
    ]
    client.assert_passed(GATE)


async def test_role_views_allows_edit_member(world):
    """edit 级成员（编制/审批角色）也能看四桶（readonly 门对 edit 放行）。"""
    identity = await world.edit_member()
    async with world.client(readiness_router.router, user=identity.user) as client:
        resp = await client.get(_role_views_url())
    assert resp.status_code == 200, resp.text
    client.assert_passed(GATE)


async def test_role_views_allows_review_member(world):
    """review 级成员（质控角色）也能看四桶。"""
    identity = await world.review_member()
    async with world.client(readiness_router.router, user=identity.user) as client:
        resp = await client.get(_role_views_url())
    assert resp.status_code == 200, resp.text
    client.assert_passed(GATE)


async def test_role_views_denies_non_member(world):
    """非本项目成员（在另一项目有 edit 行）对本项目 403。"""
    identity = await world.non_member()
    async with world.client(readiness_router.router, user=identity.user) as client:
        resp = await client.get(_role_views_url())
    assert resp.status_code == 403, resp.text


async def test_role_views_unauthenticated_401(world):
    async with world.client(readiness_router.router, user=None) as client:
        resp = await client.get(_role_views_url())
    assert resp.status_code == 401, resp.text
