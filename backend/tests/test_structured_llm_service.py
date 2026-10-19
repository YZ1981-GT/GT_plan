"""structured_llm_service 单测（mock instructor 客户端）。

覆盖路径：
  A — guided_json 成功（extra_body 含 schema）
  B — guided 被拒 → instructor fallback（BadRequestError 降级）
  C — 重试耗尽 → StructuredOutputError
  D — 熔断打开 → 快速失败
  E — LLM_GUIDED_DECODING_ENABLED=False → 不传 guided_json
  F — 连接失败记录熔断
  G — LLM_STRUCTURED_OUTPUT_ENABLED=False → recognizer 走 legacy（不调 extract_structured）
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel


# --- 测试用 Pydantic 模型 ---

class DummyResult(BaseModel):
    name: str
    value: int


# --- helpers ---

def _make_mock_client(side_effect=None, return_value=None):
    """构造 mock instructor client。"""
    client = MagicMock()
    create_mock = AsyncMock(side_effect=side_effect, return_value=return_value)
    client.chat.completions.create = create_mock
    return client


def local_route(model_name="test-model", endpoint="http://localhost:8100/v1"):
    """单条本机候选路由（结构化输出走本机优先路由，V197）。"""
    from app.models.ai_models import AIModelType, AIProvider
    from app.services.llm_provider_registry import provider_profile
    from app.services.llm_runtime import ResolvedLLMConfig, RouteCandidate

    config = ResolvedLLMConfig(
        model_name=model_name, model_type=AIModelType.chat,
        provider=AIProvider.openai_compatible, endpoint_url=endpoint, api_key=None,
        profile=provider_profile(AIProvider.openai_compatible), source="database",
        deployment="local" if "localhost" in endpoint else "server",
    )
    return [RouteCandidate(model_name, config.deployment, None, config)]


def _patch_service(
    mock_client,
    guided_enabled=True,
    max_retries=2,
    model_name="test-model",
    breaker=None,
    route=None,
):
    """返回组合 patch context manager。"""
    import contextlib

    from app.services.llm_route import reset_route_health

    @contextlib.asynccontextmanager
    async def ctx():
        reset_route_health()
        with patch(
            "app.services.structured_llm_service._get_instructor_client",
            return_value=mock_client,
        ), patch(
            "app.services.structured_llm_service._resolve_route",
            new=AsyncMock(return_value=route or local_route(model_name)),
        ), patch(
            "app.services.llm_endpoint_policy.resolve_endpoint", new=_fake_resolve_endpoint
        ), patch("app.services.structured_llm_service.settings") as s, patch(
            "app.services.structured_llm_service._breaker", breaker
        ), patch(
            "app.services.structured_llm_service._guided_unsupported_logged", False
        ):
            s.LLM_GUIDED_DECODING_ENABLED = guided_enabled
            s.LLM_STRUCTURED_MAX_RETRIES = max_retries
            s.DEFAULT_CHAT_MODEL = model_name
            s.LLM_LOCAL_CONNECT_TIMEOUT_SECONDS = 3.0
            yield s
        reset_route_health()

    return ctx()


# =============================================================================
# Path A: guided_json 成功 — extra_body 含 schema
# =============================================================================


@pytest.mark.asyncio
async def test_guided_json_success_passes_extra_body():
    """guided 开启时，extra_body={"guided_json": schema} 被正确传入。"""
    from app.services.structured_llm_service import extract_structured

    expected = DummyResult(name="hello", value=42)
    mock_client = _make_mock_client(return_value=expected)
    breaker = MagicMock()
    breaker.is_open = False

    async with _patch_service(mock_client, guided_enabled=True, breaker=breaker):
        result = await extract_structured(
            [{"role": "user", "content": "test"}],
            DummyResult,
        )

    assert result == expected
    # 验证 extra_body 被传递
    call_kwargs = mock_client.chat.completions.create.call_args
    assert "extra_body" in call_kwargs.kwargs or (
        call_kwargs[1] and "extra_body" in call_kwargs[1]
    )
    # 取 kwargs
    kw = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
    assert "guided_json" in kw["extra_body"]
    schema = kw["extra_body"]["guided_json"]
    # schema 应该是 DummyResult 的 JSON schema
    assert schema == DummyResult.model_json_schema()
    # 熔断器记录成功
    breaker.record_success.assert_called()


# =============================================================================
# Path B: guided 被拒 → 降级 instructor fallback
# =============================================================================


@pytest.mark.asyncio
async def test_guided_rejected_falls_back_to_instructor():
    """guided_json 被 vLLM 拒绝时（BadRequestError），降级无 extra_body 重试成功。"""
    from app.services.structured_llm_service import extract_structured

    expected = DummyResult(name="fallback", value=99)

    # 模拟 BadRequestError（guided 路径第一次调用失败）
    bad_request_exc = type("BadRequestError", (Exception,), {})("guided_json not supported")

    call_count = {"n": 0}

    async def side_effect_fn(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # 第一次带 extra_body 调用 → 拒绝
            raise bad_request_exc
        # 第二次不带 extra_body → 成功
        return expected

    mock_client = _make_mock_client()
    mock_client.chat.completions.create = AsyncMock(side_effect=side_effect_fn)
    breaker = MagicMock()
    breaker.is_open = False

    async with _patch_service(mock_client, guided_enabled=True, breaker=breaker):
        result = await extract_structured(
            [{"role": "user", "content": "test"}],
            DummyResult,
        )

    assert result == expected
    # 应调用两次：第一次 guided 失败，第二次 fallback 成功
    assert mock_client.chat.completions.create.call_count == 2
    # 第二次调用不应含 extra_body
    second_call = mock_client.chat.completions.create.call_args_list[1]
    kw = second_call.kwargs if second_call.kwargs else second_call[1]
    assert "extra_body" not in kw


# =============================================================================
# Path C: 重试耗尽 → StructuredOutputError
# =============================================================================


@pytest.mark.asyncio
async def test_retry_exhausted_raises_structured_output_error():
    """所有重试失败后抛出 StructuredOutputError。"""
    from app.services.structured_llm_service import (
        StructuredOutputError,
        extract_structured,
    )

    mock_client = _make_mock_client(side_effect=RuntimeError("always fail"))
    breaker = MagicMock()
    breaker.is_open = False

    async with _patch_service(
        mock_client, guided_enabled=False, max_retries=0, breaker=breaker
    ):
        with pytest.raises(StructuredOutputError, match="always fail"):
            await extract_structured(
                [{"role": "user", "content": "test"}],
                DummyResult,
            )


# =============================================================================
# Path D: 熔断打开 → 快速失败（不调用 client）
# =============================================================================


@pytest.mark.asyncio
async def test_breaker_open_fast_fails():
    """熔断器打开时立即抛 StructuredOutputError，不调用 client。"""
    from app.services.structured_llm_service import (
        StructuredOutputError,
        extract_structured,
    )

    mock_client = _make_mock_client(return_value=DummyResult(name="x", value=1))
    breaker = MagicMock()
    breaker.is_open = True  # 熔断打开

    async with _patch_service(mock_client, breaker=breaker):
        with pytest.raises(StructuredOutputError, match="熔断"):
            await extract_structured(
                [{"role": "user", "content": "test"}],
                DummyResult,
            )

    # 不应调用 client
    mock_client.chat.completions.create.assert_not_called()


# =============================================================================
# Path E: LLM_GUIDED_DECODING_ENABLED=False → 不传 guided_json
# =============================================================================


@pytest.mark.asyncio
async def test_guided_disabled_no_extra_body():
    """guided 子开关关闭时，不传 extra_body 直接走 instructor retry。"""
    from app.services.structured_llm_service import extract_structured

    expected = DummyResult(name="no-guided", value=7)
    mock_client = _make_mock_client(return_value=expected)
    breaker = MagicMock()
    breaker.is_open = False

    async with _patch_service(
        mock_client, guided_enabled=False, breaker=breaker
    ):
        result = await extract_structured(
            [{"role": "user", "content": "test"}],
            DummyResult,
        )

    assert result == expected
    # 验证未传 extra_body
    call_kwargs = mock_client.chat.completions.create.call_args
    kw = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
    assert "extra_body" not in kw


# =============================================================================
# Path F: 连接失败记录熔断
# =============================================================================


@pytest.mark.asyncio
async def test_connection_failure_records_breaker():
    """连接/超时类异常触发 breaker.record_failure()。"""
    import httpx

    from app.services.structured_llm_service import (
        StructuredOutputError,
        extract_structured,
    )

    mock_client = _make_mock_client(
        side_effect=httpx.ConnectError("connection refused")
    )
    breaker = MagicMock()
    breaker.is_open = False

    async with _patch_service(
        mock_client, guided_enabled=True, breaker=breaker
    ):
        with pytest.raises(StructuredOutputError):
            await extract_structured(
                [{"role": "user", "content": "test"}],
                DummyResult,
            )

    breaker.record_failure.assert_called()


# =============================================================================
# Path G: LLM_STRUCTURED_OUTPUT_ENABLED=False → recognizer 走 legacy
# =============================================================================


@pytest.mark.asyncio
async def test_recognizer_uses_legacy_when_structured_disabled():
    """总开关 LLM_STRUCTURED_OUTPUT_ENABLED=False 时，
    wp_document_recognizer._llm_recognize 不调 extract_structured（走 legacy json.loads）。
    """
    from uuid import uuid4
    from unittest.mock import patch as _patch

    import app.core.config as config_mod

    # Mock extract_structured 被调用的 spy
    extract_spy = AsyncMock()

    # Mock chat_completion 返回合法 JSON
    legacy_response = '{"voucher_no": "V001", "voucher_date": "2025-01-01"}'

    # 暂存原始值，patch 后恢复
    original_enabled = config_mod.settings.LLM_STRUCTURED_OUTPUT_ENABLED

    try:
        # 直接修改 settings 实例属性（local import 会拿到同一单例）
        config_mod.settings.LLM_STRUCTURED_OUTPUT_ENABLED = False

        with _patch(
            "app.services.structured_llm_service.extract_structured",
            extract_spy,
        ):
            with _patch(
                "app.services.llm_client.chat_completion",
                new_callable=AsyncMock,
                return_value=legacy_response,
            ):
                from app.services.wp_document_recognizer import WpDocumentRecognizer

                recognizer = WpDocumentRecognizer.__new__(WpDocumentRecognizer)
                result = await recognizer._llm_recognize(
                    db=MagicMock(),
                    attachment_id=uuid4(),
                    att_info={"filename": "test.pdf"},
                    doc_type="voucher",
                )
    finally:
        config_mod.settings.LLM_STRUCTURED_OUTPUT_ENABLED = original_enabled

    # extract_structured 不应被调用
    extract_spy.assert_not_called()
    # legacy json.loads 应返回解析结果
    assert result is not None
    assert result.get("voucher_no") == "V001"


# =============================================================================
# Path H: 本机优先路由（V197）—— guided 只发本机、连接失败换服务器、模型名取候选
# =============================================================================


def _two_candidate_route():
    local = local_route("local-model")[0]
    server = local_route("qwen3.8", endpoint="https://ai.example.test/v1")[0]
    return [local, server]


@pytest.mark.asyncio
async def test_guided_json_is_not_sent_to_server_candidate():
    """guided_json 是 vLLM 专有参数：服务器候选即使开关打开也不发。"""
    from app.services.structured_llm_service import extract_structured

    expected = DummyResult(name="server", value=1)
    mock_client = _make_mock_client(return_value=expected)
    breaker = MagicMock()
    breaker.is_open = False
    server_only = [local_route("qwen3.8", endpoint="https://ai.example.test/v1")[0]]

    async with _patch_service(mock_client, guided_enabled=True, breaker=breaker, route=server_only):
        result = await extract_structured([{"role": "user", "content": "t"}], DummyResult)

    assert result == expected
    kw = mock_client.chat.completions.create.call_args.kwargs
    assert "extra_body" not in kw
    assert kw["model"] == "qwen3.8"


@pytest.mark.asyncio
async def test_connection_failure_on_local_falls_back_to_server():
    """本机连不上 ⇒ 同一次调用改用服务器候选；整条路由成功记熔断成功、不记失败。"""
    import httpx

    from app.services.llm_route import last_route_outcome
    from app.services.structured_llm_service import extract_structured

    expected = DummyResult(name="fallback", value=2)
    calls: list[str] = []

    async def create(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "local-model":
            raise httpx.ConnectError("connection refused")
        return expected

    mock_client = _make_mock_client()
    mock_client.chat.completions.create = AsyncMock(side_effect=create)
    breaker = MagicMock()
    breaker.is_open = False

    async with _patch_service(
        mock_client, guided_enabled=False, breaker=breaker, route=_two_candidate_route()
    ):
        result = await extract_structured([{"role": "user", "content": "t"}], DummyResult)
        outcome = last_route_outcome()

    assert result == expected
    assert calls == ["local-model", "qwen3.8"]
    breaker.record_success.assert_called()
    breaker.record_failure.assert_not_called()
    assert outcome is not None and outcome.model_name == "qwen3.8" and outcome.fallback_used


@pytest.mark.asyncio
async def test_non_connection_error_does_not_fall_back():
    """请求被模型拒绝（非连接类）不换候选：避免同一请求在两端重复执行。"""
    from app.services.structured_llm_service import StructuredOutputError, extract_structured

    calls: list[str] = []

    async def create(**kwargs):
        calls.append(kwargs["model"])
        raise RuntimeError("schema validation failed")

    mock_client = _make_mock_client()
    mock_client.chat.completions.create = AsyncMock(side_effect=create)
    breaker = MagicMock()
    breaker.is_open = False

    async with _patch_service(
        mock_client, guided_enabled=False, breaker=breaker, route=_two_candidate_route()
    ):
        with pytest.raises(StructuredOutputError, match="schema validation failed"):
            await extract_structured([{"role": "user", "content": "t"}], DummyResult)

    assert calls == ["local-model"]


async def _fake_resolve_endpoint(endpoint, profile):
    """不做真实 DNS：结构化输出测试只关心候选顺序与参数。"""
    from app.services.llm_endpoint_policy import SafeEndpoint

    return SafeEndpoint(endpoint.rstrip("/"), "test.invalid")


# =============================================================================
# Path I: 结构化输出的转移口径与对话路由一致（ADR-ROUTE-003）
# =============================================================================


def _sdk_error(name: str, cause: BaseException | None = None) -> Exception:
    """构造与 openai SDK 同名的异常（判定只看类名与 __cause__，不依赖 SDK 版本）。"""
    exc = type(name, (Exception,), {})(name)
    exc.__cause__ = cause
    return exc


@pytest.mark.asyncio
@pytest.mark.parametrize(("failure", "fails_over"), [
    (_sdk_error("APITimeoutError", httpx.ConnectTimeout("slow connect")), True),
    (_sdk_error("APIConnectionError", httpx.ConnectError("refused")), True),
    (_sdk_error("InternalServerError"), True),
    (_sdk_error("NotFoundError"), True),
    (_sdk_error("APITimeoutError", httpx.ReadTimeout("slow answer")), False),
    (_sdk_error("RateLimitError"), False),
    (_sdk_error("BadRequestError"), False),
])
async def test_structured_failover_matches_chat_route_semantics(failure, fails_over):
    """读超时 / 限流 / 参数错误不换服务器重复执行；连不上 / 5xx / 模型不存在才换。"""
    from app.services.structured_llm_service import StructuredOutputError, extract_structured

    expected = DummyResult(name="server", value=3)
    calls: list[str] = []

    async def create(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "local-model":
            raise failure
        return expected

    mock_client = _make_mock_client()
    mock_client.chat.completions.create = AsyncMock(side_effect=create)
    breaker = MagicMock()
    breaker.is_open = False

    async with _patch_service(
        mock_client, guided_enabled=False, breaker=breaker, route=_two_candidate_route()
    ):
        if fails_over:
            assert await extract_structured([{"role": "user", "content": "t"}], DummyResult) == expected
        else:
            with pytest.raises(StructuredOutputError):
                await extract_structured([{"role": "user", "content": "t"}], DummyResult)

    assert calls == (["local-model", "qwen3.8"] if fails_over else ["local-model"])


@pytest.mark.asyncio
async def test_structured_read_timeout_still_counts_for_the_breaker():
    """不转移的读超时仍计入熔断（整条路由到此为止，旧口径保留）。"""
    from app.services.structured_llm_service import StructuredOutputError, extract_structured

    mock_client = _make_mock_client(side_effect=httpx.ReadTimeout("slow answer"))
    breaker = MagicMock()
    breaker.is_open = False
    async with _patch_service(
        mock_client, guided_enabled=False, breaker=breaker, route=_two_candidate_route()
    ):
        with pytest.raises(StructuredOutputError):
            await extract_structured([{"role": "user", "content": "t"}], DummyResult)
    assert mock_client.chat.completions.create.await_count == 1
    breaker.record_failure.assert_called_once()
