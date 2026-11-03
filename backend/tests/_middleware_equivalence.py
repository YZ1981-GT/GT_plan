"""中间件栈新旧等价判据的驱动（spec backend-startup-and-request-overhead R3.1，任务 8）。

按 ``app/main.py`` 的顺序和参数装好 8 个自有中间件 + GZip + CORS + 异常处理器，挂一组覆盖各分支的端点，直接按 ASGI
调用（不经 httpx，拿到原始响应头、原始字节与分段数），记录：状态码、响应头（按序）、解压后的响应体、审计日志调用、
请求日志、端点里看到的 request_id / in-flight 计数。旧实现（``BaseHTTPMiddleware``）跑一遍存成
``tests/_snapshots/middleware_stack_equivalence.json``，新实现与它逐项比较（``test_middleware_pure_asgi.py``）。

用法（生成快照）：``python -m tests._middleware_equivalence <输出 json>``（在 backend 目录下）
"""
from __future__ import annotations

import asyncio
import contextlib
import gzip
import hashlib
import json
import logging
import sys
import uuid
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

USER_ID = "0b6e6a43-5d4c-4f0e-9a5f-6a4e0c2d7b11"
OBJ_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
BIG_ROWS = 60_000  # 约 6 MB JSON
ORIGIN = "http://localhost:3030"


class FakeRedis:
    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = dict(counts)

    async def get(self, key):
        return self.counts.get(key)

    async def set(self, key, value, ex=None):
        self.counts[key] = int(value)

    async def incr(self, key):
        self.counts[key] = int(self.counts.get(key, 0)) + 1

    async def ttl(self, key):
        return 42


def build_app() -> FastAPI:
    from app.middleware.app_version import AppVersionHeaderMiddleware
    from app.middleware.audit_log import AuditLogMiddleware
    from app.middleware.body_limit import RequestBodyLimitMiddleware
    from app.middleware.error_handler import (
        generic_exception_handler,
        http_exception_handler,
        validation_exception_handler,
    )
    from app.middleware.gzip_offload import OffloadingGZipMiddleware
    from app.middleware.inflight import InflightTrackingMiddleware, inflight_counter
    from app.middleware.observability import ObservabilityMiddleware
    from app.middleware.rate_limiter import LLMRateLimitMiddleware
    from app.middleware.request_id import RequestIDMiddleware, request_id_var
    from app.middleware.response import ResponseWrapperMiddleware
    from app.core.offloop_json import preencoded_json_response

    app = FastAPI()

    def seen() -> dict:
        return {"rid": request_id_var.get(), "inflight": inflight_counter.value()}

    @app.get("/api/item")
    async def item():
        return {"id": 1, "name": "条目", **seen()}

    @app.get("/api/items")
    async def items():
        return [{"id": 1}, {"id": 2}]

    @app.get("/api/none")
    async def none():
        return None

    @app.get("/api/wrapped")
    async def wrapped():
        return {"code": 200, "message": "success", "data": {"id": 1}}

    @app.get("/api/http-error")
    async def http_error():
        raise HTTPException(status_code=404, detail="没有")

    @app.get("/api/validation")
    async def validation(n: int):
        return {"n": n}

    @app.get("/api/boom")
    async def boom():
        raise RuntimeError("炸了")

    @app.get("/api/server-error")
    async def server_error():
        return JSONResponse(status_code=503, content={"detail": "忙"})

    @app.get("/api/preencoded")
    async def preencoded():
        return preencoded_json_response(b'{"x": [1, 2]}')

    @app.get("/api/preencoded-409")
    async def preencoded_409():
        return preencoded_json_response(b'{"detail": "x"}', status_code=409)

    @app.get("/api/stream-json")
    async def stream_json():
        async def gen():
            yield b'{"a": '
            yield b'[1, 2, 3]}'

        return StreamingResponse(gen(), media_type="application/json")

    @app.get("/api/stream-json-big")
    async def stream_json_big():
        async def gen():
            yield b"["
            for i in range(BIG_ROWS):
                yield (b"," if i else b"") + b'{"i": %d, "pad": "%s"}' % (i, b"x" * 80)
            yield b"]"

        return StreamingResponse(gen(), media_type="application/json")

    @app.get("/api/big-json")
    async def big_json():
        return JSONResponse([{"i": i, "pad": "x" * 80} for i in range(BIG_ROWS)])

    @app.get("/api/mid-json")
    async def mid_json():
        return {"rows": [{"i": i, "pad": "y" * 40} for i in range(200)]}

    @app.get("/api/sse")
    async def sse():
        async def gen():
            yield "event: a\ndata: 1\n\n"
            yield "event: b\ndata: 2\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/download")
    async def download():
        return Response(content=b"\x00\x01binary", media_type="application/octet-stream",
                        headers={"Content-Disposition": "attachment; filename=x.bin"})

    @app.get("/api/attachment-json")
    async def attachment_json():
        return JSONResponse({"a": 1}, headers={"Content-Disposition": "attachment; filename=a.json"})

    @app.get("/api/no-content", status_code=204)
    async def no_content():
        return Response(status_code=204)

    @app.get("/api/html")
    async def html():
        return HTMLResponse("<p>hi</p>")

    @app.get("/api/bad-json")
    async def bad_json():
        return Response(content=b"{not json", media_type="application/json")

    @app.get("/api/with-background")
    async def with_background():
        done: list[int] = []
        return JSONResponse({"ok": True}, background=BackgroundTask(lambda: done.append(1)))

    @app.get("/api/slow")
    async def slow():
        await asyncio.sleep(1.2)  # 慢请求阈值在 run_all 里钉成 1000 ms：大载荷的序列化不会误判成慢
        return {"slow": True}

    @app.get("/api/ai-generate-slow")
    async def ai_slow():
        await asyncio.sleep(1.2)
        return {"slow": True}

    @app.post("/api/things")
    async def create_thing(request: Request):
        body = await request.json()
        return {"id": OBJ_ID, "echo": body, **seen()}

    @app.put("/api/things/{thing_id}")
    async def update_thing(thing_id: str):
        return {"id": thing_id, "updated": True}

    @app.delete("/api/things/{thing_id}")
    async def delete_thing(thing_id: str):
        return {"deleted": thing_id}

    @app.post("/api/things-fail")
    async def create_fail():
        return JSONResponse(status_code=400, content={"detail": "不行"})

    @app.post("/api/things-sse")
    async def create_sse():
        async def gen():
            yield "data: x\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/api/things-list")
    async def create_list():
        return [1, 2, 3]

    @app.post("/api/auth/login")
    async def login():
        return {"access_token": "t"}

    @app.post("/api/upload")
    async def upload(request: Request):
        return {"size": len(await request.body())}

    @app.post("/api/projects/p1/wp-ai/explain")
    async def llm():
        return {"llm": True}

    @app.post("/api/ai-chat/runs")
    async def ai_chat_run():
        return {"run": True}

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/events/stream")
    async def events_stream():
        return {"events": []}

    @app.get("/wopi/files/x")
    async def wopi():
        return {"wopi": True}

    @app.post("/api/wp/onlyoffice-callback")
    async def oo_callback():
        return {"error": 0}

    @app.get("/livez")
    async def livez():
        return {"alive": True, **seen()}

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    # 与 app/main.py 同序（先加 = 最内层）
    app.add_middleware(InflightTrackingMiddleware)
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(LLMRateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(ResponseWrapperMiddleware)
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(OffloadingGZipMiddleware, minimum_size=1000)
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(AppVersionHeaderMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_credentials=True, allow_methods=["*"],
                       allow_headers=["*"])
    return app


def _token() -> str:
    from app.core.security import create_access_token

    return create_access_token({"sub": USER_ID})


def cases() -> list[dict[str, Any]]:
    auth = [("authorization", f"Bearer {_token()}")]
    gz = [("accept-encoding", "gzip")]
    js = [("content-type", "application/json")]
    c: list[dict[str, Any]] = []

    def add(name, method, path, headers=(), body=b"", query=b"", **extra):
        c.append({"name": name, "method": method, "path": path, "headers": list(headers), "body": body,
                  "query": query, **extra})

    for p in ("/api/item", "/api/items", "/api/none", "/api/wrapped", "/api/http-error", "/api/boom",
              "/api/server-error", "/api/preencoded", "/api/preencoded-409", "/api/stream-json", "/api/sse",
              "/api/download", "/api/attachment-json", "/api/no-content", "/api/html", "/api/bad-json",
              "/api/with-background", "/api/health", "/api/events/stream", "/wopi/files/x", "/livez",
              "/api/nope", "/api/item/", "/openapi.json", "/api/mid-json"):
        add(f"GET {p}", "GET", p)
    add("GET validation", "GET", "/api/validation", query=b"n=abc")
    add("GET with request id", "GET", "/api/item", headers=[("x-request-id", "rid-from-client")])
    add("HEAD item", "HEAD", "/api/item")
    add("POST to GET route (405)", "POST", "/api/item")
    add("GET big-json gzip", "GET", "/api/big-json", headers=gz)
    add("GET big-json identity", "GET", "/api/big-json")
    add("GET mid-json gzip", "GET", "/api/mid-json", headers=gz)
    add("GET small json gzip", "GET", "/api/items", headers=gz)
    add("GET stream-json-big gzip", "GET", "/api/stream-json-big", headers=gz, known_diff="stream_big")
    add("GET stream-json-big", "GET", "/api/stream-json-big", known_diff="stream_big")
    add("GET sse gzip", "GET", "/api/sse", headers=gz)
    add("GET slow", "GET", "/api/slow")
    add("GET expected slow", "GET", "/api/ai-generate-slow")
    add("POST create", "POST", "/api/things", headers=auth + js + [("x-forwarded-for", "198.51.100.7, 10.0.0.1")],
        body=b'{"name": "x"}')
    add("POST create anon", "POST", "/api/things", headers=js, body=b'{"name": "y"}')
    add("PUT update", "PUT", f"/api/things/{OBJ_ID}", headers=auth)
    add("DELETE", "DELETE", f"/api/things/{OBJ_ID}", headers=auth)
    add("PATCH unknown", "PATCH", f"/api/things/{OBJ_ID}", headers=auth)
    add("POST fail", "POST", "/api/things-fail", headers=auth)
    add("POST sse", "POST", "/api/things-sse", headers=auth)
    add("POST list", "POST", "/api/things-list", headers=auth)
    add("POST login", "POST", "/api/auth/login")
    add("POST onlyoffice", "POST", "/api/wp/onlyoffice-callback")
    add("POST upload ok", "POST", "/api/upload", body=b"x" * 50)
    add("POST upload too big", "POST", "/api/upload", body=b"x" * 500)
    add("DELETE with big body", "DELETE", f"/api/things/{OBJ_ID}", body=b"x" * 500)
    add("POST llm under limit", "POST", "/api/projects/p1/wp-ai/explain", headers=auth)
    add("POST llm over limit", "POST", "/api/projects/p1/wp-ai/explain", headers=auth, redis={"llm": 999})
    add("POST llm no token", "POST", "/api/projects/p1/wp-ai/explain", redis={"llm": 999})
    add("POST llm redis down", "POST", "/api/projects/p1/wp-ai/explain", headers=auth, redis=None)
    add("POST ai chat under", "POST", "/api/ai-chat/runs", headers=auth, redis={"ai": 3})
    add("POST ai chat over", "POST", "/api/ai-chat/runs", headers=auth, redis={"ai": 999})
    add("GET ai chat path (no limit)", "GET", "/api/ai-chat/runs", headers=auth, redis={"ai": 999})
    add("CORS preflight", "OPTIONS", "/api/things",
        headers=[("origin", ORIGIN), ("access-control-request-method", "POST")])
    add("CORS simple", "GET", "/api/item", headers=[("origin", ORIGIN)])
    add("CORS other origin", "GET", "/api/item", headers=[("origin", "http://evil.example")])
    add("path with encoded ?", "GET", "/api/item?x", raw_path=b"/api/item%3Fx")
    return c


def _norm_json(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: ("<ts>" if k == "reset" and v[k] else _norm_json(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm_json(x) for x in v]
    return v


def _norm_log_arg(a: Any) -> Any:
    if isinstance(a, dict):
        return {k: v for k, v in a.items() if k != "duration_ms"}
    return a


def _log_args(record: logging.LogRecord) -> Any:
    """日志参数（比较取值，不只比键）：``logger.x("... %s", d)`` 只传一个 dict 时 logging 把 ``record.args`` 设成
    这个 dict 本身，逐项迭代只会得到键名。"""
    if isinstance(record.args, dict):
        return _norm_log_arg(record.args)
    return [_norm_log_arg(a) for a in (record.args or ())]


async def _drive(app, case: dict[str, Any]) -> dict[str, Any]:
    path = case["path"]
    raw_path = case.get("raw_path", path.encode())
    headers = [(k.encode(), v.encode()) for k, v in case["headers"]] + [(b"host", b"testserver")]
    if case["body"]:
        headers.append((b"content-length", str(len(case["body"])).encode()))
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1",
             "method": case["method"], "scheme": "http", "path": path, "raw_path": raw_path,
             "query_string": case["query"], "root_path": "", "headers": headers,
             "client": ("203.0.113.9", 50000), "server": ("testserver", 80), "state": {}}
    inbox = [{"type": "http.request", "body": case["body"], "more_body": False}]

    async def receive():
        if inbox:
            return inbox.pop(0)
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    error = None
    try:
        await app(scope, receive, send)
    except Exception as exc:  # noqa: BLE001 — ServerErrorMiddleware 发完 500 后照样上抛
        error = type(exc).__name__
    start = next((m for m in sent if m["type"] == "http.response.start"), None)
    raw = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    hdrs = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in (start or {}).get("headers", [])]
    enc = next((v for k, v in hdrs if k == "content-encoding"), "")
    body = gzip.decompress(raw) if enc == "gzip" and raw else raw
    lengths = [v for k, v in hdrs if k == "content-length"]
    norm_headers = []
    for k, v in hdrs:
        if k in ("content-length", "transfer-encoding"):
            continue
        if k == "x-response-time":
            v = "<ms>"
        if k == "x-request-id" and not any(h[0] == "x-request-id" for h in case["headers"]):
            v = "<rid>"
        norm_headers.append([k, v])
    client_rid = any(h[0] == "x-request-id" for h in case["headers"])
    if len(body) > 4000:
        shown: Any = {"len": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    else:
        try:
            shown = _norm_rid(_norm_json(json.loads(body)), client_rid)
        except (ValueError, UnicodeDecodeError):
            shown = body.decode("utf-8", "replace")
    return {
        "status": start["status"] if start else None,
        "headers": norm_headers,
        "encoding": enc,
        "body": shown,
        "body_len": len(body),
        "content_length_ok": all(int(v) == len(raw) for v in lengths),
        "has_content_length": bool(lengths),
        "body_messages": sum(1 for m in sent if m["type"] == "http.response.body"),
        "error": error,
    }


def _norm_rid(v: Any, client_rid: bool) -> Any:
    """端点回显的 request_id：客户端没给时是随机值，记成 <rid>（"-" 表示没设上，原样保留）。"""
    if isinstance(v, dict):
        return {k: ("<rid>" if k == "rid" and not client_rid and x != "-" else _norm_rid(x, client_rid))
                for k, x in v.items()}
    if isinstance(v, list):
        return [_norm_rid(x, client_rid) for x in v]
    return v


async def run_all() -> list[dict[str, Any]]:
    import app.middleware.body_limit as body_limit
    import app.middleware.observability as observability
    from app.core.config import settings
    from app.middleware.audit_log import _write_log  # noqa: F401 - 确认存在
    from app.middleware.inflight import inflight_counter
    from app.middleware.rate_limiter import LLMRateLimitMiddleware, _ai_chat_rate_limit_key, _rate_limit_key

    audit_calls: list[dict] = []

    async def fake_write_log(**kwargs):
        audit_calls.append({k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in kwargs.items()})

    log_records: list[logging.LogRecord] = []

    class Grab(logging.Handler):
        def emit(self, record):
            log_records.append(record)

    grab = Grab(level=logging.DEBUG)
    loggers = [logging.getLogger("audit_platform.metrics"), logging.getLogger("audit_platform.error")]
    saved = [(lg, lg.level, lg.propagate) for lg in loggers]
    for lg in loggers:
        lg.addHandler(grab)
        lg.setLevel(logging.DEBUG)
    results = []
    redis_state: dict[str, Any] = {"client": None}

    async def fake_get_redis(self):
        return redis_state["client"]

    saved_count = inflight_counter._count
    try:
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("app.middleware.audit_log._write_log", new=fake_write_log))
            stack.enter_context(patch("app.middleware.app_version.get_build_version",
                                      new=lambda: {"git_commit": "testcommit"}))
            stack.enter_context(patch.object(body_limit, "_MAX_BYTES", 100))
            stack.enter_context(patch.object(observability, "_SLOW_REQUEST_MS", 1000))
            # 进响应文案的配置值钉成默认值：快照不随 .env 变
            stack.enter_context(patch.object(settings, "MAX_REQUEST_BODY_MB", 850))
            stack.enter_context(patch("app.middleware.rate_limiter.LLM_RATE_LIMIT_PER_MINUTE", 10))
            stack.enter_context(patch("app.middleware.rate_limiter.AI_CHAT_RATE_LIMIT_PER_MINUTE", 20))
            stack.enter_context(patch.object(LLMRateLimitMiddleware, "_get_redis", new=fake_get_redis))
            app = build_app()
            for case in cases():
                inflight_counter._count = 0
                audit_calls.clear()
                log_records.clear()
                spec = case.get("redis", {})
                if spec is None:
                    redis_state["client"] = None
                else:
                    counts = {}
                    if "llm" in spec:
                        counts[_rate_limit_key(USER_ID)] = spec["llm"]
                    if "ai" in spec:
                        counts[_ai_chat_rate_limit_key(USER_ID)] = spec["ai"]
                    redis_state["client"] = FakeRedis(counts)
                out = await _drive(app, case)
                out["name"] = case["name"]
                out["known_diff"] = case.get("known_diff")
                client_rid = any(h[0] == "x-request-id" for h in case["headers"])
                out["audit"] = [_norm_rid(call, client_rid) for call in audit_calls]
                out["logs"] = [[r.name, r.levelname, r.msg, _log_args(r)
                                if r.name != "audit_platform.error" else str(r.getMessage()).splitlines()[0]]
                               for r in log_records]
                out["inflight_after"] = inflight_counter.value()
                results.append(out)
    finally:
        inflight_counter._count = saved_count
        for lg, level, propagate in saved:
            lg.removeHandler(grab)
            lg.setLevel(level)
            lg.propagate = propagate
    return results


def main() -> None:
    results = asyncio.run(run_all())
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1, default=str)
    print(f"{len(results)} cases -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
