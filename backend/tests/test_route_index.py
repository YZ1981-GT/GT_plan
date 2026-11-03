"""路由按路径段建索引（spec backend-startup-and-request-overhead R3.2，任务 7）。

判据：与 Starlette 自己的逐条扫描（``Router.app``）分派结果逐个相同 —— 真实应用全部路由 × 模板路径 / 尾斜杠
变体 × 多种方法，外加随机路径；合成路由表覆盖 Mount / Host / WebSocket / path 转换器 / 部分字面段 / 自定义
matches / 根路径；路由表增删改后自动重建，整体换成普通列表时退回逐条扫描；版本闸门与开关。
"""
from __future__ import annotations

import asyncio
import random
import uuid

import pytest
from starlette.convertors import FloatConvertor, IntegerConvertor, PathConvertor, UUIDConvertor
from starlette.responses import PlainTextResponse
from starlette.routing import Host, Match, Mount, Route, Router, WebSocketRoute

from app.core import route_index as ri

METHODS = ("GET", "POST", "PUT", "DELETE", "OPTIONS")
UUID_SAMPLE = "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49"


def _fill(route) -> str | None:
    fmt = getattr(route, "path_format", None)
    if not isinstance(fmt, str):
        return None
    out = fmt
    for name, conv in getattr(route, "param_convertors", {}).items():
        value = {IntegerConvertor: "7", FloatConvertor: "1.5", UUIDConvertor: UUID_SAMPLE,
                 PathConvertor: "a/b"}.get(type(conv), "x1")
        out = out.replace("{" + name + "}", value)
    return out


class _Recorder:
    """把路由的 handle / router.default / send 换成记录器：只看分派到了哪里，不真跑接口。"""

    def __init__(self, routes):
        self.hits: list = []
        self.routes = routes
        self.saved = []
        for i, route in enumerate(routes):
            self.saved.append(route)

            async def handle(scope, receive, send, _i=i):
                self.hits.append(("route", _i, dict(scope.get("path_params", {}))))

            route.handle = handle

    async def default(self, scope, receive, send):
        self.hits.append(("default", None, None))

    async def send(self, message):
        if message["type"] == "http.response.start":
            headers = dict(message.get("headers") or [])
            self.hits.append(("redirect", message["status"], headers.get(b"location")))

    def restore(self):
        for route in self.saved:
            route.__dict__.pop("handle", None)


def _routers(routes, recorder):
    linear = Router(routes=list(routes), default=recorder.default)
    indexed = Router(routes=list(routes), default=recorder.default)
    assert ri.install_route_index(indexed)
    return linear, indexed


async def _outcome(router, recorder, scope):
    recorder.hits.clear()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await router(dict(scope), receive, recorder.send)
    return list(recorder.hits)


def _scope(path, method="GET", kind="http"):
    return {"type": kind, "path": path, "raw_path": path.encode(), "root_path": "", "method": method,
            "query_string": b"", "headers": [(b"host", b"testserver")], "scheme": "http",
            "server": ("testserver", 80)}


def _compare(routes, scopes):
    recorder = _Recorder(routes)
    try:
        linear, indexed = _routers(routes, recorder)

        async def run():
            diffs = []
            for scope in scopes:
                a = await _outcome(linear, recorder, scope)
                b = await _outcome(indexed, recorder, scope)
                if a != b:
                    diffs.append((scope["type"], scope["method"], scope["path"], a, b))
            return diffs

        return asyncio.run(run())
    finally:
        recorder.restore()


def test_real_app_dispatch_identical_to_linear_scan():
    from app.main import app

    routes = list(app.router.routes)
    rnd = random.Random(20261028)
    words = sorted({seg for r in routes for seg in (getattr(r, "path_format", "") or "").split("/") if seg and "{" not in seg})
    scopes = []
    for route in routes:
        path = _fill(route)
        if path is None:
            continue
        variants = {path, path.rstrip("/") or "/", path + "/"}
        for p in variants:
            scopes.extend(_scope(p, m) for m in ("GET", "POST", "DELETE"))  # 逐条扫描一次约 0.7 ms：方法取三种
    for _ in range(1500):
        depth = rnd.randint(1, 7)
        segs = [rnd.choice(words) if rnd.random() < 0.7 else rnd.choice(["x1", "7", UUID_SAMPLE, "", "..."])
                for _ in range(depth)]
        scopes.append(_scope("/" + "/".join(segs), rnd.choice(METHODS)))
    diffs = _compare(routes, scopes)
    assert len(scopes) > 15000
    assert not diffs, f"{len(diffs)} 个请求分派不同，首个：{diffs[0]}"


async def _ok(request):
    return PlainTextResponse("ok")


class _OddRoute(Route):
    """自定义 matches：不按路径正则（索引不得假设它的形状）。"""

    def matches(self, scope):
        if scope["type"] == "http" and scope["path"].endswith("/odd"):
            return Match.FULL, {"endpoint": self.endpoint, "path_params": {}}
        return Match.NONE, {}


def _synthetic_routes():
    sub = Router(routes=[Route("/inner", _ok)])
    return [
        Route("/", _ok),
        Route("/api/items", _ok, methods=["GET"]),
        Route("/api/items/", _ok, methods=["POST"]),
        Route("/api/items/{item_id:int}", _ok, methods=["GET"]),
        Route("/api/items/{item_id}", _ok, methods=["DELETE"]),
        Route("/api/v{version:int}/ping", _ok),
        Route("/api/files/{rest:path}", _ok),
        Route("/api/sync/{entry:path}/store", _ok, methods=["PUT"]),
        Route("/api/{tenant}/settings", _ok),
        Route("/api/report.{fmt}", _ok),
        _OddRoute("/never/used", _ok),
        Host("{sub}.example.org", app=sub),
        Mount("/static", app=sub),
        Mount("/m/{tenant}", routes=[Route("/inner", _ok)]),
        WebSocketRoute("/ws/{room}", _ok),
        Route("/{catch_all:path}", _ok, methods=["PATCH"]),
    ]


def test_synthetic_shapes_identical_to_linear_scan():
    routes = _synthetic_routes()
    paths = ["/", "", "/api/items", "/api/items/", "/api/items/3", "/api/items/x", "/api/items/3/", "/api/v2/ping",
             "/api/vx/ping", "/api/files/", "/api/files/a/b/c", "/api/files", "/api/sync/xlsx/gt-a51/store",
             "/api/sync/a/store/", "/api/acme/settings", "/api/report.json", "/x/odd", "/static/inner", "/static",
             "/static/", "/m/acme/inner", "/m/acme", "/ws/r1", "/nope", "//", "/api//items", "/api/items//"]
    scopes = [_scope(p, m) for p in paths for m in (*METHODS, "PATCH")]
    scopes += [_scope(p, "GET", "websocket") for p in ("/ws/r1", "/ws/", "/static/inner")]
    scopes += [dict(_scope("/api/items"), headers=[(b"host", b"a.example.org")])]
    assert len(scopes) > 150
    assert not _compare(routes, scopes)


def test_candidates_are_few_for_deep_routes():
    from app.main import app

    index = ri.RouteIndex(list(app.router.routes))
    cands = index.candidates(f"/api/projects/{UUID_SAMPLE}/workpapers/{UUID_SAMPLE}/ai/stocktake-summary")
    assert 1 <= len(cands) <= 20, len(cands)
    assert len(index.candidates("/api/notifications/unread-count")) <= 10


def test_mutations_rebuild_and_plain_list_falls_back():
    routes = [Route("/a", _ok), Route("/b/{x}", _ok)]
    recorder = _Recorder(routes)
    try:
        router = Router(routes=list(routes), default=recorder.default)
        assert ri.install_route_index(router) and ri.install_route_index(router)
        assert isinstance(router.routes, ri.VersionedRoutes)

        async def hit(path):
            return (await _outcome(router, recorder, _scope(path)))[0]

        assert asyncio.run(hit("/a"))[:2] == ("route", 0)

        async def extra_handle(scope, receive, send):
            recorder.hits.append(("route", "extra", {}))

        extra = Route("/c", _ok)
        extra.handle = extra_handle
        router.routes.insert(0, extra)  # 改动后下一次请求重建
        assert asyncio.run(hit("/c")) == ("route", "extra", {})
        assert asyncio.run(hit("/a"))[:2] == ("route", 0)
        router.routes[0] = Route("/d", _ok)  # 原位替换（长度不变）也要重建
        router.routes[0].handle = extra_handle
        assert asyncio.run(hit("/c"))[0] == "default" and asyncio.run(hit("/d"))[1] == "extra"
        router.routes = [routes[1]]  # 整体换成普通列表：退回逐条扫描，结果照样对
        assert asyncio.run(hit("/b/1"))[:2] == ("route", 1) and asyncio.run(hit("/a"))[0] == "default"
    finally:
        recorder.restore()


def test_version_gate_and_switch(monkeypatch):
    router = Router(routes=[Route("/a", _ok)])
    monkeypatch.setenv("GT_ROUTE_INDEX", "0")
    assert ri.install_route_index(router) is False and router.middleware_stack == router.app
    monkeypatch.delenv("GT_ROUTE_INDEX")
    monkeypatch.setattr(ri, "VALIDATED_STARLETTE_VERSIONS", frozenset({"0.0.0"}))
    assert ri.install_route_index(router) is False and router.middleware_stack == router.app


def test_pinned_starlette_version_is_enabled():
    import starlette

    assert starlette.__version__ in ri.VALIDATED_STARLETTE_VERSIONS, (
        "Starlette 升级了：先核对 Router.app 源码再把版本加进 VALIDATED_STARLETTE_VERSIONS")


def test_main_installs_index_after_routes():
    from app.main import app

    assert getattr(app.router.middleware_stack, "__gt_route_index__", None) is not None
    assert isinstance(app.router.routes, ri.VersionedRoutes) and len(app.router.routes) > 2000


def test_websocket_candidates_and_lifespan_passthrough():
    seen = []

    class R(Router):
        async def lifespan(self, scope, receive, send):
            seen.append("lifespan")

    router = R(routes=[WebSocketRoute("/ws/{room}", _ok)])
    assert ri.install_route_index(router)
    asyncio.run(router({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]
    index = ri.RouteIndex(router.routes)
    assert index.candidates("/ws/r1") == [0] and index.candidates("/ws") == []


def test_uuid_param_sample_is_valid():
    assert str(uuid.UUID(UUID_SAMPLE)) == UUID_SAMPLE
