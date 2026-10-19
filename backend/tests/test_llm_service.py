"""Tests for LLMService — 经平台本机优先路由调用 + 超时降级 + 错误处理

V197 起 LLMService 不再自建 httpx 直连 `.env` 端点，而是走 ``llm_runtime.resolve_route``
的候选与同一 transport；这里用 MockTransport 替换出站，验证结构化响应契约不变。

Requirements: F2.1, F2.4
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.ai_models import AIModelType, AIProvider
from app.services.llm_provider_registry import provider_profile
from app.services.llm_route import reset_route_health
from app.services.llm_runtime import ResolvedLLMConfig, RouteCandidate
from app.services.llm_service import LLMResponse, LLMService

LOCAL = "http://localhost:8100/v1"
SERVER = "https://ai.example.test/v1"


def _candidate(model: str, endpoint: str) -> RouteCandidate:
    provider = AIProvider.openai_compatible if "localhost" in endpoint else AIProvider.custom
    config = ResolvedLLMConfig(
        model_name=model, model_type=AIModelType.chat, provider=provider,
        endpoint_url=endpoint, api_key=None if "localhost" in endpoint else "k",
        profile=provider_profile(provider), source="database",
        deployment="local" if "localhost" in endpoint else "server",
    )
    return RouteCandidate(model, config.deployment, None, config)


def _success(content: str, usage: dict | None = None) -> dict:
    body: dict = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        body["usage"] = usage
    return body


@pytest.fixture(autouse=True)
def _clean_route_health():
    reset_route_health()
    yield
    reset_route_health()


def _transport(handlers: dict[str, object], seen: list[httpx.Request] | None = None):
    """按端点前缀分派：值为 httpx.Response 或要抛出的异常实例。"""

    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        for prefix, outcome in handlers.items():
            if str(request.url).startswith(prefix):
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise AssertionError(f"unexpected request {request.url}")

    async def factory(config, *, timeout, connect_timeout=10.0):
        return httpx.AsyncClient(
            base_url=config.endpoint_url.rstrip("/") + "/",
            transport=httpx.MockTransport(handle),
        )

    return factory


async def _generate(route, handlers, *, seen=None, **kwargs) -> LLMResponse:
    svc = LLMService()
    with patch.object(LLMService, "_route", new=AsyncMock(return_value=route)), patch(
        "app.services.llm_runtime.build_runtime_client", _transport(handlers, seen)
    ):
        return await svc.generate(
            system_prompt=kwargs.pop("system_prompt", "你是审计师"),
            user_prompt=kwargs.pop("user_prompt", "分析费用异常"),
            **kwargs,
        )


# --- Tests: Successful calls ---


@pytest.mark.asyncio
async def test_generate_success():
    """调用成功时返回 content + tokens_used + is_stub=False"""
    result = await _generate(
        [_candidate("local-model", LOCAL)],
        {LOCAL: httpx.Response(200, json=_success("## 异常分析\n销售费用同比增长 45%", {"total_tokens": 230}))},
    )
    assert isinstance(result, LLMResponse)
    assert result.is_stub is False
    assert "异常分析" in result.content
    assert result.tokens_used == 230
    assert result.error is None
    assert result.duration_ms > 0


@pytest.mark.asyncio
async def test_generate_success_no_usage():
    """响应缺少 usage 字段时 tokens_used 默认为 0"""
    result = await _generate(
        [_candidate("local-model", LOCAL)],
        {LOCAL: httpx.Response(200, json=_success("分析结果：费用正常。"))},
    )
    assert result.is_stub is False
    assert result.content == "分析结果：费用正常。"
    assert result.tokens_used == 0


@pytest.mark.asyncio
async def test_generate_custom_params():
    """temperature / max_tokens / 消息结构 / 候选自身的模型名正确传递"""
    seen: list[httpx.Request] = []
    result = await _generate(
        [_candidate("local-model", LOCAL)],
        {LOCAL: httpx.Response(200, json=_success("ok"))},
        seen=seen,
        system_prompt="系统提示", user_prompt="用户提示", temperature=0.7, max_tokens=500,
    )
    assert result.is_stub is False
    body = json.loads(seen[0].content)
    assert body["temperature"] == 0.7
    assert body["max_tokens"] == 500
    assert body["model"] == "local-model"
    assert body["messages"] == [
        {"role": "system", "content": "系统提示"},
        {"role": "user", "content": "用户提示"},
    ]


# --- Tests: 本机优先路由 ---


@pytest.mark.asyncio
async def test_local_unreachable_falls_back_to_server():
    """本机连不上 ⇒ 同一次调用改用服务器候选，服务器的模型名与用量生效。"""
    seen: list[httpx.Request] = []
    result = await _generate(
        [_candidate("local-model", LOCAL), _candidate("qwen3.8", SERVER)],
        {
            LOCAL: httpx.ConnectError("Connection refused"),
            SERVER: httpx.Response(200, json=_success("服务器回答", {"total_tokens": 42})),
        },
        seen=seen,
    )
    assert result.is_stub is False
    assert result.content == "服务器回答"
    assert result.tokens_used == 42
    assert [json.loads(r.content)["model"] for r in seen] == ["local-model", "qwen3.8"]


@pytest.mark.asyncio
async def test_local_read_timeout_does_not_fall_back():
    """读取超时说明请求已被接收：不换服务器重复执行，直接降级。"""
    seen: list[httpx.Request] = []
    result = await _generate(
        [_candidate("local-model", LOCAL), _candidate("qwen3.8", SERVER)],
        {
            LOCAL: httpx.ReadTimeout("read timed out"),
            SERVER: httpx.Response(200, json=_success("不该被调用")),
        },
        seen=seen,
    )
    assert result.is_stub is True
    assert "timeout" in result.error.lower()
    assert len(seen) == 1


# --- Tests: Timeout degradation (F2.4) ---


@pytest.mark.asyncio
async def test_generate_timeout_degradation():
    """超时后降级返回 is_stub=True + error 描述"""
    result = await _generate(
        [_candidate("local-model", LOCAL)],
        {LOCAL: httpx.ReadTimeout("Connection timed out")},
        timeout=30.0,
    )
    assert result.is_stub is True
    assert result.content is None
    assert result.tokens_used == 0
    assert "timeout" in result.error.lower()
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_generate_connect_timeout():
    """连接超时也降级"""
    result = await _generate(
        [_candidate("local-model", LOCAL)],
        {LOCAL: httpx.ConnectTimeout("Failed to connect")},
    )
    assert result.is_stub is True
    assert result.content is None
    assert "timeout" in result.error.lower()


# --- Tests: HTTP error handling ---


@pytest.mark.asyncio
async def test_generate_http_500_error():
    """返回 500 时降级，错误里不回传上游正文"""
    result = await _generate(
        [_candidate("local-model", LOCAL)],
        {LOCAL: httpx.Response(500, text="upstream-secret-body")},
    )
    assert result.is_stub is True
    assert result.content is None
    assert "500" in result.error
    assert "upstream-secret-body" not in result.error


@pytest.mark.asyncio
async def test_generate_http_429_rate_limit():
    """返回 429 限流时降级"""
    result = await _generate(
        [_candidate("local-model", LOCAL)],
        {LOCAL: httpx.Response(429, text="Rate limit exceeded")},
    )
    assert result.is_stub is True
    assert "provider_rate_limited" in result.error


# --- Tests: Connection errors ---


@pytest.mark.asyncio
async def test_generate_connection_refused():
    """本机未启动且没有服务器候选时降级"""
    result = await _generate(
        [_candidate("local-model", LOCAL)],
        {LOCAL: httpx.ConnectError("Connection refused")},
    )
    assert result.is_stub is True
    assert result.content is None
    assert "provider_unreachable" in result.error


# --- Tests: LLMResponse dataclass ---


def test_llm_response_defaults():
    """LLMResponse 默认值正确"""
    resp = LLMResponse()
    assert resp.content is None
    assert resp.tokens_used == 0
    assert resp.is_stub is False
    assert resp.error is None
    assert resp.duration_ms == 0.0


def test_llm_response_stub():
    """LLMResponse stub 模式"""
    resp = LLMResponse(content=None, tokens_used=0, is_stub=True, error="timeout")
    assert resp.is_stub is True
    assert resp.error == "timeout"


# --- Tests: LLMService initialization ---


def test_llm_service_default_config():
    """默认不点名模型：完全按路由选择"""
    assert LLMService().model is None


def test_llm_service_model_is_only_a_preference():
    """点名模型只作优先提示，不再接受任意 base_url（不得绕开路由与出站策略）"""
    assert LLMService(model="custom-model").model == "custom-model"
    with pytest.raises(TypeError):
        LLMService(base_url="http://custom:9000/v1")  # type: ignore[call-arg]


# --- Tests: Duration logging ---


@pytest.mark.asyncio
async def test_generate_records_duration():
    """调用记录耗时（duration_ms > 0）"""
    result = await _generate(
        [_candidate("local-model", LOCAL)],
        {LOCAL: httpx.Response(200, json=_success("ok", {"total_tokens": 1}))},
    )
    assert result.duration_ms > 0


@pytest.mark.asyncio
async def test_generate_records_duration_on_failure():
    """失败时也记录耗时"""
    result = await _generate(
        [_candidate("local-model", LOCAL)],
        {LOCAL: httpx.ConnectError("refused")},
    )
    assert result.duration_ms >= 0
    assert result.is_stub is True
