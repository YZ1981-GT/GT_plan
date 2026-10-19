"""本机优先路由（spec llm-ocr-local-first-routing，V197）：部署位置、候选排序、错误分类、冷却、
路由执行、熔断按整条路由、实际服务模型、启用唯一索引语义。

出站一律换成 MockTransport（替换 ``llm_runtime.build_runtime_client``），失败原因描述不做真实 DNS。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.models.ai_model_options import classify_deployment, endpoint_is_loopback
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.services import llm_route
from app.services.llm_provider_registry import provider_profile
from app.services.llm_runtime import (
    LLMRuntimeError,
    ResolvedLLMConfig,
    RouteCandidate,
    classify_model_deployment,
    deployment_of,
    order_candidates,
)

LOCAL = "http://localhost:8100/v1"
SERVER = "https://ai.example.test/v1"
MESSAGES = [{"role": "user", "content": "你好"}]
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def _candidate(model: str, endpoint: str, *, model_id=None) -> RouteCandidate:
    local = endpoint_is_loopback(endpoint)
    provider = AIProvider.openai_compatible if local else AIProvider.custom
    config = ResolvedLLMConfig(
        model_name=model, model_type=AIModelType.chat, provider=provider,
        endpoint_url=endpoint, api_key=None if local else "k",
        profile=provider_profile(provider), source="database", model_id=model_id,
        deployment="local" if local else "server",
    )
    return RouteCandidate(model, config.deployment, model_id, config)


def _pair():
    return _candidate("Qwen3.5", LOCAL), _candidate("qwen3.8", SERVER, model_id=uuid4())


def _ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture(autouse=True)
def _isolated_route_state(monkeypatch):
    """冷却记录、路由结果与熔断器都是进程级状态：用例间隔离；失败原因描述不做真实 DNS。"""
    from app.services import llm_client

    async def _describe(endpoint, exc):
        return type(exc).__name__

    monkeypatch.setattr("app.services.llm_runtime.describe_network_failure", _describe)
    llm_route.reset_route_health()
    llm_route.clear_route_outcome()
    llm_client._breaker.reset()
    yield
    llm_route.reset_route_health()
    llm_client._breaker.reset()


class _Net:
    """按端点前缀分派出站：值为 Response、要抛出的异常（AssertionError = 不该被调用）。"""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.seen: list[httpx.Request] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        for prefix, outcome in self.routes.items():
            if str(request.url).startswith(prefix):
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome
        raise AssertionError(f"unexpected request {request.url}")

    async def client(self, config, *, timeout, connect_timeout=10.0):
        return httpx.AsyncClient(
            base_url=config.endpoint_url.rstrip("/") + "/",
            transport=httpx.MockTransport(self._handle),
        )

    def models(self) -> list[str]:
        return [json.loads(request.content)["model"] for request in self.seen]


@pytest.fixture
def net(monkeypatch):
    def install(routes: dict[str, object]) -> _Net:
        stub = _Net(routes)
        monkeypatch.setattr("app.services.llm_runtime.build_runtime_client", stub.client)
        return stub

    return install


# ---------------------------------------------------------------------------
# 部署位置（ADR-ROUTE-001）
# ---------------------------------------------------------------------------

_ENDPOINT_CASES = [
    ("http://localhost:8100/v1", "local"),
    ("http://LOCALHOST:8100/v1", "local"),
    ("http://127.0.0.1:8100/v1", "local"),
    ("http://127.8.9.10/v1", "local"),
    ("http://[::1]:8100/v1", "local"),
    ("https://ai.gt-china.com.cn:10010/v1", "server"),
    ("http://192.168.0.41:10010/v1", "server"),  # 企业网关内网地址也是服务器
    ("http://10.0.0.1/v1", "server"),
    ("http://localhost.localdomain/v1", "server"),
    ("http://127.0.0.1.example.test/v1", "server"),
]


@pytest.mark.parametrize(("endpoint", "expected"), _ENDPOINT_CASES + [("", "server"), (None, "server")])
def test_deployment_follows_the_literal_host(endpoint, expected):
    assert classify_deployment(endpoint_url=endpoint) == expected


def test_local_ocr_engine_is_local_whatever_the_endpoint():
    remote = "https://ai.gt-china.com.cn:10080"
    assert classify_deployment(endpoint_url=remote, ocr_protocol="local") == "local"
    assert classify_deployment(endpoint_url=remote, ocr_protocol="paddlex_json") == "server"


@pytest.mark.parametrize(("provider", "expected"), [
    (AIProvider.openai_compatible, "local"),  # 默认端点 localhost:8100
    (AIProvider.ollama, "local"),             # 默认端点 localhost:11434
    (AIProvider.deepseek, "server"),
    (AIProvider.custom, "server"),            # 无默认端点
])
def test_empty_endpoint_uses_the_provider_default(provider, expected):
    row = SimpleNamespace(endpoint_url=None, provider=provider, ocr_protocol=None)
    assert classify_model_deployment(row) == expected


def test_stored_deployment_wins_and_an_invalid_value_is_rederived():
    row = SimpleNamespace(
        endpoint_url=LOCAL, provider=AIProvider.openai_compatible, ocr_protocol=None, deployment="server"
    )
    assert deployment_of(row) == "server"
    row.deployment = "garbage"
    assert deployment_of(row) == "local"


def test_v197_backfill_regex_agrees_with_runtime_classification():
    """迁移回填（SQL 正则）与运行时 classify_deployment 必须同一口径，否则回填后的行与新建行分类不同。"""
    sql = (MIGRATIONS / "V197__ai_model_config_deployment_local_first_routing.sql").read_text(encoding="utf-8")
    match = re.search(r"endpoint_url ~\* '([^']+)'", sql)
    assert match, "V197 回填正则变了，更新本用例的提取方式"
    loopback = re.compile(match.group(1), re.IGNORECASE)
    for endpoint, expected in _ENDPOINT_CASES:
        assert bool(loopback.search(endpoint)) is (expected == "local"), endpoint
        assert endpoint_is_loopback(endpoint) is (expected == "local"), endpoint


# ---------------------------------------------------------------------------
# 候选排序（ADR-ROUTE-005）与错误分类（ADR-ROUTE-003）
# ---------------------------------------------------------------------------


def test_local_first_and_the_requested_model_is_only_a_hint():
    local, server = _pair()
    assert order_candidates([server, local]) == [local, server]
    assert order_candidates([server, local], requested_model="qwen3.8") == [server, local]
    # 点名一个没有启用的模型：忽略（旧行为是把它发给 DB 端点 ⇒ 404）
    assert order_candidates([server, local], requested_model="gpt-4o") == [local, server]
    assert order_candidates([server, local], requested_model="  ") == [local, server]


@pytest.mark.parametrize(("status", "kind"), [
    (401, "config"), (403, "config"), (404, "config"),
    (500, "unavailable"), (502, "unavailable"), (503, "unavailable"),
    (400, "request"), (422, "request"), (429, "request"),
])
def test_http_status_decides_whether_to_fail_over(status, kind):
    from app.services.llm_runtime import _raise_for_status

    with pytest.raises(LLMRuntimeError) as caught:
        _raise_for_status(httpx.Response(status))
    assert caught.value.kind == kind
    assert caught.value.failover is (kind in {"config", "unavailable"})


@pytest.mark.asyncio
@pytest.mark.parametrize(("exc", "kind"), [
    (httpx.ConnectError("refused"), "unavailable"),
    (httpx.ConnectTimeout("slow connect"), "unavailable"),
    (httpx.ReadTimeout("slow answer"), "timeout"),
    (httpx.WriteTimeout("slow upload"), "timeout"),
    (httpx.RemoteProtocolError("dropped mid-response"), "request"),
])
async def test_only_connection_phase_failures_fail_over(exc, kind):
    from app.services.llm_runtime import _transport_error

    error = await _transport_error(_candidate("m", LOCAL).config, exc)
    assert error.kind == kind


@pytest.mark.asyncio
async def test_endpoint_policy_block_fails_over():
    from app.services.llm_endpoint_policy import LLMEndpointPolicyError
    from app.services.llm_runtime import _transport_error

    error = await _transport_error(_candidate("m", SERVER).config, LLMEndpointPolicyError("blocked"))
    assert (error.code, error.kind, error.failover) == ("endpoint_blocked", "unavailable", True)


# ---------------------------------------------------------------------------
# 冷却期（ADR-ROUTE-004）
# ---------------------------------------------------------------------------


def test_cooling_candidate_is_skipped_only_while_others_remain():
    local, server = _pair()
    llm_route.mark_unavailable(local.identity, "端点不可达")
    assert llm_route.plan_attempts([local, server]) == [server]
    llm_route.mark_unavailable(server.identity, "端点不可达")
    assert llm_route.plan_attempts([local, server]) == [local, server]  # 全部冷却：按顺序全试
    llm_route.mark_available(local.identity)
    assert llm_route.plan_attempts([local, server]) == [local]


def test_cooldown_expires(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(llm_route, "time", SimpleNamespace(time=lambda: 0.0, monotonic=lambda: clock[0]))
    local, server = _pair()
    llm_route.mark_unavailable(local.identity, "端点不可达")
    clock[0] += settings.LLM_ROUTE_COOLDOWN_SECONDS - 0.1
    assert llm_route.is_cooling(local.identity)
    clock[0] += 0.2
    assert not llm_route.is_cooling(local.identity)
    assert llm_route.plan_attempts([local, server]) == [local, server]


# ---------------------------------------------------------------------------
# 路由执行：转移 / 不转移 / 实际服务模型（ADR-ROUTE-003/004/008）
# ---------------------------------------------------------------------------

_NOT_CALLED = AssertionError("这一端不该被调用")


@pytest.mark.asyncio
async def test_local_answers_when_available(net):
    local, server = _pair()
    stub = net({LOCAL: _ok("本机回答"), SERVER: _NOT_CALLED})
    assert await llm_route.route_chat_sync([local, server], MESSAGES) == "本机回答"
    outcome = llm_route.last_route_outcome()
    assert (outcome.model_name, outcome.deployment, outcome.fallback_used) == ("Qwen3.5", "local", False)
    assert stub.models() == ["Qwen3.5"]


@pytest.mark.asyncio
async def test_unreachable_local_fails_over_and_records_who_answered(net):
    local, server = _pair()
    stub = net({LOCAL: httpx.ConnectError("refused"), SERVER: _ok("服务器回答")})
    assert await llm_route.route_chat_sync([local, server], MESSAGES) == "服务器回答"
    # 每个候选用自己的模型名（旧缺陷：DB 端点收到 `.env` 的模型名 ⇒ 404）
    assert stub.models() == ["Qwen3.5", "qwen3.8"]
    outcome = llm_route.last_route_outcome()
    assert (outcome.model_name, outcome.deployment, outcome.model_id) == ("qwen3.8", "server", server.model_id)
    assert outcome.fallback_used is True
    assert outcome.attempts == ("本机模型「Qwen3.5」：模型端点不可达：ConnectError",)
    assert llm_route.served_model_label("默认模型") == "qwen3.8"
    assert llm_route.is_cooling(local.identity)

    # 冷却期内下一次调用直接跳过本机（不再每次多等一次连接失败），并在 attempts 里说明
    again = net({LOCAL: _NOT_CALLED, SERVER: _ok("第二次")})
    assert await llm_route.route_chat_sync([local, server], MESSAGES) == "第二次"
    assert again.models() == ["qwen3.8"]
    assert llm_route.last_route_outcome().attempts == (
        "本机模型「Qwen3.5」：冷却中（模型端点不可达：ConnectError）",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    httpx.Response(500), httpx.Response(503), httpx.Response(401), httpx.Response(404),
    httpx.ConnectTimeout("slow connect"), httpx.Response(200, text="<html>不是 OpenAI 兼容</html>"),
])
async def test_unavailable_or_misconfigured_local_fails_over(net, failure):
    local, server = _pair()
    stub = net({LOCAL: failure, SERVER: _ok("服务器回答")})
    assert await llm_route.route_chat_sync([local, server], MESSAGES) == "服务器回答"
    assert stub.models() == ["Qwen3.5", "qwen3.8"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    httpx.Response(400), httpx.Response(422), httpx.Response(429), httpx.ReadTimeout("slow answer"),
    httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}),
    httpx.Response(200, json={"choices": [{"message": {"content": None}, "finish_reason": "length"}]}),
])
async def test_accepted_requests_are_not_replayed_on_the_server(net, failure):
    """请求已被接收（读超时）或在另一端会同样失败（参数 / 限流 / 空输出）：不转移、不冷却。"""
    local, server = _pair()
    stub = net({LOCAL: failure, SERVER: _NOT_CALLED})
    with pytest.raises(LLMRuntimeError) as caught:
        await llm_route.route_chat_sync([local, server], MESSAGES)
    assert caught.value.failover is False
    assert stub.models() == ["Qwen3.5"]
    assert llm_route.last_route_outcome() is None
    assert not llm_route.is_cooling(local.identity)


@pytest.mark.asyncio
async def test_exhausted_route_lists_every_candidate(net):
    local, server = _pair()
    net({LOCAL: httpx.ConnectError("refused"), SERVER: httpx.Response(503)})
    with pytest.raises(LLMRuntimeError) as caught:
        await llm_route.route_chat_sync([local, server], MESSAGES)
    assert str(caught.value) == (
        "本机模型「Qwen3.5」：模型端点不可达：ConnectError；服务器模型「qwen3.8」：模型提供商返回 HTTP 503"
    )
    assert caught.value.code == "provider_error"  # 取最后一个候选的 code
    assert llm_route.last_route_outcome() is None


@pytest.mark.asyncio
async def test_exhausted_route_names_skipped_cooling_candidates(net):
    local, server = _pair()
    llm_route.mark_unavailable(local.identity, "模型端点不可达：ConnectError")
    net({LOCAL: _NOT_CALLED, SERVER: httpx.Response(503)})
    with pytest.raises(LLMRuntimeError) as caught:
        await llm_route.route_chat_sync([local, server], MESSAGES)
    assert str(caught.value) == (
        "服务器模型「qwen3.8」：模型提供商返回 HTTP 503；"
        "本机模型「Qwen3.5」：冷却中（模型端点不可达：ConnectError）"
    )


@pytest.mark.asyncio
async def test_single_candidate_failure_keeps_the_original_error(net):
    local, _ = _pair()
    net({LOCAL: httpx.ConnectError("refused")})
    with pytest.raises(LLMRuntimeError) as caught:
        await llm_route.route_chat_sync([local], MESSAGES)
    assert str(caught.value) == "模型端点不可达：ConnectError"


@pytest.mark.asyncio
async def test_unresolvable_candidate_is_skipped_with_its_reason(net):
    broken = RouteCandidate(
        "缺 Key 的本机行", "local", uuid4(), None,
        LLMRuntimeError("api_key_required", "该提供商尚未配置 API Key", kind="config"),
    )
    _, server = _pair()
    net({SERVER: _ok("服务器回答")})
    assert await llm_route.route_chat_sync([broken, server], MESSAGES) == "服务器回答"
    assert llm_route.last_route_outcome().attempts == ("本机模型「缺 Key 的本机行」：该提供商尚未配置 API Key",)


class _SseStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], then: BaseException | None):
        self._chunks, self._then = chunks, then

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk
        if self._then is not None:
            raise self._then

    async def aclose(self) -> None:
        return None


def _sse(*contents: str, then: BaseException | None = None) -> httpx.Response:
    chunks = [
        f"data: {json.dumps({'choices': [{'delta': {'content': text}}]}, ensure_ascii=False)}\n\n".encode()
        for text in contents
    ]
    if then is None:
        chunks.append(b"data: [DONE]\n\n")
    return httpx.Response(200, stream=_SseStream(chunks, then))


@pytest.mark.asyncio
async def test_stream_fails_over_before_the_first_chunk(net):
    local, server = _pair()
    stub = net({LOCAL: httpx.ConnectError("refused"), SERVER: _sse("服务器", "回答")})
    chunks = [chunk async for chunk in llm_route.route_chat_stream([local, server], MESSAGES)]
    assert chunks == ["服务器", "回答"]
    assert stub.models() == ["Qwen3.5", "qwen3.8"]
    assert llm_route.last_route_outcome().fallback_used is True


@pytest.mark.asyncio
async def test_stream_never_splices_two_answers(net):
    """本机已输出片段后断开：即使错误本身可转移，也原样报错，不把服务器的回答接在后面。"""
    local, server = _pair()
    stub = net({LOCAL: _sse("本机前半", then=httpx.ConnectError("peer vanished")), SERVER: _NOT_CALLED})
    received: list[str] = []
    with pytest.raises(LLMRuntimeError) as caught:
        async for chunk in llm_route.route_chat_stream([local, server], MESSAGES):
            received.append(chunk)
    assert received == ["本机前半"]
    assert caught.value.failover is True  # 错误类别本身可转移，只因已输出才不转移
    assert stub.models() == ["Qwen3.5"]


# ---------------------------------------------------------------------------
# 熔断按整条路由（ADR-ROUTE-007）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breaker_records_success_when_the_server_covers_for_local(net, monkeypatch):
    from app.services import llm_client

    local, server = _pair()
    net({LOCAL: httpx.ConnectError("refused"), SERVER: _ok("兜底成功")})
    failures: list[int] = []
    original = llm_client._breaker.record_failure

    def spy() -> None:
        failures.append(1)
        original()

    monkeypatch.setattr(llm_client._breaker, "record_failure", spy)
    for _ in range(llm_client._CIRCUIT_FAILURE_THRESHOLD + 1):
        llm_route.reset_route_health()  # 每次都真实经历一次本机失败
        result = await llm_client._sync_completion({"messages": MESSAGES}, route=[local, server])
        assert result == "兜底成功"
    # 只看最终计数不够：成功会清零计数，按候选计失败的实现照样「最终为 0」
    assert failures == []
    assert llm_client._breaker.is_open is False


@pytest.mark.asyncio
async def test_breaker_opens_only_when_every_candidate_fails(net):
    from app.services import llm_client

    local, server = _pair()
    stub = net({LOCAL: httpx.ConnectError("refused"), SERVER: httpx.Response(503)})
    for _ in range(llm_client._CIRCUIT_FAILURE_THRESHOLD):
        result = await llm_client._sync_completion({"messages": MESSAGES}, route=[local, server])
        assert result.startswith("[LLM 调用失败")
    assert llm_client._breaker.is_open is True
    calls = len(stub.seen)
    blocked = await llm_client._sync_completion({"messages": MESSAGES}, route=[local, server])
    assert blocked == "[LLM 服务熔断中，请稍后重试]"
    assert len(stub.seen) == calls
    # 路由组成变化（如管理员启用了新模型）⇒ 熔断器按新路由重新计数
    net({SERVER: _ok("新路由")})
    assert await llm_client._sync_completion({"messages": MESSAGES}, route=[server]) == "新路由"


@pytest.mark.asyncio
async def test_caller_bugs_do_not_trip_the_breaker(net):
    from app.services import llm_client

    local, _ = _pair()
    net({LOCAL: _ok("不会走到这里")})
    for _ in range(llm_client._CIRCUIT_FAILURE_THRESHOLD + 2):
        result = await llm_client._sync_completion({"messages": ["不是消息字典"]}, route=[local])
        assert result == "[LLM 调用失败，请稍后重试]"
    assert llm_client._breaker.is_open is False
    assert llm_client._breaker._failure_count == 0


# ---------------------------------------------------------------------------
# 启用唯一索引语义（ADR-ROUTE-002；ORM 与 V197 同一组索引）
# ---------------------------------------------------------------------------


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(AIModelConfig.__table__.create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def _row(model_type: AIModelType, deployment: str, *, capability=None, active=True, deleted=False):
    return AIModelConfig(
        model_name=f"m-{uuid4().hex[:8]}", model_type=model_type,
        provider=AIProvider.paddleocr if model_type == AIModelType.ocr else AIProvider.custom,
        ocr_capability=capability, deployment=deployment, is_active=active, is_deleted=deleted,
    )


async def _accepts(factory, *rows) -> bool:
    async with factory() as db:
        db.add_all(rows)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return False
    return True


CHAT, EMBED, OCR = AIModelType.chat, AIModelType.embedding, AIModelType.ocr


@pytest.mark.asyncio
@pytest.mark.parametrize(("rows", "allowed"), [
    ([(CHAT, "local"), (CHAT, "server")], True),
    ([(CHAT, "local"), (CHAT, "local")], False),
    ([(CHAT, "server"), (CHAT, "server")], False),
    ([(EMBED, "local"), (EMBED, "server")], False),  # 向量只一条：不跨模型兜底
    ([(OCR, "local", "ocr"), (OCR, "server", "ocr")], True),
    ([(OCR, "server", "ocr"), (OCR, "server", "layout_parsing")], True),
    ([(OCR, "server", "layout_parsing"), (OCR, "server", "layout_parsing")], False),
    ([(CHAT, "server"), (EMBED, "server"), (OCR, "server", "ocr")], True),
])
async def test_active_route_uniqueness(session_factory, rows, allowed):
    built = [_row(spec[0], spec[1], capability=spec[2] if len(spec) > 2 else None) for spec in rows]
    assert await _accepts(session_factory, *built) is allowed


@pytest.mark.asyncio
async def test_inactive_and_deleted_rows_do_not_occupy_a_slot(session_factory):
    assert await _accepts(
        session_factory,
        _row(CHAT, "server"),
        _row(CHAT, "server", active=False),
        _row(CHAT, "server", deleted=True),
        _row(EMBED, "local"),
        _row(EMBED, "server", active=False),
    )


@pytest.mark.asyncio
async def test_resolve_route_orders_enabled_rows_and_falls_back_to_env(session_factory):
    from app.services.llm_runtime import resolve_route

    async with session_factory() as db:
        implicit = await resolve_route(db, AIModelType.chat)
        assert len(implicit) == 1 and implicit[0].implicit and implicit[0].config.source == "environment"
        db.add_all([
            AIModelConfig(
                model_name="qwen3.8", model_type=CHAT, provider=AIProvider.custom,
                endpoint_url="https://ai.gt-china.com.cn:10010/v1", deployment="server", is_active=True,
            ),
            AIModelConfig(
                model_name="Qwen3.5", model_type=CHAT, provider=AIProvider.openai_compatible,
                endpoint_url=LOCAL, deployment="local", is_active=True,
            ),
        ])
        await db.commit()
        route = await resolve_route(db, AIModelType.chat, requested_model="no-such-model")
    assert [(c.deployment, c.model_name, c.implicit) for c in route] == [
        ("local", "Qwen3.5", False), ("server", "qwen3.8", False),
    ]
    assert [c.config.source for c in route] == ["database", "database"]
