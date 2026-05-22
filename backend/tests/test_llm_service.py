"""Tests for LLMService — mock vLLM responses + timeout degradation + error handling

Requirements: F2.1, F2.4
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.llm_service import LLMResponse, LLMService


# --- Fixtures ---


@pytest.fixture
def llm_service():
    """Create LLMService instance with test URL"""
    return LLMService(base_url="http://test-vllm:8100/v1", model="test-model")


# --- Mock response helpers ---


def _mock_success_response() -> dict:
    """Standard successful vLLM response"""
    return {
        "choices": [
            {
                "message": {
                    "content": "## 异常分析\n\n销售费用同比增长 45%，主要原因：\n1. 新增渠道推广费用\n2. 人员扩张"
                }
            }
        ],
        "usage": {"prompt_tokens": 150, "completion_tokens": 80, "total_tokens": 230},
    }


def _mock_success_response_no_usage() -> dict:
    """vLLM response without usage field"""
    return {
        "choices": [
            {
                "message": {
                    "content": "分析结果：费用正常。"
                }
            }
        ],
    }


def _make_httpx_response(status_code: int = 200, json_data: dict | None = None, text: str = "") -> httpx.Response:
    """Create a mock httpx.Response"""
    if json_data is not None:
        return httpx.Response(
            status_code=status_code,
            json=json_data,
            request=httpx.Request("POST", "http://test-vllm:8100/v1/chat/completions"),
        )
    return httpx.Response(
        status_code=status_code,
        text=text,
        request=httpx.Request("POST", "http://test-vllm:8100/v1/chat/completions"),
    )


# --- Tests: Successful calls ---


@pytest.mark.asyncio
async def test_generate_success(llm_service):
    """LLM 调用成功时返回 content + tokens_used + is_stub=False"""
    mock_response = _make_httpx_response(200, _mock_success_response())

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await llm_service.generate(
            system_prompt="你是审计师",
            user_prompt="分析费用异常",
        )

    assert isinstance(result, LLMResponse)
    assert result.is_stub is False
    assert result.content is not None
    assert "异常分析" in result.content
    assert result.tokens_used == 230
    assert result.error is None
    assert result.duration_ms > 0


@pytest.mark.asyncio
async def test_generate_success_no_usage(llm_service):
    """vLLM 响应缺少 usage 字段时 tokens_used 默认为 0"""
    mock_response = _make_httpx_response(200, _mock_success_response_no_usage())

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await llm_service.generate(
            system_prompt="你是审计师",
            user_prompt="分析",
        )

    assert result.is_stub is False
    assert result.content == "分析结果：费用正常。"
    assert result.tokens_used == 0


@pytest.mark.asyncio
async def test_generate_custom_params(llm_service):
    """自定义 temperature/max_tokens 参数正确传递"""
    mock_response = _make_httpx_response(200, _mock_success_response())

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await llm_service.generate(
            system_prompt="系统提示",
            user_prompt="用户提示",
            temperature=0.7,
            max_tokens=500,
        )

    assert result.is_stub is False

    # Verify request payload
    call_args = mock_client.post.call_args
    body = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
    assert body["temperature"] == 0.7
    assert body["max_tokens"] == 500
    assert body["model"] == "test-model"
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][0]["content"] == "系统提示"
    assert body["messages"][1]["role"] == "user"
    assert body["messages"][1]["content"] == "用户提示"


# --- Tests: Timeout degradation (F2.4) ---


@pytest.mark.asyncio
async def test_generate_timeout_degradation(llm_service):
    """超时 30s 后降级返回 is_stub=True + error 描述"""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("Connection timed out"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await llm_service.generate(
            system_prompt="你是审计师",
            user_prompt="分析费用异常",
            timeout=30.0,
        )

    assert result.is_stub is True
    assert result.content is None
    assert result.tokens_used == 0
    assert result.error is not None
    assert "timeout" in result.error.lower()
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_generate_connect_timeout(llm_service):
    """连接超时也降级"""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectTimeout("Failed to connect"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await llm_service.generate(
            system_prompt="系统",
            user_prompt="用户",
        )

    assert result.is_stub is True
    assert result.content is None
    assert "timeout" in result.error.lower()


# --- Tests: HTTP error handling ---


@pytest.mark.asyncio
async def test_generate_http_500_error(llm_service):
    """vLLM 返回 500 时降级"""
    mock_response = _make_httpx_response(500, text="Internal Server Error")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await llm_service.generate(
            system_prompt="系统",
            user_prompt="用户",
        )

    assert result.is_stub is True
    assert result.content is None
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_generate_http_429_rate_limit(llm_service):
    """vLLM 返回 429 限流时降级"""
    mock_response = _make_httpx_response(429, text="Rate limit exceeded")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await llm_service.generate(
            system_prompt="系统",
            user_prompt="用户",
        )

    assert result.is_stub is True
    assert "429" in result.error


# --- Tests: Connection errors ---


@pytest.mark.asyncio
async def test_generate_connection_refused(llm_service):
    """vLLM 未启动（连接拒绝）时降级"""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await llm_service.generate(
            system_prompt="系统",
            user_prompt="用户",
        )

    assert result.is_stub is True
    assert result.content is None
    assert result.error is not None
    assert "ConnectError" in result.error


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
    """LLMService 使用 settings 默认配置"""
    svc = LLMService()
    assert svc.BASE_URL == "http://localhost:8100/v1"
    assert svc.MODEL == "Kbenkhaled/Qwen3.5-27B-NVFP4"


def test_llm_service_custom_config():
    """LLMService 支持自定义 base_url 和 model"""
    svc = LLMService(base_url="http://custom:9000/v1", model="custom-model")
    assert svc.BASE_URL == "http://custom:9000/v1"
    assert svc.MODEL == "custom-model"


# --- Tests: Duration logging ---


@pytest.mark.asyncio
async def test_generate_records_duration(llm_service):
    """调用记录耗时（duration_ms > 0）"""
    mock_response = _make_httpx_response(200, _mock_success_response())

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await llm_service.generate(
            system_prompt="系统",
            user_prompt="用户",
        )

    assert result.duration_ms > 0


@pytest.mark.asyncio
async def test_generate_records_duration_on_failure(llm_service):
    """失败时也记录耗时"""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await llm_service.generate(
            system_prompt="系统",
            user_prompt="用户",
        )

    assert result.duration_ms >= 0
    assert result.is_stub is True
