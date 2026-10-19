"""统一 LLM transport 回归：代理隔离、Qwen 专有参数、空输出处理。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.ai_models import AIModelType, AIProvider
from app.services.llm_provider_registry import provider_profile
from app.services.llm_runtime import ResolvedLLMConfig, build_chat_payload


def _config(*, endpoint="http://localhost:8100/v1", model="Qwen3.5-27B"):
    return ResolvedLLMConfig(
        model_name=model,
        model_type=AIModelType.chat,
        provider=AIProvider.openai_compatible,
        endpoint_url=endpoint,
        api_key=None,
        profile=provider_profile(AIProvider.openai_compatible),
        source="environment",
    )


class TestHttpxTrustEnvFalse:
    @pytest.mark.asyncio
    async def test_runtime_client_disables_proxy_and_redirects(self):
        from app.services.llm_endpoint_policy import SafeEndpoint
        from app.services.llm_runtime import build_runtime_client

        with patch(
            "app.services.llm_runtime.resolve_endpoint",
            new=AsyncMock(return_value=SafeEndpoint("http://localhost:8100/v1", "localhost")),
        ), patch("app.services.llm_runtime.httpx.AsyncClient") as client_cls:
            client_cls.return_value = MagicMock()
            await build_runtime_client(_config(), timeout=30.0)
            _, kwargs = client_cls.call_args
            assert kwargs["trust_env"] is False
            assert kwargs["mounts"] == {}
            assert kwargs["follow_redirects"] is False
            # 系统 DNS 正常时不改传输层。
            assert kwargs["transport"] is None

    @pytest.mark.asyncio
    async def test_ai_service_legacy_helpers_still_disable_proxy(self):
        from app.services.ai_service import (
            _get_chromadb_client,
            _get_llm_client,
            _get_ollama_client,
        )

        for factory in (_get_llm_client, _get_ollama_client, _get_chromadb_client):
            with patch("httpx.AsyncClient") as client_cls:
                client_cls.return_value = MagicMock()
                await factory()
                _, kwargs = client_cls.call_args
                assert kwargs["trust_env"] is False
                assert kwargs["mounts"] == {}

    @pytest.mark.asyncio
    async def test_availability_fallback_check_llm_trust_env(self):
        response = MagicMock(status_code=200)
        with patch("httpx.AsyncClient") as client_cls:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.get = AsyncMock(return_value=response)
            client_cls.return_value = client
            from app.services.availability_fallback_service import AvailabilityFallbackService
            await AvailabilityFallbackService.check_llm_available()
            _, kwargs = client_cls.call_args
            assert kwargs["trust_env"] is False
            assert kwargs["mounts"] == {}


class TestChatTemplateKwargsTopLevel:
    def test_local_qwen_gets_top_level_thinking_flag(self):
        payload = build_chat_payload(
            _config(), [{"role": "user", "content": "test"}],
            temperature=0.3, max_tokens=100, stream=False, enable_thinking=False,
        )
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert "extra_body" not in payload

    def test_external_provider_never_gets_qwen_private_flag(self):
        config = ResolvedLLMConfig(
            model_name="qwen-plus", model_type=AIModelType.chat,
            provider=AIProvider.qwen,
            endpoint_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="secret", profile=provider_profile(AIProvider.qwen), source="database",
        )
        payload = build_chat_payload(
            config, [{"role": "user", "content": "test"}],
            temperature=0.3, max_tokens=100, stream=False,
        )
        assert "chat_template_kwargs" not in payload


def _client_for_response(response: httpx.Response):
    async def factory(config, *, timeout, connect_timeout=10.0):
        return httpx.AsyncClient(
            base_url=config.endpoint_url.rstrip("/") + "/",
            transport=httpx.MockTransport(lambda request: response),
        )
    return factory


class TestFinishReasonLengthHandling:
    @pytest.mark.asyncio
    async def test_finish_reason_length_returns_warning_not_reasoning(self, monkeypatch):
        import app.services.llm_client as client

        response = httpx.Response(200, json={
            "choices": [{
                "message": {"content": None, "reasoning_content": "private thought"},
                "finish_reason": "length",
            }],
        })
        monkeypatch.setattr(
            "app.services.llm_runtime.build_runtime_client",
            _client_for_response(response),
        )
        result = await client._sync_completion(
            {"messages": [], "max_tokens": 10}, config=_config()
        )
        assert isinstance(result, str)
        assert "token" in result or "限制" in result
        assert "private thought" not in result

    @pytest.mark.asyncio
    async def test_empty_content_returns_generic_warning(self, monkeypatch):
        import app.services.llm_client as client

        response = httpx.Response(200, json={
            "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
        })
        monkeypatch.setattr(
            "app.services.llm_runtime.build_runtime_client",
            _client_for_response(response),
        )
        result = await client._sync_completion(
            {"messages": [], "max_tokens": 10}, config=_config()
        )
        assert "未返回有效内容" in result

    @pytest.mark.asyncio
    async def test_normal_response_returns_content(self, monkeypatch):
        import app.services.llm_client as client

        response = httpx.Response(200, json={
            "choices": [{"message": {"content": "正常回复内容"}, "finish_reason": "stop"}],
        })
        monkeypatch.setattr(
            "app.services.llm_runtime.build_runtime_client",
            _client_for_response(response),
        )
        result = await client._sync_completion(
            {"messages": [], "max_tokens": 10}, config=_config()
        )
        assert result == "正常回复内容"
