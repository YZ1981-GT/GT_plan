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


def _patch_service(
    mock_client,
    guided_enabled=True,
    max_retries=2,
    model_name="test-model",
    breaker=None,
):
    """返回组合 patch context manager。"""
    import contextlib

    @contextlib.asynccontextmanager
    async def ctx():
        with patch(
            "app.services.structured_llm_service._get_instructor_client",
            return_value=mock_client,
        ), patch("app.services.structured_llm_service.settings") as s, patch(
            "app.services.structured_llm_service._breaker", breaker
        ), patch(
            "app.services.structured_llm_service._guided_unsupported_logged", False
        ):
            s.LLM_GUIDED_DECODING_ENABLED = guided_enabled
            s.LLM_STRUCTURED_MAX_RETRIES = max_retries
            s.DEFAULT_CHAT_MODEL = model_name
            yield s

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
