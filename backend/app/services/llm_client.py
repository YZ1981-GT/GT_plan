"""LLM 客户端公共入口：DB active 配置 + 统一 transport + 熔断/限流。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator

from app.core.database import async_session
from app.models.ai_models import AIModelType
from app.services.llm_runtime import (
    LLMRuntimeError,
    ResolvedLLMConfig,
    chat_stream as runtime_chat_stream,
    chat_sync as runtime_chat_sync,
    resolve_runtime_config,
)

logger = logging.getLogger(__name__)

_LLM_MAX_CONCURRENCY = 5
_llm_semaphore = asyncio.Semaphore(_LLM_MAX_CONCURRENCY)
_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SECONDS = 60
_LLM_TIMEOUT_SYNC = 30.0
_LLM_TIMEOUT_STREAM = 90.0


class _CircuitBreaker:
    """简单熔断器：closed → open → half-open。"""

    def __init__(self):
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "closed"

    @property
    def is_open(self) -> bool:
        if self._state == "open":
            if time.time() - self._last_failure_time > _CIRCUIT_COOLDOWN_SECONDS:
                self._state = "half-open"
                return False
            return True
        return False

    def record_success(self):
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= _CIRCUIT_FAILURE_THRESHOLD:
            self._state = "open"
            logger.warning(
                "LLM 熔断器打开：连续 %d 次失败，冷却 %ds",
                self._failure_count,
                _CIRCUIT_COOLDOWN_SECONDS,
            )

    def reset(self):
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "closed"


_breaker = _CircuitBreaker()
_breaker_identity: str | None = None


def _bind_breaker(config: ResolvedLLMConfig) -> None:
    """配置切换时只重置熔断器，不缓存 URL/Key。"""
    global _breaker_identity
    identity = f"{config.provider.value}|{config.endpoint_url}|{config.model_name}"
    if identity != _breaker_identity:
        _breaker.reset()
        _breaker_identity = identity


async def _resolve_config(model: str | None = None) -> ResolvedLLMConfig:
    async with async_session() as db:
        return await resolve_runtime_config(
            db, AIModelType.chat, requested_model=model
        )


async def get_active_config() -> dict[str, object]:
    """返回当前真实生效配置；不包含 Key 或 Key 前缀。"""
    config = await _resolve_config()
    safe = config.safe_dict()
    safe.pop("has_api_key", None)
    return safe


async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    stream: bool = False,
    context_documents: list[str] | None = None,
    enable_thinking: bool | None = None,
) -> str | AsyncGenerator[str, None]:
    """调用当前 active LLM；无 active row 时回落 `.env`。"""
    if context_documents:
        context_text = "\n\n---\n\n".join(context_documents)
        if len(context_text) > 8000:
            context_text = context_text[:8000] + "\n\n[...参照文档已截断...]"
        suffix = f"\n\n以下是参照文档，请在生成内容时参考：\n\n{context_text}"
        if messages and messages[0].get("role") == "system":
            messages = [
                {"role": "system", "content": messages[0]["content"] + suffix},
                *messages[1:],
            ]
        else:
            messages = [{"role": "system", "content": suffix.strip()}, *messages]

    config = await _resolve_config(model)
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "enable_thinking": enable_thinking,
    }
    if stream:
        return _stream_completion(payload, config=config)
    return await _sync_completion(payload, config=config)


async def _sync_completion(
    payload: dict,
    *,
    config: ResolvedLLMConfig | None = None,
) -> str:
    """非流式调用；保留旧 helper 名供测试与兼容调用。"""
    if config is None:
        config = await _resolve_config(payload.get("model"))
    _bind_breaker(config)
    if _breaker.is_open:
        return "[LLM 服务熔断中，请稍后重试]"

    async with _llm_semaphore:
        try:
            result = await runtime_chat_sync(
                config,
                payload.get("messages", []),
                temperature=float(payload.get("temperature", 0.3)),
                max_tokens=int(payload.get("max_tokens", 2000)),
                enable_thinking=payload.get("enable_thinking"),
                timeout=_LLM_TIMEOUT_SYNC,
            )
            _breaker.record_success()
            return result
        except LLMRuntimeError as exc:
            _breaker.record_failure()
            logger.warning("LLM 调用失败 code=%s", exc.code)
            if exc.code == "provider_timeout":
                return "[LLM 调用超时，请稍后重试]"
            if exc.code == "output_limit":
                return "⚠️ 思考超出 token 限制，请简化提问或增大 max_tokens 设置。"
            if exc.code == "empty_response":
                return "⚠️ LLM 未返回有效内容，请重试。"
            if exc.code in {"provider_unreachable", "invalid_model_config"}:
                return "[LLM 服务暂不可用，请检查模型配置和网络]"
            return f"[LLM 调用失败: {exc}]"
        except Exception as exc:
            _breaker.record_failure()
            logger.error("LLM 调用异常: %s", type(exc).__name__, exc_info=True)
            return "[LLM 调用失败，请稍后重试]"


async def _stream_completion(
    payload: dict,
    *,
    config: ResolvedLLMConfig | None = None,
) -> AsyncGenerator[str, None]:
    """流式调用；配置与 semaphore 在完整流生命周期内保持一致。"""
    if config is None:
        config = await _resolve_config(payload.get("model"))
    _bind_breaker(config)
    if _breaker.is_open:
        yield "[LLM 服务熔断中，请稍后重试]"
        return

    async with _llm_semaphore:
        try:
            async for chunk in runtime_chat_stream(
                config,
                payload.get("messages", []),
                temperature=float(payload.get("temperature", 0.3)),
                max_tokens=int(payload.get("max_tokens", 2000)),
                enable_thinking=payload.get("enable_thinking"),
                timeout=_LLM_TIMEOUT_STREAM,
            ):
                yield chunk
            _breaker.record_success()
        except LLMRuntimeError as exc:
            _breaker.record_failure()
            logger.warning("LLM 流式调用失败 code=%s", exc.code)
            if exc.code == "provider_timeout":
                yield "[LLM 调用超时，请稍后重试]"
            elif exc.code == "provider_unreachable":
                yield "[LLM 服务暂不可用]"
            else:
                yield f"[LLM 错误: {exc}]"
        except Exception as exc:
            _breaker.record_failure()
            logger.error("LLM 流式调用异常: %s", type(exc).__name__, exc_info=True)
            yield "[LLM 错误，请稍后重试]"
