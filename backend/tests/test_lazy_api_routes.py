"""推迟路由定义判据（spec backend-startup-and-request-overhead R1 / 任务 1）。

- 合成应用：推迟构造的轻属性与立即构造相同、重属性推迟；请求结果（含 422 / 405 / 依赖覆盖）与 OpenAPI 相同；
  子路由那一份不物化；定义错误在物化时抛出；物化里的 AttributeError 不被 hasattr 吞掉；闸门。
- 真实应用（子进程）：立即构造与推迟构造逐条路由签名相同、OpenAPI 逐字节相同、物化 0 失败。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import fastapi
import pytest
from fastapi import APIRouter, Body, Depends, FastAPI, Query
from fastapi.exceptions import FastAPIError
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core import lazy_api_routes as lar

BACKEND = Path(__file__).resolve().parents[1]
CHEAP = ("path", "name", "methods", "unique_id", "status_code", "tags", "response_model", "include_in_schema",
         "path_format", "summary", "description", "operation_id", "response_description", "deprecated")


@pytest.fixture(autouse=True)
def _wrappers():
    lar.install_wrappers()  # 只在推迟标记打开时生效，对其他用例无影响


class Item(BaseModel):
    name: str
    price: float = 0


class Out(BaseModel):
    name: str


def _user(x_user: str | None = None) -> str:
    return x_user or "anon"


def _noop() -> None:
    return None


def _build(route_class):
    app = FastAPI()
    r = APIRouter(prefix="/items", route_class=route_class, tags=["t"], dependencies=[Depends(_noop)])

    @r.get("/{item_id}", response_model=Out)
    def get_item(item_id: int, q: str = Query("d", min_length=1), user: str = Depends(_user)):
        return {"name": f"{item_id}-{q}-{user}", "secret": "hidden"}

    @r.post("", status_code=201)
    def create(item: Item, extra: int = Body(0)):
        return {"got": item.name, "extra": extra}

    @r.put("/{item_id}")
    async def update(item_id: int, item: Item) -> dict:
        return {"id": item_id, "name": item.name}

    app.include_router(r, prefix="/api", tags=["outer"])
    return app, r


def _api_routes(app):
    return [x for x in app.router.routes if isinstance(x, APIRoute)]


def test_cheap_attrs_equal_heavy_deferred_and_sub_routes_never_materialize():
    eager, eager_sub = _build(APIRoute)
    lazy, lazy_sub = _build(lar.LazyAPIRoute)
    for e, z in zip(_api_routes(eager), _api_routes(lazy)):
        assert isinstance(z, lar.LazyAPIRoute) and z.gt_pending
        assert not (lar.HEAVY_ATTRS & set(vars(z))), "重属性应推迟"
        assert set(vars(z)) - {"_gt_lazy_args"} == set(vars(e)) - lar.HEAVY_ATTRS
        for k in CHEAP:
            assert repr(getattr(z, k)) == repr(getattr(e, k)), k
        assert z.path_regex.pattern == e.path_regex.pattern
    client = TestClient(lazy)
    assert client.get("/api/items/5").status_code == 200
    assert all(r.gt_pending for r in lazy_sub.routes), "include_router 只读轻属性，子路由那一份不应物化"
    first = _api_routes(lazy)[0]
    assert not first.gt_pending and set(vars(first)) == set(vars(_api_routes(eager)[0]))


@pytest.mark.parametrize(
    "method,url,body",
    [
        ("get", "/api/items/5?q=x", None),
        ("get", "/api/items/abc", None),
        ("get", "/api/items/5?q=", None),
        ("post", "/api/items", {"item": {"name": "a", "price": 1}, "extra": 3}),
        ("post", "/api/items", {"item": {"price": "bad"}}),
        ("put", "/api/items/7", {"name": "b"}),
        ("delete", "/api/items/7", None),
    ],
)
def test_requests_equivalent(method, url, body):
    results = []
    for cls in (APIRoute, lar.LazyAPIRoute):
        app, _ = _build(cls)
        resp = getattr(TestClient(app), method)(url, **({"json": body} if body is not None else {}))
        results.append((resp.status_code, resp.json()))
    assert results[0] == results[1]


def test_dependency_overrides_and_openapi_equivalent():
    apps = [_build(cls)[0] for cls in (APIRoute, lar.LazyAPIRoute)]
    names = []
    for app in apps:
        app.dependency_overrides[_user] = lambda: "ovr"
        names.append(TestClient(app).get("/api/items/1").json()["name"])
    assert names == ["1-d-ovr", "1-d-ovr"]
    docs = [json.dumps(app.openapi(), sort_keys=True) for app in (_build(APIRoute)[0], _build(lar.LazyAPIRoute)[0])]
    assert docs[0] == docs[1]


class _NotAField:
    pass


def test_definition_error_surfaces_on_materialize():
    def bad(w: _NotAField = Query(...)):  # 不是合法的 Pydantic 字段类型
        return {}

    with pytest.raises(FastAPIError):
        APIRouter(route_class=APIRoute).get("/bad")(bad)
    router = APIRouter(route_class=lar.LazyAPIRoute)
    router.get("/bad")(bad)  # 推迟：构造不报错
    route = router.routes[0]
    assert route.gt_pending
    failures = lar.materialize_all(router.routes)
    assert len(failures) == 1 and failures[0][0] == "/bad" and "FastAPIError" in failures[0][1]
    with pytest.raises(FastAPIError):
        route.dependant  # noqa: B018
    assert route.gt_pending, "物化失败后保持未物化，下次访问再抛"


def test_attribute_error_in_materialize_is_not_swallowed(monkeypatch):
    router = APIRouter(route_class=lar.LazyAPIRoute)
    router.get("/x")(lambda: {"ok": 1})
    route = router.routes[0]
    original = APIRoute.__init__

    def raising(self, *a, **k):
        raise AttributeError("boom")

    monkeypatch.setattr(APIRoute, "__init__", raising)
    with pytest.raises(RuntimeError, match="物化失败"):
        route.dependant  # noqa: B018
    with pytest.raises(RuntimeError):
        hasattr(route, "app")  # 不能被 hasattr 吞成 False
    monkeypatch.setattr(APIRoute, "__init__", original)
    assert route.dependant is not None and not route.gt_pending


def test_deferred_construction_builds_no_type_adapters(monkeypatch):
    """推迟构造不建任何 TypeAdapter（参数 / 响应模型都推迟）；立即构造与物化都会建。"""
    from pydantic import TypeAdapter

    built = []
    original = TypeAdapter.__init__

    def counting(self, *a, **k):
        built.append(1)
        return original(self, *a, **k)

    monkeypatch.setattr(TypeAdapter, "__init__", counting)

    def endpoint(a: int, q: str = Query("x"), item: Item | None = None) -> Out:
        return Out(name=str(a))

    lazy_router = APIRouter(route_class=lar.LazyAPIRoute)
    lazy_router.post("/y/{a}")(endpoint)
    assert built == [] and lazy_router.routes[0].gt_pending
    lazy_router.routes[0].gt_materialize()
    after_materialize = len(built)
    built.clear()
    APIRouter(route_class=APIRoute).post("/y/{a}")(endpoint)
    assert after_materialize == len(built) > 0, (after_materialize, len(built))


def test_install_gates(monkeypatch):
    kw = APIRouter.__init__.__kwdefaults__
    saved_cls, saved_flag = kw["route_class"], lar._installed
    try:
        monkeypatch.setattr(lar, "_installed", False)
        kw["route_class"] = APIRoute
        monkeypatch.setenv("GT_LAZY_ROUTES", "0")
        assert lar.install_lazy_api_routes() is False and kw["route_class"] is APIRoute
        monkeypatch.delenv("GT_LAZY_ROUTES")
        monkeypatch.setattr(lar.fastapi, "__version__", "0.0.0")
        assert lar.install_lazy_api_routes() is False and kw["route_class"] is APIRoute
    finally:
        kw["route_class"], lar._installed = saved_cls, saved_flag


def test_current_fastapi_version_is_validated():
    # 升级 FastAPI 先在这里红：重新核对 APIRoute.__init__ / include_router 后把新版本加进 VALIDATED_FASTAPI_VERSIONS
    assert fastapi.__version__ in lar.VALIDATED_FASTAPI_VERSIONS


def _dump(tmp_path: Path, lazy: bool) -> dict:
    out = tmp_path / ("lazy.json" if lazy else "eager.json")
    # 同一个 hash 种子：多方法路由的 unique_id 取 list(methods)[0]，集合遍历顺序随种子变（与推迟无关）
    env = dict(os.environ, GT_LAZY_ROUTES="1" if lazy else "0", PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0")
    proc = subprocess.run([sys.executable, str(BACKEND / "tests" / "_lazy_routes_dump.py"), str(out)], cwd=BACKEND,
                          env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(out.read_text(encoding="utf-8"))


def test_real_app_lazy_equivalent_to_eager(tmp_path):
    eager = _dump(tmp_path, lazy=False)
    lazy = _dump(tmp_path, lazy=True)
    assert eager["enabled"] is False and eager["pending_before"] == 0 and eager["lazy_classes"] == 0
    assert lazy["enabled"] is True and lazy["failures"] == []
    assert lazy["pending_before"] >= 2500, lazy["pending_before"]
    assert lazy["lazy_classes"] == lazy["pending_before"]
    assert len(eager["routes"]) == len(lazy["routes"])
    diffs = [i for i, (a, b) in enumerate(zip(eager["routes"], lazy["routes"])) if a != b]
    assert not diffs, f"{len(diffs)} 条路由签名不同，首条 #{diffs[0]}: {eager['routes'][diffs[0]]} / {lazy['routes'][diffs[0]]}"
    assert eager["openapi_sha256"] == lazy["openapi_sha256"]


def _router_with_bad_route():
    def bad(w: _NotAField = Query(...)):
        return {}

    router = APIRouter(route_class=lar.LazyAPIRoute)
    router.get("/good/{a}")(lambda a: {"a": a})
    router.get("/bad")(bad)
    return router


@pytest.mark.asyncio
async def test_verify_in_background_materializes_and_reports():
    router = _router_with_bad_route()
    calls = []
    failures = await lar.verify_in_background(router.routes, delay_s=0, interval_s=0,
                                             on_progress=lambda *a: calls.append(a))
    assert [p for p, _ in failures] == ["/bad"]
    assert not router.routes[0].gt_pending and router.routes[1].gt_pending
    assert calls[-1][0] == calls[-1][1] == 2 and calls[-1][3] is True


@pytest.mark.asyncio
async def test_startup_task_verify_lazy_routes_updates_report(monkeypatch):
    from app.core import startup_registry as sr

    spec = next(t for t in sr.STARTUP_TASKS if t.name == "verify_lazy_routes")
    assert (spec.phase, spec.criticality) == ("caches", "critical")
    monkeypatch.setattr(lar, "_installed", True)
    monkeypatch.setenv("GT_LAZY_ROUTES_VERIFY_DELAY", "0")
    app = FastAPI()
    app.include_router(_router_with_bad_route())
    ctx = sr.StartupContext(extras={"app": app})
    saved = sr.get_startup_report()
    try:
        await sr.run_startup_tasks([spec], context=ctx)
        assert len(ctx.worker_tasks) == 1, "后台核验要登记成 worker 任务，关闭时一起取消"
        await ctx.worker_tasks[0]
        item = next(r for r in sr.get_startup_report() if r.name == "verify_lazy_routes")
        assert item.status == "failed" and "失败 1" in item.detail and "/bad" in item.detail
    finally:
        if saved is None:
            sr.reset_startup_report()
        else:
            sr._set_runtime_report(saved)


@pytest.mark.asyncio
async def test_background_verifier_uses_shared_heavy_phase_lock():
    """后台路由物化不得与预热 / event replay / OpenAPI / GC 同时占 GIL。"""
    import asyncio

    from app.core.gc_tuning import heavy_phase

    router = APIRouter(route_class=lar.LazyAPIRoute)
    router.get("/locked/{x}")(lambda x: {"x": x})
    route = router.routes[0]
    assert route.gt_pending
    async with heavy_phase("test-blocker"):
        task = asyncio.create_task(
            lar.verify_in_background(router.routes, delay_s=0, interval_s=0)
        )
        await asyncio.sleep(0.02)
        assert route.gt_pending, "其他重阶段持锁时不得开始物化"
    assert await asyncio.wait_for(task, 2) == []
    assert not route.gt_pending
