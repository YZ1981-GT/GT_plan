"""LLM typed 结果契约：失败不再伪装成可保存正文。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services import llm_client as client
from app.services.llm_route import RouteOutcome
from app.services.llm_runtime import LLMRuntimeError, RouteCandidate


@pytest.fixture(autouse=True)
def _reset_breaker():
    client._breaker.reset()
    client._breaker_identity = None
    yield
    client._breaker.reset()
    client._breaker_identity = None


def _route() -> list[RouteCandidate]:
    return [RouteCandidate("served-model", "local", uuid4(), None)]


@pytest.mark.asyncio
async def test_typed_success_records_actual_route_and_usage() -> None:
    outcome = RouteOutcome(
        model_name="served-model",
        deployment="server",
        model_id=uuid4(),
        fallback_used=True,
        attempts=("本机模型：连接失败",),
    )
    with patch.object(client, "route_chat_sync", new=AsyncMock(return_value="有效正文")), patch.object(
        client, "last_route_outcome", return_value=outcome
    ), patch.object(client, "last_total_tokens", return_value=123):
        result = await client._sync_completion_result(
            {"messages": [], "temperature": 0.1, "max_tokens": 100}, route=_route()
        )

    assert result.succeeded
    assert result.text == "有效正文"
    assert result.model_name == "served-model"
    assert result.deployment == "server"
    assert result.fallback_used is True
    assert result.attempts == ("本机模型：连接失败",)
    assert result.total_tokens == 123


@pytest.mark.parametrize(
    ("code", "kind", "status"),
    [
        ("provider_unreachable", "unavailable", client.LLMInvocationStatus.unavailable),
        ("provider_timeout", "timeout", client.LLMInvocationStatus.timeout),
        ("provider_rate_limited", "request", client.LLMInvocationStatus.rejected),
        ("empty_response", "output", client.LLMInvocationStatus.invalid_output),
    ],
)
@pytest.mark.asyncio
async def test_typed_failure_never_contains_business_text(code, kind, status) -> None:
    error = LLMRuntimeError(code, "上游失败", kind=kind)
    with patch.object(client, "route_chat_sync", new=AsyncMock(side_effect=error)):
        result = await client._sync_completion_result(
            {"messages": [], "temperature": 0.1, "max_tokens": 100}, route=_route()
        )

    assert result.status is status
    assert result.text is None
    assert result.succeeded is False
    assert result.error_code == code


@pytest.mark.asyncio
async def test_request_rejection_does_not_open_global_breaker() -> None:
    error = LLMRuntimeError("provider_rate_limited", "限流", kind="request")
    with patch.object(client, "route_chat_sync", new=AsyncMock(side_effect=error)):
        for _ in range(3):
            await client._sync_completion_result(
                {"messages": [], "temperature": 0.1, "max_tokens": 100}, route=_route()
            )

    assert client._breaker._failure_count == 0
    assert client._breaker.is_open is False


@pytest.mark.asyncio
async def test_fail_hard_adapter_raises_typed_result() -> None:
    failed = client.LLMInvocationResult(
        status=client.LLMInvocationStatus.unavailable,
        error_code="provider_unreachable",
        error_message="不可达",
    )
    with patch.object(client, "chat_completion_result", new=AsyncMock(return_value=failed)):
        with pytest.raises(client.LLMInvocationFailed) as caught:
            await client.chat_completion_or_raise([{"role": "user", "content": "测试"}])

    assert caught.value.result is failed
