"""DSH 模型桥与环回转发端点（spec dsh-kb-ocr-local-first-routing Task 5，ADR-DKR-001~003）。"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.models.ai_models import AIModelType, AIProvider
from app.routers import dsh_model_forward as F
from app.services.ai_chat import dsh_model_bridge as B
from app.services.ai_chat.engine import EngineFailure
from app.services.ai_chat.run_contract import ChatErrorCode
from app.services.llm_provider_registry import provider_profile
from app.services.llm_route import is_cooling, mark_unavailable, reset_route_health
from app.services.llm_runtime import LLMRuntimeError, ResolvedLLMConfig, RouteCandidate

LOCAL = ResolvedLLMConfig(
    model_name="Kbenkhaled/Qwen3.5-27B-NVFP4", model_type=AIModelType.chat,
    provider=AIProvider.openai_compatible, endpoint_url="http://localhost:8100/v1", api_key=None,
    profile=provider_profile(AIProvider.openai_compatible), source="database", model_id=uuid4(),
    deployment="local",
)
SERVER = ResolvedLLMConfig(
    model_name="qwen3.8", model_type=AIModelType.chat, provider=AIProvider.custom,
    endpoint_url="https://ai.gt-china.com.cn:10010/v1", api_key="sk-enterprise",
    profile=provider_profile(AIProvider.custom), source="database", model_id=uuid4(),
    reasoning_effort="low", deployment="server",
)
PUBLIC = ResolvedLLMConfig(
    model_name="deepseek-v4", model_type=AIModelType.chat, provider=AIProvider.deepseek,
    endpoint_url="https://api.deepseek.com", api_key="sk-public",
    profile=provider_profile(AIProvider.deepseek), source="database", model_id=uuid4(),
    deployment="server",
)


def _cand(config: ResolvedLLMConfig) -> RouteCandidate:
    return RouteCandidate(config.model_name, config.deployment, config.model_id, config)


@pytest.fixture(autouse=True)
def _clean_health():
    reset_route_health()
    yield
    reset_route_health()


# ---------------------------------------------------------------------------
# 令牌
# ---------------------------------------------------------------------------


def test_token_roundtrip_binds_run_and_candidate() -> None:
    run_id = uuid4()
    claims = B.verify_token(B.issue_token(run_id, SERVER.identity, ttl_seconds=60))
    assert claims.run_id == run_id and claims.identity == SERVER.identity
    assert claims.expires_at > time.time()


@pytest.mark.parametrize("mangle", [
    lambda t: t[:-1] + ("0" if t[-1] != "0" else "1"),       # 改签名
    lambda t: "e" + t,                                         # 改载荷
    lambda t: t.split(".")[0],                                 # 去掉签名
    lambda t: "",
    lambda t: "not-a-token",
])
def test_tampered_token_rejected(mangle) -> None:
    token = B.issue_token(uuid4(), LOCAL.identity, ttl_seconds=60)
    with pytest.raises(B.DshTokenError):
        B.verify_token(mangle(token))


def test_expired_token_rejected() -> None:
    token = B.issue_token(uuid4(), LOCAL.identity, ttl_seconds=1)
    with patch.object(B.time, "time", return_value=time.time() + 5):
        with pytest.raises(B.DshTokenError, match="过期"):
            B.verify_token(token)


def test_token_key_comes_from_platform_secret(monkeypatch) -> None:
    """签名密钥派生自 JWT_SECRET_KEY：换一个平台密钥签的令牌校验不过；密钥缺失时拒绝签发（不落回固定常量）。"""
    monkeypatch.setattr(B.settings, "JWT_SECRET_KEY", "platform-secret-a")
    token = B.issue_token(uuid4(), SERVER.identity, ttl_seconds=60)
    assert B.verify_token(token).identity == SERVER.identity
    monkeypatch.setattr(B.settings, "JWT_SECRET_KEY", "platform-secret-b")
    with pytest.raises(B.DshTokenError, match="签名无效"):
        B.verify_token(token)
    monkeypatch.setattr(B.settings, "JWT_SECRET_KEY", "")
    with pytest.raises(B.DshTokenError, match="JWT_SECRET_KEY"):
        B.issue_token(uuid4(), SERVER.identity, ttl_seconds=60)


# ---------------------------------------------------------------------------
# 请求改写与上游端点策略
# ---------------------------------------------------------------------------

_DSH_BODY = {
    "model": "whatever-dsh-sent",
    "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "问"}],
    "stream": True,
    "stream_options": {"include_usage": True},
    "thinking": {"type": "disabled"},
    "reasoning_effort": "high",
    # vendor 适配器可能带的思考 / 透传字段：一律丢弃，按候选重写
    "chat_template_kwargs": {"enable_thinking": True},
    "extra_body": {"reasoning_effort": "max"},
    "tools": [{"type": "function", "function": {"name": "mcp__audit__wp_list", "parameters": {}}}],
    "max_tokens": 8192,
}


def test_rewrite_forces_model_and_applies_candidate_reasoning() -> None:
    server = B.rewrite_request(dict(_DSH_BODY), SERVER)
    assert server["model"] == "qwen3.8"
    assert not {"thinking", "chat_template_kwargs", "extra_body"} & set(server)
    # 企业网关只收 low / medium / xhigh：按候选配置重写，DSH 发来的 high 不得透传（传 high 网关返回 400）
    assert server["reasoning_effort"] == "low"
    for key in ("messages", "stream", "stream_options", "tools", "max_tokens"):
        assert server[key] == _DSH_BODY[key]

    local = B.rewrite_request(dict(_DSH_BODY), LOCAL)
    assert local["model"] == LOCAL.model_name
    assert not {"reasoning_effort", "thinking", "extra_body"} & set(local)
    assert local["chat_template_kwargs"] == {"enable_thinking": False}  # DSH 发来的 True 被候选配置覆盖


@pytest.mark.parametrize("endpoint,allowed", [
    ("https://ai.gt-china.com.cn:10010/v1", True),   # 企业预设（受信清单）
    ("http://localhost:8100/v1", True),
    ("http://127.0.0.1:8100/v1", True),
    ("http://10.1.2.3:8000/v1", True),
    ("https://api.deepseek.com", False),            # 公网官方 API：native 可用，DSH 不给用
    ("https://ai.gt-china.com.cn:10011/v1", False),  # 端口不同 ≠ 预设
    ("https://evil.example.com/v1", False),
    ("", False),
])
def test_dsh_upstream_policy(endpoint: str, allowed: bool) -> None:
    assert (not B.validate_dsh_upstream(endpoint)) is allowed


def test_dsh_upstream_honours_env_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(B.settings, "LLM_ENDPOINT_ALLOWLIST", "https://llm.corp.example:8443/v1", raising=False)
    from app.services import llm_endpoint_policy

    monkeypatch.setattr(llm_endpoint_policy.settings, "LLM_ENDPOINT_ALLOWLIST", "https://llm.corp.example:8443/v1")
    assert not B.validate_dsh_upstream("https://llm.corp.example:8443/v1")


# ---------------------------------------------------------------------------
# 选候选（执行前探测，全程不换）
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _no_db():
    yield object()


def _patch_route(route: list[RouteCandidate], probe: dict[str, tuple[bool, str]], windows=None):
    async def _resolve(_db, _kind, **_kw):
        assert _kind == AIModelType.chat
        return route

    async def _probe(config):
        return probe[config.identity]

    async def _windows(_cands):
        return windows or {}

    return (
        patch.object(B, "async_session", _no_db),
        patch.object(B, "resolve_route", _resolve),
        patch("app.services.model_route_status.probe_chat_candidate", _probe),
        patch.object(B, "_context_windows", _windows),
    )


async def _select(route, probe, windows=None):
    p1, p2, p3, p4 = _patch_route(route, probe, windows)
    with p1, p2, p3, p4:
        return await B.select_run_candidate()


@pytest.mark.asyncio
async def test_local_first_when_local_available() -> None:
    picked = await _select([_cand(LOCAL), _cand(SERVER)], {LOCAL.identity: (True, "可用"), SERVER.identity: (True, "可用")})
    assert picked.config is LOCAL and picked.notes == ()


@pytest.mark.asyncio
async def test_server_fallback_when_local_unavailable() -> None:
    picked = await _select(
        [_cand(LOCAL), _cand(SERVER)],
        {LOCAL.identity: (False, "连接被拒绝（端口未监听）"), SERVER.identity: (True, "可用")},
        windows={SERVER.model_id: 262144},
    )
    assert picked.config is SERVER and picked.deployment == "server"
    assert picked.context_window == 262144 and picked.max_output_tokens == 8192
    assert any("连接被拒绝" in note for note in picked.notes)


@pytest.mark.asyncio
async def test_cooling_local_is_skipped_without_probe() -> None:
    mark_unavailable(LOCAL.identity, "刚失败过")
    picked = await _select([_cand(LOCAL), _cand(SERVER)], {SERVER.identity: (True, "可用")})
    assert picked.config is SERVER
    assert any("冷却中" in note for note in picked.notes)


@pytest.mark.asyncio
async def test_public_endpoint_never_selected_for_dsh() -> None:
    picked = await _select([_cand(PUBLIC), _cand(LOCAL)], {LOCAL.identity: (True, "可用")})
    assert picked.config is LOCAL
    with pytest.raises(EngineFailure) as exc:
        await _select([_cand(PUBLIC)], {})
    assert exc.value.code == ChatErrorCode.local_only_violation


@pytest.mark.asyncio
async def test_all_unavailable_lists_every_reason() -> None:
    invalid = RouteCandidate("broken", "server", uuid4(), None, LLMRuntimeError("api_key_required", "该提供商尚未配置 API Key"))
    with pytest.raises(EngineFailure) as exc:
        await _select(
            [_cand(LOCAL), invalid, _cand(SERVER)],
            {LOCAL.identity: (False, "本机挂了"), SERVER.identity: (False, "鉴权失败，请检查 API Key")},
        )
    assert exc.value.code == ChatErrorCode.engine_unavailable
    for reason in ("本机挂了", "尚未配置 API Key", "鉴权失败"):
        assert reason in exc.value.detail


# ---------------------------------------------------------------------------
# 环回转发端点
# ---------------------------------------------------------------------------


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(F.router)
    return app


def _client(host: str = "127.0.0.1") -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=_app(), client=(host, 50123))
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:9980")


_URL = "/api/ai-chat/dsh-llm/v1/chat/completions"


def test_forward_prefix_matches_bridge_constant() -> None:
    """路由前缀写成字面量（鉴权基线扫描器只认字面量），而 DSH 子进程的 baseURL 由 ``FORWARD_PATH`` 拼出
    ⇒ 两者必须逐字相等，否则子进程的模型请求全部 404。"""
    assert F.router.prefix == B.FORWARD_PATH
    assert B.forward_base_url().endswith(B.FORWARD_PATH)
    assert _URL == F.router.prefix + "/chat/completions"
    assert {route.path for route in F.router.routes} == {_URL}


def _upstream(handler):
    """把 build_runtime_client 换成 MockTransport 客户端（其余转发逻辑全真）。"""

    async def _build(config, *, timeout, connect_timeout=10.0):
        return httpx.AsyncClient(
            base_url=config.endpoint_url.rstrip("/") + "/", transport=httpx.MockTransport(handler)
        )

    return patch.object(F, "build_runtime_client", _build)


def _auth(config: ResolvedLLMConfig) -> dict[str, str]:
    return {"Authorization": f"Bearer {B.issue_token(uuid4(), config.identity, ttl_seconds=60)}"}


def _candidate(config: ResolvedLLMConfig | None):
    async def _for(identity):
        return config if config is not None and config.identity == identity else None

    return patch.object(F, "candidate_for", _for)


@pytest.mark.asyncio
async def test_forward_rejects_non_loopback_requests() -> None:
    async with _client("10.0.0.8") as client:
        assert (await client.post(_URL, json={}, headers=_auth(SERVER))).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("header,value", [
    ("X-Forwarded-For", "203.0.113.9"),
    ("X-Forwarded-Host", "audit.example.com"),
    ("X-Real-IP", "203.0.113.9"),
    ("Forwarded", "for=203.0.113.9"),
])
async def test_forward_rejects_proxied_requests(header: str, value: str) -> None:
    """经反向代理转来的公网请求同样显示为 127.0.0.1，靠代理头区分。"""
    async with _client() as client:
        proxied = {**_auth(SERVER), header: value}
        assert (await client.post(_URL, json={}, headers=proxied)).status_code == 403


@pytest.mark.asyncio
async def test_forward_requires_valid_token() -> None:
    async with _client() as client:
        assert (await client.post(_URL, json={})).status_code == 401
        bad = {"Authorization": "Bearer " + B.issue_token(uuid4(), SERVER.identity, ttl_seconds=60)[:-2] + "00"}
        assert (await client.post(_URL, json={}, headers=bad)).status_code == 401


@pytest.mark.asyncio
async def test_forward_409_when_selected_model_changed() -> None:
    with _candidate(None):
        async with _client() as client:
            response = await client.post(_URL, json=_DSH_BODY, headers=_auth(SERVER))
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_forward_streams_upstream_and_rewrites_body() -> None:
    seen: dict = {}
    sse = b'data: {"choices":[{"delta":{"content":"\xe4\xbd\xa0"}}]}\n\ndata: [DONE]\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen["url"] = str(request.url)
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

    mark_unavailable(SERVER.identity, "上一次 run 失败过")  # 成功转发要把冷却清掉，下一次 run 才会再选它
    with _candidate(SERVER), _upstream(handler):
        async with _client() as client:
            response = await client.post(_URL, json=_DSH_BODY, headers=_auth(SERVER))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.content == sse
    assert seen["url"] == "https://ai.gt-china.com.cn:10010/v1/chat/completions"
    assert seen["body"]["model"] == "qwen3.8" and seen["body"]["reasoning_effort"] == "low"
    assert not {"thinking", "chat_template_kwargs", "extra_body"} & set(seen["body"])
    assert not is_cooling(SERVER.identity)


@pytest.mark.asyncio
async def test_forward_decodes_upstream_content_encoding() -> None:
    """上游压缩的流：回传不带 content-encoding，必须转发解压后的字节（转发原始压缩字节 DSH 收到的是乱码）。"""
    import gzip

    sse = 'data: {"choices":[{"delta":{"content":"好"}}]}\n\ndata: [DONE]\n\n'.encode()

    def handler(_request):
        return httpx.Response(
            200, content=gzip.compress(sse),
            headers={"content-type": "text/event-stream", "content-encoding": "gzip"},
        )

    with _candidate(SERVER), _upstream(handler):
        async with _client() as client:
            response = await client.post(_URL, json=_DSH_BODY, headers=_auth(SERVER))
    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.content == sse


@pytest.mark.asyncio
@pytest.mark.parametrize("status,cools", [
    (500, True), (503, True), (401, True), (403, True), (404, True), (400, False), (422, False), (429, False),
])
async def test_forward_upstream_errors_cool_only_when_candidate_unavailable(status: int, cools: bool) -> None:
    def handler(_request):
        return httpx.Response(status, json={"error": {"message": f"upstream {status}"}})

    with _candidate(SERVER), _upstream(handler):
        async with _client() as client:
            response = await client.post(_URL, json=_DSH_BODY, headers=_auth(SERVER))
    assert response.status_code == status
    assert response.json() == {"error": {"message": f"upstream {status}"}}
    assert is_cooling(SERVER.identity) is cools


@pytest.mark.asyncio
async def test_forward_connect_failure_is_502_and_cools() -> None:
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with _candidate(LOCAL), _upstream(handler):
        async with _client() as client:
            response = await client.post(_URL, json=_DSH_BODY, headers=_auth(LOCAL))
    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream_unavailable"
    assert is_cooling(LOCAL.identity)


@pytest.mark.asyncio
async def test_forward_read_timeout_is_504_without_cooling() -> None:
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with _candidate(SERVER), _upstream(handler):
        async with _client() as client:
            response = await client.post(_URL, json=_DSH_BODY, headers=_auth(SERVER))
    assert response.status_code == 504
    assert not is_cooling(SERVER.identity)
