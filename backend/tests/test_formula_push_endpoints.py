"""公式推送端点：TestClient 真发请求（任务 12 · 需求 1.1 / 1.4 / 2.3）。

只 override ``get_current_user``（随请求切换身份）与 ``get_db``（SQLite 内存库）——
``require_project_access`` 是依赖工厂，每次调用返回新函数，override 工厂本身会静默失效；
这里让真实的项目权限判定（project_users 查询）照常执行，无权限用户走真 403。
取数层同引擎测试：``E1Binding.load_sources`` 换成固定源，其余全走真实代码。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import ProjectUser, User
from app.routers.formula_push import router
from tests._formula_push_env import CASH_OPENING, YEAR, base_entries, make_env


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch, extra_tables=(User.__table__, ProjectUser.__table__)) as e:
        yield e


class _Actor:
    def __init__(self, role: UserRole):
        self.id = uuid.uuid4()
        self.role = role
        self.username = f"u-{self.id.hex[:4]}"
        self.email = f"{self.username}@example.com"
        self.is_active = True


@pytest_asyncio.fixture
async def api(env):
    editor, reader, outsider = _Actor(UserRole.auditor), _Actor(UserRole.auditor), _Actor(UserRole.auditor)
    async with env.factory() as db:
        for actor, level in ((editor, PermissionLevel.edit), (reader, PermissionLevel.readonly)):
            db.add(ProjectUser(project_id=env.pid, user_id=actor.id, role=ProjectUserRole.auditor,
                               permission_level=level))
        await db.commit()
    app = FastAPI()
    app.include_router(router)
    who = {"actor": editor}

    async def _db():
        async with env.factory() as s:
            yield s

    async def _user():
        return who["actor"]

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield {
            "client": client, "env": env, "base": f"/api/projects/{env.pid}/formula-push",
            "as": lambda name: who.update(actor={"editor": editor, "reader": reader, "outsider": outsider}[name]),
        }



@pytest.mark.asyncio
async def test_rules_listing_is_readonly_and_chinese(api):
    c, base = api["client"], api["base"]
    api["as"]("reader")
    r = await c.get(f"{base}/rules", params={"wp_code": "E1"})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["supported_wp_codes"] == ["E1"]
    rules = payload["rules"]
    assert len(rules) == 30 and {x["wp_code"] for x in rules} == {"E1"}
    tb = next(x for x in rules if x["rule_id"] == "E1.tb_amount.ending")
    assert tb["formula"].startswith("TB('1001','期末余额')") and "试算" in tb["description"]
    assert all(x["description"] and x["formula"] for x in rules), "面板每条规则都要有中文说明与算式"


@pytest.mark.asyncio
async def test_bindings_listing_is_readonly_and_returns_registry_shape(api):
    c, base = api["client"], api["base"]
    api["as"]("reader")
    r = await c.get(f"{base}/bindings")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "supported_wp_codes": ["E1"],
        "bindings": [{"wp_code": "E1", "account_prefixes": ["1001", "1002", "1012"]}],
    }


@pytest.mark.asyncio
async def test_bindings_listing_tracks_temporary_registry_registration_and_revoke(api):
    from app.services.formula_push.bindings import register_binding

    class FakeBinding:
        wp_code = "Z9"
        account_prefixes = ("9901",)
        derivations = frozenset()

    c, base = api["client"], api["base"]
    api["as"]("reader")
    revoke = register_binding("Z9", FakeBinding)
    try:
        r = await c.get(f"{base}/bindings")
        assert r.status_code == 200
        assert r.json()["supported_wp_codes"] == ["E1", "Z9"]
        assert r.json()["bindings"][-1] == {"wp_code": "Z9", "account_prefixes": ["9901"]}
    finally:
        revoke()

    r = await c.get(f"{base}/bindings")
    assert r.status_code == 200
    assert r.json()["supported_wp_codes"] == ["E1"]


@pytest.mark.asyncio
async def test_run_and_state_endpoints(api):
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    r = await c.post(f"{base}/run", json={"year": YEAR})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written_count"] == 20 and body["kept_count"] == 2 and body["run_id"]
    assert (await env.entries())["E1-adj-tb-amount-ending"] == "606.73"

    api["as"]("reader")
    latest = (await c.get(f"{base}/latest", params={"year": YEAR})).json()
    assert latest["run"]["run_id"] == body["run_id"] and latest["run"]["trigger"] == "manual"
    assert latest["state_counts"]["pending_confirm"] == 2
    pending = (await c.get(f"{base}/states", params={"year": YEAR, "state": "pending_confirm"})).json()["states"]
    row = next(s for s in pending if s["addr_id"] == CASH_OPENING)
    assert (row["current_value"], row["formula_value"], row["differs"]) == (200.0, 286.73, True)
    assert (await c.get(f"{base}/states", params={"year": YEAR, "state": "bogus"})).status_code == 400


@pytest.mark.asyncio
async def test_dry_run_endpoint_leaves_no_trace(api):
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    before = await env.entries()
    r = await c.post(f"{base}/run", json={"year": YEAR, "dry_run": True})
    assert r.status_code == 200 and r.json()["dry_run"] is True and r.json()["run_id"] is None
    assert r.json()["written_count"] == 20
    assert await env.entries() == before and await env.runs() == []


@pytest.mark.asyncio
async def test_adopt_and_lock_endpoints(api):
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    await c.post(f"{base}/run", json={"year": YEAR})
    r = await c.post(f"{base}/states/adopt", json={"year": YEAR, "addr_ids": [CASH_OPENING]})
    assert r.status_code == 200, r.text
    assert [i["action"] for i in r.json()["items"]] == ["write"]
    r = await c.post(f"{base}/states/lock", json={"year": YEAR, "addr_ids": [CASH_OPENING], "locked": True})
    assert r.status_code == 200 and r.json()["states"][0]["state"] == "locked"
    # 派生值 / 系统值不能锁定；没有推送记录的目标不能采用 —— 400 且中文原因
    r = await c.post(f"{base}/states/lock", json={"year": YEAR, "addr_ids": ["E1/E1-1/E1-adj-total-1001"],
                                                   "locked": True})
    assert r.status_code == 400 and "不能采用或锁定" in r.json()["detail"]
    r = await c.post(f"{base}/states/adopt", json={"year": YEAR, "addr_ids": ["E1/E1-9/不存在"]})
    assert r.status_code == 400 and "尚无推送记录" in r.json()["detail"]
    assert (await env.states())[CASH_OPENING].state == "locked", "失败的锁定请求不得改动其它目标"


@pytest.mark.asyncio
async def test_run_for_non_audit_year_is_400(api):
    r = await api["client"].post(f"{api['base']}/run", json={"year": YEAR - 1})
    assert r.status_code == 400 and "审计年度" in r.json()["detail"]



WRITE_CALLS = [
    ("post", "/run", {"year": YEAR}),
    ("post", "/states/adopt", {"year": YEAR, "addr_ids": [CASH_OPENING]}),
    ("post", "/states/lock", {"year": YEAR, "addr_ids": [CASH_OPENING], "locked": True}),
]
READ_CALLS = [
    ("get", "/bindings", None),
    ("get", "/rules", None),
    ("get", f"/latest?year={YEAR}", None),
    ("get", f"/states?year={YEAR}", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path, body", WRITE_CALLS)
async def test_write_endpoints_require_project_edit(api, method, path, body):
    """只读成员 / 非项目成员调写端点 ⇒ 真 403，且不产生任何写入。"""
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    before = await env.entries()
    for who in ("reader", "outsider"):
        api["as"](who)
        r = await getattr(c, method)(f"{base}{path}", json=body)
        assert r.status_code == 403, (who, r.status_code, r.text)
    assert await env.entries() == before and await env.runs() == [] and await env.states() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path, body", READ_CALLS)
async def test_read_endpoints_require_project_membership(api, method, path, body):
    c, base = api["client"], api["base"]
    api["as"]("outsider")
    assert (await getattr(c, method)(f"{base}{path}")).status_code == 403
    api["as"]("reader")
    assert (await getattr(c, method)(f"{base}{path}")).status_code == 200


def test_every_route_declares_project_access_dependency():
    """纯 AST：每个端点签名都以 require_project_access(...) 为依赖（docstring / 注释不算）；写端点必须 edit。"""
    import ast
    import inspect

    import app.routers.formula_push as mod

    tree = ast.parse(inspect.getsource(mod))
    routes: dict[str, str] = {}
    for fn in (n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)):
        verbs = [d.func.attr for d in fn.decorator_list
                 if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("get", "post")]
        if not verbs:
            continue
        levels = [
            d.args[0].args[0].value
            for d in fn.args.defaults + fn.args.kw_defaults
            if isinstance(d, ast.Call) and getattr(d.func, "id", None) == "Depends" and d.args
            and isinstance(d.args[0], ast.Call) and getattr(d.args[0].func, "id", None) == "require_project_access"
        ]
        assert levels, f"{fn.name} 未挂 require_project_access"
        routes[fn.name] = levels[0]
        assert levels[0] == ("edit" if verbs[0] == "post" else "readonly"), (fn.name, levels)
    assert set(routes) == {"list_bindings", "list_rules", "run_push", "latest", "states", "adopt", "lock"}


def test_router_is_registered():
    from fastapi import FastAPI

    from app.router_registry.report import register_report_routers

    app = FastAPI()
    register_report_routers(app)
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/projects/{project_id}/formula-push/run" in paths
    assert "/api/projects/{project_id}/formula-push/states/adopt" in paths
