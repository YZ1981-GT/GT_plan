"""8 个自有中间件改纯 ASGI（spec backend-startup-and-request-overhead R3.1，任务 8）。

判据：
1. 同一组 62 个请求（``tests/_middleware_equivalence.py``）与改之前（``BaseHTTPMiddleware``）存下的快照逐项相同：
   状态码、响应头（不计跨名字的先后）、解压后的响应体、审计日志调用、请求日志、端点里看到的 request_id / in-flight、
   413 / 429 / 405 / 404 / 307 / CORS。与快照不同的只有两类有意差别（design §7）：
   - 小于 GZip ``minimum_size`` 的响应不再被压、不再带 ``Vary: Accept-Encoding``（原来内层每个
     ``BaseHTTPMiddleware`` 都把响应改成流式，GZip 对流式一律压，``minimum_size=1000`` 形同虚设）；
   - 无 content-length 的流式 JSON 超过 5MB 时原版只交出已读的部分（响应体被截断），现在完整转发。
2. 生产栈里没有 ``BaseHTTPMiddleware``。
3. in-flight 计数覆盖到响应体发完；审计日志在响应发出之后写；request_id 对外层中间件也可见。
4. 声明长度超 5MB 的 JSON 直接放行、不进缓冲（快照只看最终字节，看不出缓冲没缓冲）。
5. 判定用的路径：Host 头正常时与原口径 ``Request(scope).url.path`` 逐字相同；畸形 Host 头不再带偏路径（design §7）。
6. 会被包装 / 记审计的流式 JSON 输出到一半抛异常：500、不记审计（原版 200 + 半截响应体）。
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

from tests import _middleware_equivalence as harness

GOLDEN = Path(__file__).resolve().parent / "_snapshots" / "middleware_stack_equivalence.json"
GZIP_MIN = 1000
COMPARED = ("status", "encoding", "body", "body_len", "error", "audit", "logs", "inflight_after")


def _expected(old: dict) -> dict:
    """快照（旧实现）按有意差别 1 调整：小响应不压、不带 Vary: Accept-Encoding。"""
    exp = copy.deepcopy(old)
    if old["body_len"] >= GZIP_MIN:
        return exp
    headers = []
    for name, value in exp["headers"]:
        if name == "vary":
            tokens = [t.strip() for t in value.split(",") if t.strip().lower() != "accept-encoding"]
            if not tokens:
                continue
            value = ", ".join(tokens)
        if name == "content-encoding":
            continue
        headers.append([name, value])
    exp["headers"] = headers
    exp["encoding"] = ""
    return exp


def _full_stream_body() -> bytes:
    parts = [b"["] + [(b"," if i else b"") + b'{"i": %d, "pad": "%s"}' % (i, b"x" * 80) for i in range(harness.BIG_ROWS)]
    return b"".join(parts) + b"]"


@pytest.fixture(scope="module")
def results() -> dict[str, dict]:
    return {r["name"]: r for r in asyncio.run(harness.run_all())}


def test_same_as_basehttp_snapshot_except_intended_differences(results):
    golden = {r["name"]: r for r in json.loads(GOLDEN.read_text(encoding="utf-8"))}
    assert golden.keys() == results.keys() and len(golden) >= 60
    diffs = []
    for name, old in golden.items():
        new = results[name]
        assert new["content_length_ok"], f"{name}: content-length 与实际字节数不符"
        if old["known_diff"] == "stream_big":
            continue
        exp = _expected(old)
        for key in COMPARED:
            if exp[key] != new[key]:
                diffs.append((name, key, exp[key], new[key]))
        if sorted(map(tuple, exp["headers"])) != sorted(map(tuple, new["headers"])):
            diffs.append((name, "headers", exp["headers"], new["headers"]))
    assert not diffs, f"{len(diffs)} 处不同，首个：{diffs[0]}"


def test_streaming_json_over_limit_is_no_longer_truncated(results):
    golden = {r["name"]: r for r in json.loads(GOLDEN.read_text(encoding="utf-8"))}
    full = _full_stream_body()
    for name in ("GET stream-json-big", "GET stream-json-big gzip"):
        assert golden[name]["body_len"] < len(full), "快照里记的是原版截断后的长度"
        new = results[name]
        assert new["status"] == 200 and new["body_len"] == len(full)
        assert new["body"] == {"len": len(full), "sha256": hashlib.sha256(full).hexdigest()}


def test_small_responses_follow_gzip_minimum_size(results):
    small, mid = results["GET small json gzip"], results["GET mid-json gzip"]
    assert small["encoding"] == "" and small["body_len"] < GZIP_MIN
    assert mid["encoding"] == "gzip" and ["vary", "Accept-Encoding"] in mid["headers"]


def test_production_stack_has_no_basehttp_middleware():
    from app.main import app

    classes = [m.cls for m in app.user_middleware]
    names = {c.__name__ for c in classes}
    assert {"AppVersionHeaderMiddleware", "RequestBodyLimitMiddleware", "ObservabilityMiddleware",
            "ResponseWrapperMiddleware", "RequestIDMiddleware", "LLMRateLimitMiddleware", "AuditLogMiddleware",
            "InflightTrackingMiddleware"} <= names
    offenders = [c.__name__ for c in classes if isinstance(c, type) and issubclass(c, BaseHTTPMiddleware)]
    assert not offenders, offenders


async def _call(app, path: str, method: str = "GET", sent: list | None = None) -> list[dict]:
    sent = [] if sent is None else sent
    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(), "root_path": "",
             "query_string": b"", "headers": [(b"host", b"t")], "scheme": "http", "server": ("t", 80),
             "client": ("1.2.3.4", 1), "http_version": "1.1", "asgi": {"version": "3.0"}}
    inbox = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive():
        if inbox:
            return inbox.pop(0)
        await asyncio.sleep(3600)

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return sent


def test_inflight_covers_streaming_body():
    from app.middleware.inflight import InflightTrackingMiddleware, inflight_counter

    during: list[int] = []
    app = FastAPI()

    @app.get("/s")
    async def stream():
        async def gen():
            yield b"a"
            during.append(inflight_counter.value())
            yield b"b"

        return StreamingResponse(gen(), media_type="text/plain")

    app.add_middleware(InflightTrackingMiddleware)
    saved = inflight_counter._count
    inflight_counter._count = 0
    try:
        asyncio.run(_call(app, "/s"))
        assert during == [1], "流式响应还在输出时应计入 in-flight"
        assert inflight_counter.value() == 0
    finally:
        inflight_counter._count = saved


def _inflight_probe_app(media_type: str, probe: list[tuple[int, int, int]]):
    """返回一个在响应体输出中途抓三个计数的 app（media_type 决定是否算 SSE）。"""
    from app.middleware.inflight import InflightTrackingMiddleware, inflight_counter

    app = FastAPI()

    @app.get("/s")
    async def stream():
        async def gen():
            yield b"a"
            probe.append((
                inflight_counter.value(),
                inflight_counter.streaming(),
                inflight_counter.value_excluding_streams(),
            ))
            yield b"b"

        return StreamingResponse(gen(), media_type=media_type)

    app.add_middleware(InflightTrackingMiddleware)
    return app


def test_sse_stream_is_excluded_from_idle_view_but_still_in_flight():
    """SSE 长连接必须仍算 in-flight（drain 要等它），但不能算进 GC 空闲判定。"""
    from app.middleware.inflight import inflight_counter

    probe: list[tuple[int, int, int]] = []
    app = _inflight_probe_app("text/event-stream", probe)
    saved = (inflight_counter._count, inflight_counter._streaming)
    inflight_counter._count = 0
    inflight_counter._streaming = 0
    try:
        asyncio.run(_call(app, "/s"))
        assert probe == [(1, 1, 0)], f"SSE 输出中途应为 in-flight=1 / streaming=1 / 空闲视图=0，实得 {probe}"
        assert inflight_counter.value() == 0
        assert inflight_counter.streaming() == 0, "响应结束必须把 streaming 子计数减回去"
        assert inflight_counter.value_excluding_streams() == 0
    finally:
        inflight_counter._count, inflight_counter._streaming = saved


def test_non_sse_stream_counts_in_both_views():
    """反向用例：普通流式响应不得被当成 SSE 排除，否则 GC 会在真实请求进行中 freeze。"""
    from app.middleware.inflight import inflight_counter

    probe: list[tuple[int, int, int]] = []
    app = _inflight_probe_app("text/plain", probe)
    saved = (inflight_counter._count, inflight_counter._streaming)
    inflight_counter._count = 0
    inflight_counter._streaming = 0
    try:
        asyncio.run(_call(app, "/s"))
        assert probe == [(1, 0, 1)], f"非 SSE 流式响应应为 in-flight=1 / streaming=0 / 空闲视图=1，实得 {probe}"
    finally:
        inflight_counter._count, inflight_counter._streaming = saved


def test_sse_streaming_unmarked_even_when_body_raises():
    """SSE 中途抛错也必须把 streaming 子计数减回去，否则 freeze 永久被毒死。"""
    from app.middleware.inflight import InflightTrackingMiddleware, inflight_counter

    app = FastAPI()

    @app.get("/boom")
    async def boom():
        async def gen():
            yield b"a"
            raise RuntimeError("mid-stream")

        return StreamingResponse(gen(), media_type="text/event-stream")

    app.add_middleware(InflightTrackingMiddleware)
    saved = (inflight_counter._count, inflight_counter._streaming)
    inflight_counter._count = 0
    inflight_counter._streaming = 0
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(_call(app, "/boom"))
        assert inflight_counter.streaming() == 0
        assert inflight_counter.value() == 0
    finally:
        inflight_counter._count, inflight_counter._streaming = saved


def test_all_production_sse_endpoints_use_the_detected_media_type():
    """判据不按路由清单：全仓流式端点必须都用 ``text/event-stream``（即中间件识别的那个值）。

    若某处改用别名（如 ``application/x-ndjson``），它就会被算进空闲视图、让 freeze 再次永不发生；
    这条断言把「识别口径」与「生产实际用的值」钉在一起。
    """
    import re
    from pathlib import Path

    from app.middleware.inflight import STREAM_MEDIA_TYPE

    root = Path(__file__).resolve().parents[1] / "app"
    literal = STREAM_MEDIA_TYPE.decode()
    hosts = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if literal in p.read_text(encoding="utf-8")
    )
    assert len(hosts) >= 8, f"生产 SSE 宿主现算 {len(hosts)} 个，低于已知下界 ⇒ 口径或扫描面出错：{hosts}"
    # 反向：不得出现「流式响应用了别的 media_type」的写法（扫 StreamingResponse/EventSourceResponse 的
    # media_type= 实参，排除 text/event-stream 自身与非流式的 JSON/文件下载）。
    alias = re.compile(r"media_type=[\"'](application/x-ndjson|text/plain; *charset=utf-8; *stream)[\"']")
    offenders = [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if alias.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"这些文件用了 SSE 别名 media_type，会绕过空闲视图排除：{offenders}"


def _audit_order_app(monkeypatch, write_log):
    from app.middleware import audit_log
    from app.middleware.audit_log import AuditLogMiddleware

    monkeypatch.setattr(audit_log, "_write_log", write_log)
    app = FastAPI()

    @app.post("/api/things")
    async def create():
        return {"id": 1}

    app.add_middleware(AuditLogMiddleware)
    return app


class _Recorder(list):
    def __init__(self, order):
        super().__init__()
        self.order = order

    def append(self, message):
        if message["type"] == "http.response.body" and not message.get("more_body"):
            self.order.append("response sent")
        super().append(message)


def test_audit_log_committed_before_response_is_sent(monkeypatch):
    """R4.1：客户端看到成功响应时，审计日志必须已 commit。"""
    order: list[str] = []

    async def fake_write_log(**kwargs):
        order.append(f"log new_value={kwargs['new_value']}")
        return True

    app = _audit_order_app(monkeypatch, fake_write_log)
    sent = asyncio.run(_call(app, "/api/things", "POST", _Recorder(order)))
    assert order == ["log new_value={'id': 1}", "response sent"]
    assert sent[0]["status"] == 200 and json.loads(sent[-1]["body"]) == {"id": 1}


def test_audit_log_failure_is_fail_open_and_observable(monkeypatch):
    """写失败仍发原 2xx（避免重复写），但必须留下可观测失败状态。"""
    from app.middleware import audit_log

    order: list[str] = []

    def boom(**_kwargs):
        # async_session() 是同步调用、返回异步上下文管理器；这里模拟取会话就失败。
        raise RuntimeError("logs 表不可写")

    monkeypatch.setattr(audit_log, "async_session", boom)
    monkeypatch.setitem(audit_log._FAILURE_STATE, "failed_count", 0)
    monkeypatch.setitem(audit_log._FAILURE_STATE, "last_target", None)
    app = _audit_order_app(monkeypatch, audit_log._write_log)
    sent = asyncio.run(_call(app, "/api/things", "POST", _Recorder(order)))
    assert order == ["response sent"]
    assert sent[0]["status"] == 200 and json.loads(sent[-1]["body"]) == {"id": 1}
    state = audit_log.audit_log_failure_state()
    assert state["failed_count"] == 1 and state["last_target"] == "create thing"


def test_request_id_visible_to_outer_middleware():
    from app.middleware.request_id import RequestIDMiddleware, request_id_var

    seen: list[str] = []

    class Outer:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)
            seen.append(request_id_var.get())

    app = FastAPI()

    @app.get("/x")
    async def x():
        return {"rid": request_id_var.get()}

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(Outer)
    sent = asyncio.run(_call(app, "/x"))
    header = dict(sent[0]["headers"])[b"x-request-id"].decode()
    assert seen == [header] and json.loads(sent[1]["body"])["rid"] == header


def test_declared_large_json_streams_through_without_buffering():
    """content-length 超 5MB 的 JSON 不进缓冲（原版同样直接放行）：端点产出第二段之前，第一段已经发给客户端。"""
    from app.middleware.response import _MAX_WRAP_BYTES, ResponseWrapperMiddleware

    first = b" " * 1024
    total = _MAX_WRAP_BYTES + len(first)
    sent: list[dict] = []
    bodies_sent_before_second: list[int] = []
    app = FastAPI()

    @app.get("/api/big")
    async def big():
        async def gen():
            yield first
            bodies_sent_before_second.append(sum(1 for m in sent if m["type"] == "http.response.body"))
            yield b" " * (total - len(first))

        return StreamingResponse(gen(), media_type="application/json", headers={"content-length": str(total)})

    app.add_middleware(ResponseWrapperMiddleware)
    asyncio.run(_call(app, "/api/big", sent=sent))
    assert bodies_sent_before_second == [1]
    assert sum(len(m.get("body", b"")) for m in sent if m["type"] == "http.response.body") == total


def _path_scope(path: str, host: str | None) -> dict:
    headers = [] if host is None else [(b"host", host.encode("latin-1"))]
    return {"type": "http", "method": "POST", "path": path, "raw_path": path.encode("utf-8"), "root_path": "",
            "query_string": b"q=1", "headers": headers, "scheme": "http", "server": ("t", 80)}


def test_request_path_same_as_url_path_for_normal_hosts():
    from starlette.requests import Request

    from app.middleware._asgi import request_path

    paths = ["/api/item", "/api/item?x", "/a#b", "/a\tb", "/a\r\nb", "//x/y", "x", "x/y", "", "*", "/api/%3F",
             "/中文", "/a b", "/a;b=c", "/a/../b", "/[x", "/a]b"]
    for host in ("t", "t:8080", "[::1]:9980", "x@y", None):
        for path in paths:
            scope = _path_scope(path, host)
            assert request_path(scope) == Request(scope).url.path, (host, path)


def test_request_path_not_skewed_by_malformed_host():
    """原口径把 Host 头拼进 URL 再拆：畸形 Host 头能让限流认不出 LLM 端点、让写操作躲开审计日志、或直接抛异常。"""
    from starlette.requests import Request

    from app.middleware._asgi import request_path

    llm = "/api/projects/p1/wp-ai/explain"
    assert Request(_path_scope(llm, "x?")).url.path == ""
    assert Request(_path_scope("/api/things", "x/api/health?")).url.path == "/api/health"
    with pytest.raises(ValueError):
        _ = Request(_path_scope(llm, "[")).url.path
    for host in ("x?", "x#", "x/abc", "x/api/health?", "["):
        assert request_path(_path_scope(llm, host)) == llm, host
    assert request_path(_path_scope("[x", "t")) == "[x"  # 原口径抛 ValueError（500）；这里交给路由（404）


def test_exception_mid_stream_of_buffered_json_gives_500_without_audit(monkeypatch):
    """会被包装 / 记审计的 JSON 流式响应输出到一半抛异常：响应头还没发出，返回 500 统一错误信封、不记审计；原版是
    200 + 半截响应体，写操作还记一条审计（design §7-10）。不缓冲的流式响应（text/plain）与原版相同：200 + 已发出的部分。"""
    from app.middleware import audit_log

    calls: list[str] = []

    async def fake_write_log(**kwargs):
        calls.append(kwargs["action_type"])

    monkeypatch.setattr(audit_log, "_write_log", fake_write_log)
    app = harness.build_app()

    def broken(media_type: str) -> StreamingResponse:
        async def gen():
            yield b'{"a": ' if media_type == "application/json" else b"part"
            raise RuntimeError("中途炸了")

        return StreamingResponse(gen(), media_type=media_type)

    @app.get("/api/raise-json")
    async def raise_json():
        return broken("application/json")

    @app.post("/api/raise-write")
    async def raise_write():
        return broken("application/json")

    @app.get("/api/raise-text")
    async def raise_text():
        return broken("text/plain")

    def drive(method: str, path: str) -> dict:
        case = {"name": path, "method": method, "path": path, "headers": [], "body": b"", "query": b""}
        return asyncio.run(harness._drive(app, case))

    for method, path in (("GET", "/api/raise-json"), ("POST", "/api/raise-write")):
        out = drive(method, path)
        assert (out["status"], out["error"]) == (500, "RuntimeError"), (path, out)
        assert out["body"]["code"] == 500 and "data" not in out["body"], (path, out["body"])
    assert calls == []
    text = drive("GET", "/api/raise-text")
    assert (text["status"], text["body"], text["error"]) == (200, "part", "RuntimeError")


def test_health_reports_audit_log_failures_as_degraded(monkeypatch):
    """R4.2：审计写失败必须在公开健康状态里可见，不能只躺在日志里。"""
    from unittest.mock import AsyncMock, patch

    from fastapi import FastAPI as _FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.health import router
    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.middleware import audit_log

    async def _db():
        session = AsyncMock()
        session.execute = AsyncMock(return_value=None)
        yield session

    async def _redis():
        client = AsyncMock()
        client.ping = AsyncMock(return_value=True)
        yield client

    app = _FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    clean = AsyncMock(return_value={"applied_count": 0, "failures": []})
    drift = AsyncMock(return_value={"count": 0, "critical_count": 0, "items": []})

    async def run() -> tuple[dict, dict]:
        with patch("app.api.health._query_migration_status", new=clean), \
             patch("app.api.health._query_schema_drift", new=drift):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
                healthy = (await client.get("/api/health")).json()
                audit_log._record_failure("update", "workpaper")
                degraded = (await client.get("/api/health")).json()
        return healthy, degraded

    monkeypatch.setitem(audit_log._FAILURE_STATE, "failed_count", 0)
    monkeypatch.setitem(audit_log._FAILURE_STATE, "last_target", None)
    healthy, degraded = asyncio.run(run())
    assert healthy["status"] == "healthy" and healthy["audit_log"]["failed_count"] == 0
    assert degraded["status"] == "degraded"
    assert degraded["audit_log"]["failed_count"] == 1
    assert degraded["audit_log"]["last_target"] == "update workpaper"


# ── follow-up：Observability 日志快路 + scope path 缓存 ───────────────────────


def test_observability_normal_2xx_skips_headers_when_debug_disabled(monkeypatch):
    """WARNING 级生产日志下，普通 2xx 不构造最终会被丢弃的 log_data / request Headers。"""
    from app.middleware import observability
    from app.middleware.observability import ObservabilityMiddleware

    class ExplodingHeaders:
        def __init__(self, *args, **kwargs):
            raise AssertionError("普通 2xx DEBUG 关闭时不应构造请求 Headers")

    monkeypatch.setattr(observability, "Headers", ExplodingHeaders)
    monkeypatch.setattr(observability.logger, "isEnabledFor", lambda level: level >= 30)
    app = FastAPI()

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    app.add_middleware(ObservabilityMiddleware)
    sent = asyncio.run(_call(app, "/ok"))
    headers = dict(sent[0]["headers"])
    assert sent[0]["status"] == 200
    assert b"x-response-time" in headers, "快路不得删响应耗时契约"


def test_observability_log_priority_is_unchanged():
    from app.middleware.observability import _log_decision

    assert _log_decision(1, 200, "/api/x") == (10, "REQUEST")
    assert _log_decision(1, 404, "/api/x") == (20, "CLIENT_ERROR")
    assert _log_decision(1, 500, "/api/x") == (40, "SERVER_ERROR")
    # 慢请求优先于状态码；预期慢路径仍降为 DEBUG
    assert _log_decision(4000, 500, "/api/x") == (30, "SLOW_REQUEST")
    assert _log_decision(4000, 500, "/api/ai/chat") == (10, "SLOW_OK")


def test_request_path_is_cached_in_scope_and_keeps_sensitive_path_semantics():
    from app.middleware._asgi import request_path

    for original in ("/api/x", "/api/a?b", "[x", "/中 文"):
        scope = _path_scope(original, "t")
        first = request_path(scope)
        assert scope["_gt_request_path"] == first
        # 同一请求里的内层中间件必须复用缓存；改 path 用来证明没有重算。
        scope["path"] = "/mutated"
        assert request_path(scope) == first
