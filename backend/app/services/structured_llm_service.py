"""统一 LLM 结构化输出（Instructor + vLLM guided_json）。"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client = None
_guided_unsupported_logged = False

# --- 熔断器：复用 llm_client._breaker 实例 ---
try:
    from app.services.llm_client import _breaker
except ImportError:
    _breaker = None  # type: ignore[assignment]


class StructuredOutputError(Exception):
    """结构化输出在所有重试后仍失败。"""


def _get_instructor_client():
    global _client
    if _client is not None:
        return _client
    import instructor
    from openai import AsyncOpenAI

    http_client = httpx.AsyncClient(trust_env=False, timeout=120.0)
    raw = AsyncOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY or "not-needed",
        http_client=http_client,
    )
    _client = instructor.from_openai(raw)
    return _client


def _is_guided_rejected(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in ("BadRequestError", "APIStatusError"):
        msg = str(exc).lower()
        return "guided" in msg or "unknown" in msg or "invalid" in msg
    return False


def _is_connection_failure(exc: Exception) -> bool:
    """判断是否为连接/超时类失败（应触发熔断）。"""
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        return True
    name = type(exc).__name__
    # openai 库包装的连接错误
    if name in ("APIConnectionError", "APITimeoutError"):
        return True
    return False


async def extract_structured(
    messages: list[dict[str, Any]],
    response_model: type[T],
    *,
    model: str | None = None,
    max_retries: int | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> T:
    """统一结构化输出入口。"""
    global _guided_unsupported_logged

    # --- 熔断器检查：打开时快速失败 ---
    if _breaker is not None and _breaker.is_open:
        raise StructuredOutputError("Circuit breaker open — LLM 服务熔断中")

    retries = (
        settings.LLM_STRUCTURED_MAX_RETRIES if max_retries is None else max_retries
    )
    model_name = model or settings.DEFAULT_CHAT_MODEL
    client = _get_instructor_client()
    schema = response_model.model_json_schema()

    kwargs: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "response_model": response_model,
        "max_retries": retries,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    use_guided = settings.LLM_GUIDED_DECODING_ENABLED
    if use_guided:
        kwargs["extra_body"] = {"guided_json": schema}
        try:
            result = await client.chat.completions.create(**kwargs)
            # 成功 → 记录
            if _breaker is not None:
                _breaker.record_success()
            return result
        except Exception as exc:
            if _is_guided_rejected(exc):
                if not _guided_unsupported_logged:
                    logger.warning(
                        "vLLM guided_json 不可用，降级纯 Instructor retry: %s",
                        exc,
                    )
                    _guided_unsupported_logged = True
                kwargs.pop("extra_body", None)
            else:
                # 连接/超时类失败 → 记录熔断
                if _breaker is not None and _is_connection_failure(exc):
                    _breaker.record_failure()
                raise StructuredOutputError(str(exc)) from exc

    try:
        result = await client.chat.completions.create(**kwargs)
        if _breaker is not None:
            _breaker.record_success()
        return result
    except Exception as exc:
        if _breaker is not None and _is_connection_failure(exc):
            _breaker.record_failure()
        raise StructuredOutputError(str(exc)) from exc
