"""vLLM / httpx 链路 3 bug 修复 — 单元测试

Property 1: 所有 httpx client 创建必须 trust_env=False + mounts={}
Property 2: chat_template_kwargs 在 payload 顶层（非 extra_body 内）
Property 3: _sync_completion 返回值永远是非 None 字符串
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Property 1: httpx 系统代理绕过
# ---------------------------------------------------------------------------


class TestHttpxTrustEnvFalse:
    """Bug 1: 所有 httpx.AsyncClient 必须 trust_env=False, mounts={}"""

    @pytest.mark.asyncio
    async def test_llm_client_sync_completion_trust_env(self):
        """llm_client._sync_completion 创建的 client 必须绕过系统代理"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from app.services.llm_client import _sync_completion

            await _sync_completion({"model": "test", "messages": [], "stream": False})

            _, kwargs = mock_client_cls.call_args
            assert kwargs.get("trust_env") is False, "trust_env must be False"
            assert kwargs.get("mounts") == {}, "mounts must be empty dict"

    @pytest.mark.asyncio
    async def test_llm_client_stream_completion_trust_env(self):
        """llm_client._stream_completion 创建的 client 必须绕过系统代理"""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            mock_stream_ctx = AsyncMock()
            mock_resp = AsyncMock()
            mock_resp.aiter_lines = AsyncMock(return_value=iter(["data: [DONE]"]))
            mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_client.stream = MagicMock(return_value=mock_stream_ctx)
            mock_client_cls.return_value = mock_client

            from app.services.llm_client import _stream_completion

            gen = _stream_completion({"model": "test", "messages": [], "stream": True})
            # Consume generator
            chunks = []
            async for chunk in gen:
                chunks.append(chunk)

            _, kwargs = mock_client_cls.call_args
            assert kwargs.get("trust_env") is False
            assert kwargs.get("mounts") == {}

    @pytest.mark.asyncio
    async def test_ai_service_get_ollama_client_trust_env(self):
        """ai_service._get_ollama_client 必须绕过系统代理"""
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            from app.services.ai_service import _get_ollama_client

            await _get_ollama_client()
            _, kwargs = mock_cls.call_args
            assert kwargs.get("trust_env") is False
            assert kwargs.get("mounts") == {}

    @pytest.mark.asyncio
    async def test_ai_service_get_llm_client_trust_env(self):
        """ai_service._get_llm_client 必须绕过系统代理"""
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            from app.services.ai_service import _get_llm_client

            await _get_llm_client()
            _, kwargs = mock_cls.call_args
            assert kwargs.get("trust_env") is False
            assert kwargs.get("mounts") == {}

    @pytest.mark.asyncio
    async def test_ai_service_get_chromadb_client_trust_env(self):
        """ai_service._get_chromadb_client 必须绕过系统代理"""
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            from app.services.ai_service import _get_chromadb_client

            await _get_chromadb_client()
            _, kwargs = mock_cls.call_args
            assert kwargs.get("trust_env") is False
            assert kwargs.get("mounts") == {}

    @pytest.mark.asyncio
    async def test_availability_fallback_check_llm_trust_env(self):
        """availability_fallback_service.check_llm_available 必须绕过系统代理"""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            from app.services.availability_fallback_service import AvailabilityFallbackService

            await AvailabilityFallbackService.check_llm_available()
            _, kwargs = mock_cls.call_args
            assert kwargs.get("trust_env") is False
            assert kwargs.get("mounts") == {}


# ---------------------------------------------------------------------------
# Property 2: chat_template_kwargs 在 payload 顶层
# ---------------------------------------------------------------------------


class TestChatTemplateKwargsTopLevel:
    """Bug 2: chat_template_kwargs 必须在 payload 顶层，非 extra_body 内"""

    @pytest.mark.asyncio
    async def test_payload_has_chat_template_kwargs_top_level(self):
        """chat_completion 构建的 payload 中 chat_template_kwargs 在顶层"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from app.services.llm_client import chat_completion

            await chat_completion(
                messages=[{"role": "user", "content": "test"}],
                stream=False,
            )

            # 获取 post 调用时传入的 json payload
            call_kwargs = mock_client.post.call_args[1]
            payload = call_kwargs["json"]

            # chat_template_kwargs 必须在顶层
            assert "chat_template_kwargs" in payload, (
                "chat_template_kwargs must be a top-level key in payload"
            )
            assert "enable_thinking" in payload["chat_template_kwargs"]

            # extra_body 不应存在
            assert "extra_body" not in payload, (
                "extra_body should not exist in payload"
            )

    @pytest.mark.asyncio
    async def test_payload_chat_template_kwargs_value_correct(self):
        """chat_template_kwargs.enable_thinking 值来自 settings"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            with patch("app.services.llm_client.settings") as mock_settings:
                mock_settings.LLM_BASE_URL = "http://localhost:8100/v1"
                mock_settings.LLM_API_KEY = "test"
                mock_settings.DEFAULT_CHAT_MODEL = "test-model"
                mock_settings.LLM_ENABLE_THINKING = False

                from importlib import reload
                import app.services.llm_client as llm_mod

                await llm_mod.chat_completion(
                    messages=[{"role": "user", "content": "test"}],
                    stream=False,
                )

                payload = mock_client.post.call_args[1]["json"]
                assert payload["chat_template_kwargs"]["enable_thinking"] is False


# ---------------------------------------------------------------------------
# Property 3: _sync_completion 返回值永远是非 None 字符串
# ---------------------------------------------------------------------------


class TestFinishReasonLengthHandling:
    """Bug 3: finish_reason=length + content=None 返回中文提示，禁止 fallback reasoning"""

    @pytest.mark.asyncio
    async def test_finish_reason_length_content_none_returns_warning(self):
        """finish_reason=length + content=None → 返回中文提示字符串"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": None, "reasoning": "some thinking..."},
                "finish_reason": "length",
            }]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from app.services.llm_client import _sync_completion

            result = await _sync_completion({"model": "t", "messages": []})

            assert result is not None, "Must not return None"
            assert isinstance(result, str)
            assert "token" in result or "限制" in result, (
                "Should mention token limit in Chinese"
            )
            # 禁止返回 reasoning 内容
            assert "some thinking" not in result

    @pytest.mark.asyncio
    async def test_content_none_other_reason_returns_generic_warning(self):
        """content=None + finish_reason != length → 返回通用提示"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": None, "reasoning": "thinking"},
                "finish_reason": "stop",
            }]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from app.services.llm_client import _sync_completion

            result = await _sync_completion({"model": "t", "messages": []})

            assert result is not None
            assert isinstance(result, str)
            assert "thinking" not in result, "Must not fallback to reasoning"

    @pytest.mark.asyncio
    async def test_normal_response_returns_content(self):
        """正常响应（content 有值）→ 返回 content 原值"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "正常回复内容"},
                "finish_reason": "stop",
            }]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from app.services.llm_client import _sync_completion

            result = await _sync_completion({"model": "t", "messages": []})

            assert result == "正常回复内容"

    @pytest.mark.asyncio
    async def test_content_none_with_reasoning_never_returns_reasoning(self):
        """content=None + reasoning 有值 → 绝不返回 reasoning 字段内容"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": None,
                    "reasoning": "这是中间思考过程，不应作为最终答案",
                },
                "finish_reason": "length",
            }]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from app.services.llm_client import _sync_completion

            result = await _sync_completion({"model": "t", "messages": []})

            assert "中间思考过程" not in result
            assert "不应作为最终答案" not in result
