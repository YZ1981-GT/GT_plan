"""地址库整库加载不得在事件循环上做整包编码 / 解码 / 压缩（spec writeback-followup-issue-closure R5）。

实测（重药安徽 2025，6.98 万条地址，返回 5 万条 / 27.6 MB）：开发服务器上一次热请求让事件循环停 1.1 s，
冷请求 2.1 s。构成：FastAPI ``jsonable_encoder`` 逐值递归 0.75 s、GZip level 9 压 27.6 MB 0.35 s、
Redis 二级缓存整包 ``json.loads`` / ``asdict + dumps``、辅助余额 5.6 万条逐行构建。

判据（逐项可变异打红）：
1. 分块编码与 ``json.dumps`` 字节逐一相同；Redis 值逐行分块、旧格式（整包一个数组）照常读；
2. 路由在工作线程里编码、不经 ``jsonable_encoder``，响应仍是原来的业务载荷；
3. ``ResponseWrapperMiddleware`` 按字节拼信封（> 5 MB 也包），内部标记头不外泄；
4. 大响应体的 gzip 在工作线程里压；小响应 / 流式 / 已带编码的照上游原逻辑；
5. Redis 二级缓存编解码、辅助余额逐行构建都在工作线程。
"""
from __future__ import annotations

import asyncio
import enum
import json
from dataclasses import asdict
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware, GZipResponder
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from app.core import offloop_json as OJ
from app.core.database import get_db
from app.deps import get_current_user
from app.middleware.gzip_offload import OFFLOAD_MIN_BYTES, OffloadingGZipMiddleware
from app.middleware.response import ResponseWrapperMiddleware
from app.routers import address_registry as router_module
from app.services import address_registry as svc


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _spy(target, name: str, monkeypatch, seen: list[bool]):
    real = getattr(target, name)

    def wrapper(*args, **kwargs):
        seen.append(_on_event_loop())
        return real(*args, **kwargs)

    monkeypatch.setattr(target, name, wrapper)


class _Color(str, enum.Enum):
    red = "red"


class _Plain(enum.Enum):
    one = 1


# ── 1. 编码等价 ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("items", [
    [],
    [{"a": 1}],
    [{"label": "辅助余额 > 1122 应收账款 > 甲公司\n换行", "tags": ["x", "y"]} for _ in range(7)],
    [[1, 2], "s", None, 1.5, {"k": [{"n": "中文"}]}],
])
@pytest.mark.parametrize("chunk", [1, 3, 2000])
def test_chunked_array_is_byte_identical_to_json_dumps(items, chunk):
    assert OJ.encode_json_array_chunked(items, chunk) == json.dumps(items, ensure_ascii=False).encode("utf-8")
    head = {"total": len(items), "truncated": False, "truncated_domains": ["aux"]}
    expected = json.dumps({**head, "items": items}, ensure_ascii=False).encode("utf-8")
    assert OJ.encode_object_with_chunked_array(head, "items", iter(items), chunk) == expected
    empty_head = json.dumps({"items": items}, ensure_ascii=False).encode("utf-8")
    assert OJ.encode_object_with_chunked_array({}, "items", items, chunk) == empty_head


def test_enum_and_set_follow_jsonable_encoder_and_other_types_still_fail():
    assert json.loads(OJ.encode_json_array_chunked([_Color.red, _Plain.one, {3}])) == ["red", 1, [3]]
    with pytest.raises(TypeError):
        OJ.encode_json_array_chunked([object()])
    with pytest.raises(ValueError):
        OJ.encode_object_with_chunked_array({"items": 1}, "items", [])


def test_json_lines_round_trip_and_old_single_array_format():
    items = [{"v": i, "s": "a\nb"} for i in range(10)]
    raw = OJ.encode_json_lines(items, 3)
    assert raw.count(b"\n") == 3, "10 条按 3 条一块应是 4 行"
    assert [x for b in OJ.iter_json_line_batches(raw) for x in b] == items
    assert [x for b in OJ.iter_json_line_batches(raw.decode()) for x in b] == items
    old = json.dumps(items, ensure_ascii=False)
    assert [x for b in OJ.iter_json_line_batches(old) for x in b] == items
    assert list(OJ.iter_json_line_batches(b"")) == []


# ── 2/3. 路由 + 信封 ─────────────────────────────────────────────────────────

_ITEM_KEYS = ["uri", "domain", "source", "path", "cell", "label", "formula_ref", "jump_route",
              "row_code", "account_code", "note_section", "wp_code", "tags"]


def _entries(n: int, label: str = "条目") -> list[svc.AddressEntry]:
    return [
        svc.AddressEntry(uri=f"aux://1122/甲{i}#期末", domain="aux", source="1122", path=f"甲{i}", cell="期末",
                         label=f"{label}{i}", account_code="1122", formula_ref=f"AUX('1122','甲{i}','期末')",
                         jump_route=f"/projects/p1/ledger?account=1122&i={i}", tags=["辅助余额", "应收账款"], value=1.0)
        for i in range(n)
    ]


class _Passthrough(BaseHTTPMiddleware):
    """生产栈里 GZip 与 ResponseWrapper 之间还有 Observability（BaseHTTPMiddleware）：它把响应改成流式
    （数据段 more_body=True + 末尾空段）。测试栈缺这一层时 gzip 只见到整段响应，测不到生产形状。"""

    async def dispatch(self, request, call_next):
        return await call_next(request)


@pytest.fixture
def make_client(monkeypatch):
    if "_get_domain" in vars(svc.address_registry):
        monkeypatch.delattr(svc.address_registry, "_get_domain")

    def factory(entries: list[svc.AddressEntry]) -> TestClient:
        async def fake_get_domain(self, db, project_id, year, template_type, domain):
            return [e for e in entries if e.domain == domain]

        monkeypatch.setattr(svc.AddressRegistryService, "_get_domain", fake_get_domain)
        app = FastAPI()
        app.add_middleware(ResponseWrapperMiddleware)
        app.add_middleware(_Passthrough)
        app.add_middleware(OffloadingGZipMiddleware, minimum_size=1000)
        app.include_router(router_module.router)

        async def _db():
            yield None

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: object()
        return TestClient(app)

    return factory


def _search(client: TestClient, **params):
    return client.get("/api/address-registry", params={"project_id": "p1", "year": 2025, **params})


def test_payload_unchanged_and_wrapped_once_without_leaking_the_marker(make_client):
    entries = _entries(10)
    r = _search(make_client(entries), limit=4)
    assert r.status_code == 200
    assert OJ.PREENCODED_PAYLOAD_HEADER not in r.headers
    body = r.json()
    assert (body["code"], body["message"]) == (200, "success")
    data = body["data"]
    assert (data["total"], data["returned"], data["truncated"], data["truncated_domains"]) == (10, 4, True, ["aux"])
    assert list(data) == ["total", "returned", "truncated", "truncated_domains", "items"]
    for got, e in zip(data["items"], entries):
        assert list(got) == _ITEM_KEYS
        assert got == {k: getattr(e, k) for k in _ITEM_KEYS}


def test_large_payload_is_wrapped_too_and_gzipped_off_loop(make_client, monkeypatch):
    entries = _entries(12_000, label="很长的标签" * 30)
    client = make_client(entries)
    seen: list[bool] = []
    _spy(GZipResponder, "apply_compression", monkeypatch, seen)
    r = _search(client, limit=50_000)
    assert r.headers.get("content-encoding") == "gzip"
    assert seen == [False, True], "整段载荷在工作线程里压；只剩末尾空段在事件循环上收尾"
    assert len(r.content) > 5 * 1024 * 1024, "要覆盖原「> 5MB 不包信封」那条分支"
    body = r.json()
    assert body["code"] == 200 and body["data"]["returned"] == 12_000
    assert OJ.PREENCODED_PAYLOAD_HEADER not in r.headers


def test_search_skips_jsonable_encoder_and_encodes_off_loop(make_client, monkeypatch):
    import fastapi.routing

    def _forbidden(*_a, **_k):
        raise AssertionError("搜索响应不得再经 jsonable_encoder")

    monkeypatch.setattr(fastapi.routing, "jsonable_encoder", _forbidden)
    seen: list[bool] = []
    _spy(router_module, "encode_search_payload", monkeypatch, seen)
    assert _search(make_client(_entries(3)), limit=10).status_code == 200
    assert seen == [False], "载荷编码必须在工作线程（无运行中的事件循环）"


def test_preencoded_non_2xx_is_not_wrapped_and_marker_is_dropped():
    async def boom(_request):
        return OJ.preencoded_json_response(b'{"detail": "x"}', status_code=409)

    app = Starlette(routes=[Route("/x", boom)])
    app.add_middleware(ResponseWrapperMiddleware)
    r = TestClient(app).get("/x")
    assert r.status_code == 409 and r.json() == {"detail": "x"}
    assert OJ.PREENCODED_PAYLOAD_HEADER not in r.headers


# ── 4. gzip 在工作线程 ───────────────────────────────────────────────────────

def _gzip_app(body: bytes, *, streaming: bool = False, headers: dict | None = None) -> TestClient:
    async def endpoint(_request):
        if streaming:
            async def gen():
                yield body
                yield body
            return StreamingResponse(gen(), media_type="application/json")
        return Response(body, media_type="application/json", headers=headers)

    app = Starlette(routes=[Route("/b", endpoint)])
    app.add_middleware(OffloadingGZipMiddleware, minimum_size=1000)
    return TestClient(app)


def test_large_body_is_compressed_off_loop(monkeypatch):
    seen: list[bool] = []
    _spy(GZipResponder, "apply_compression", monkeypatch, seen)
    body = b'{"k": "' + b"x" * OFFLOAD_MIN_BYTES + b'"}'
    r = _gzip_app(body).get("/b")
    assert r.headers["content-encoding"] == "gzip" and r.content == body
    assert "accept-encoding" in r.headers.get("vary", "").lower()
    assert seen == [False]


def test_small_streaming_and_preencoded_bodies_keep_upstream_behaviour(monkeypatch):
    seen: list[bool] = []
    _spy(GZipResponder, "apply_compression", monkeypatch, seen)
    small = b"y" * 5000
    r = _gzip_app(small).get("/b")
    assert r.headers["content-encoding"] == "gzip" and r.content == small and seen == [True]
    seen.clear()
    big = b"z" * OFFLOAD_MIN_BYTES
    r = _gzip_app(big, streaming=True).get("/b")
    assert r.content == big + big
    assert seen == [False, False, True], "流式的大段也在工作线程里压，末尾空段在事件循环上收尾"
    seen.clear()
    r = _gzip_app(b"s" * 2000, streaming=True).get("/b")
    assert r.content == b"s" * 4000 and seen == [True, True, True], "流式小段照上游在事件循环上压"
    seen.clear()
    r = _gzip_app(big, headers={"Content-Encoding": "identity"}).get("/b")
    assert r.content == big and seen == []


def test_main_app_uses_the_offloading_gzip_middleware():
    from app.main import app

    classes = [m.cls for m in app.user_middleware]
    assert OffloadingGZipMiddleware in classes
    assert GZipMiddleware not in classes


# ── 5. Redis 二级缓存 / 辅助余额构建 ─────────────────────────────────────────

def test_cached_entries_round_trip_in_chunks_and_read_the_old_format():
    entries = _entries(2 * OJ.JSON_CHUNK_ITEMS + 1)
    raw = svc._encode_cached_entries(entries)
    assert raw.count(b"\n") == 2, "分块写：每块一行"
    assert svc._decode_cached_entries(raw) == entries
    old = json.dumps([asdict(e) for e in entries[:5]], ensure_ascii=False)
    assert svc._decode_cached_entries(old) == entries[:5], "旧格式（整包一个数组）照常读"


@pytest.mark.asyncio
async def test_redis_codec_runs_off_loop(monkeypatch):
    service = svc.AddressRegistryService()
    redis = AsyncMock()
    stored: dict[str, bytes] = {}

    async def _set(key, value, ex=None):
        stored[key] = value

    redis.set = AsyncMock(side_effect=_set)
    redis.get = AsyncMock(side_effect=lambda key: stored.get(key))
    monkeypatch.setattr(service, "_get_redis", AsyncMock(return_value=redis))
    seen: list[bool] = []
    _spy(svc, "_encode_cached_entries", monkeypatch, seen)
    _spy(svc, "_decode_cached_entries", monkeypatch, seen)
    entries = _entries(5)
    await service._redis_set("p1:2025:soe:aux", entries, "aux")
    assert await service._redis_get("p1:2025:soe:aux") == entries
    assert seen == [False, False]


@pytest.mark.asyncio
async def test_aux_entries_are_built_off_loop(monkeypatch):
    import uuid
    from types import SimpleNamespace

    row = SimpleNamespace(account_code="1122", account_name="应收账款", aux_type="customer",
                          aux_type_name="往来单位", aux_code="C001", aux_name="甲公司")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: [row]))
    seen: list[bool] = []
    _spy(svc, "_aux_entries_from_rows", monkeypatch, seen)
    got = await svc.build_aux_entries(db, str(uuid.uuid4()), 2025)
    assert {e.formula_ref for e in got} >= {"AUX('1122','甲公司','期末')", "AUX('1122','customer','期末')"}
    assert seen == [False]
