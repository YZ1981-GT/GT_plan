"""LLM 客户端公共入口：本机优先路由 + 统一 transport + 熔断/限流。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator

from app.core.database import async_session
from app.models.ai_models import AIModelType
from app.services.llm_route import route_chat_stream, route_chat_sync, route_identity
from app.services.llm_runtime import (
    LLMRuntimeError,
    ResolvedLLMConfig,
    RouteCandidate,
    resolve_route,
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


def _bind_breaker(route: list[RouteCandidate]) -> None:
    """熔断器按整条路由计数（ADR-ROUTE-007）：路由组成变化时重置，不缓存 URL/Key。"""
    global _breaker_identity
    identity = route_identity(route)
    if identity != _breaker_identity:
        _breaker.reset()
        _breaker_identity = identity


def _single_route(config: ResolvedLLMConfig) -> list[RouteCandidate]:
    """兼容旧调用：显式给定单个配置时按单候选路由执行。"""
    return [RouteCandidate(config.model_name, config.deployment, config.model_id, config)]


async def _resolve_route(model: str | None = None) -> list[RouteCandidate]:
    async with async_session() as db:
        return await resolve_route(db, AIModelType.chat, requested_model=model)


async def get_active_config() -> dict[str, object]:
    """返回路由首个可用候选的配置；不包含 Key 或 Key 前缀。"""
    route = await _resolve_route()
    config = next((c.config for c in route if c.config is not None), None)
    if config is None:
        raise route[0].error or LLMRuntimeError("no_model", "没有可用的模型配置", kind="config")
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
    """按本机优先路由调用；无启用模型时回落 `.env`。``model`` 只作优先提示。"""
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

    route = await _resolve_route(model)
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "enable_thinking": enable_thinking,
    }
    if stream:
        return _stream_completion(payload, route=route)
    return await _sync_completion(payload, route=route)


async def _sync_completion(
    payload: dict,
    *,
    config: ResolvedLLMConfig | None = None,
    route: list[RouteCandidate] | None = None,
) -> str:
    """非流式调用；保留旧 helper 名与 ``config=`` 单候选入口供测试与兼容调用。"""
    if route is None:
        route = _single_route(config) if config is not None else await _resolve_route(payload.get("model"))
    _bind_breaker(route)
    if _breaker.is_open:
        return "[LLM 服务熔断中，请稍后重试]"

    async with _llm_semaphore:
        try:
            result = await route_chat_sync(
                route,
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
            # 占位串须原样写在本函数内：test_task6 守卫只扫 _sync/_stream_completion 的字面量。
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
            # 调用方参数错误等不是模型服务故障：不计入熔断，否则一个写错的调用点就能
            # 在 60 秒内拖垮全部 AI 功能（ADR-ROUTE-007）。
            logger.error("LLM 调用异常: %s", type(exc).__name__, exc_info=True)
            return "[LLM 调用失败，请稍后重试]"


async def _stream_completion(
    payload: dict,
    *,
    config: ResolvedLLMConfig | None = None,
    route: list[RouteCandidate] | None = None,
) -> AsyncGenerator[str, None]:
    """流式调用；路由与 semaphore 在完整流生命周期内保持一致。"""
    if route is None:
        route = _single_route(config) if config is not None else await _resolve_route(payload.get("model"))
    _bind_breaker(route)
    if _breaker.is_open:
        yield "[LLM 服务熔断中，请稍后重试]"
        return

    async with _llm_semaphore:
        try:
            async for chunk in route_chat_stream(
                route,
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
            logger.error("LLM 流式调用异常: %s", type(exc).__name__, exc_info=True)
            yield "[LLM 错误，请稍后重试]"
