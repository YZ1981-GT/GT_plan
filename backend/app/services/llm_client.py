"""LLM 客户端公共入口：本机优先路由 + 统一 transport + 熔断/限流。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator
from uuid import UUID

from app.core.database import async_session
from app.models.ai_models import AIModelType
from app.services.llm_route import (
    filter_route_by_policy,
    last_route_outcome,
    route_chat_stream,
    route_chat_sync,
    route_identity,
)
from app.services.capacity_slots import LLM_MAX_CONCURRENCY, LLM_SLOT
from app.services.llm_runtime import (
    LLMRuntimeError,
    ResolvedLLMConfig,
    RouteCandidate,
    last_total_tokens,
    last_usage,
    resolve_route,
)

logger = logging.getLogger(__name__)

# 并发许可的唯一来源是 capacity_slots.LLM_SLOT：这里与 ai_chat.native_engine 的流式回答
# 持同一个信号量实例，排队 / 执行时长由该 slot 统一计量（spec platform-heavy-jobs-and-capacity-closure
# 任务 0.2）。下面两个名字保留给既有调用方与守卫，语义不变。
_LLM_MAX_CONCURRENCY = LLM_MAX_CONCURRENCY
_llm_semaphore = LLM_SLOT.semaphore
_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SECONDS = 60
_LLM_TIMEOUT_SYNC = 30.0
_LLM_TIMEOUT_STREAM = 90.0


class LLMInvocationStatus(str, Enum):
    """模型调用结果状态；失败正文永远不混进 ``text``。"""

    success = "success"
    unavailable = "unavailable"
    timeout = "timeout"
    rejected = "rejected"
    invalid_output = "invalid_output"


@dataclass(frozen=True)
class LLMInvocationResult:
    status: LLMInvocationStatus
    text: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    model_id: UUID | None = None
    model_name: str | None = None
    deployment: str | None = None
    fallback_used: bool = False
    attempts: tuple[str, ...] = ()
    total_tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    ttft_ms: int | None = None
    tokens_per_second: float | None = None
    latency_ms: int = 0
    effective_mask_policy: str | None = None
    masked_value_count: int = 0

    @property
    def succeeded(self) -> bool:
        return self.status is LLMInvocationStatus.success and bool(self.text)


class LLMInvocationFailed(RuntimeError):
    """高风险业务调用可用的 fail-hard 适配器。"""

    def __init__(self, result: LLMInvocationResult) -> None:
        self.result = result
        super().__init__(result.error_message or result.error_code or result.status.value)


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


def _with_context_documents(
    messages: list[dict], context_documents: list[str] | None
) -> list[dict]:
    if not context_documents:
        return messages
    context_text = "\n\n---\n\n".join(context_documents)
    if len(context_text) > 8000:
        context_text = context_text[:8000] + "\n\n[...参照文档已截断...]"
    suffix = f"\n\n以下是参照文档，请在生成内容时参考：\n\n{context_text}"
    if messages and messages[0].get("role") == "system":
        return [
            {"role": "system", "content": messages[0]["content"] + suffix},
            *messages[1:],
        ]
    return [{"role": "system", "content": suffix.strip()}, *messages]


async def chat_completion_result(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    context_documents: list[str] | None = None,
    enable_thinking: bool | None = None,
    allowed_trust_zones: set[str] | frozenset[str] | None = None,
    client_data: bool = True,
    task_mask_policy: str = "strict",
    actor_role: str | None = None,
) -> LLMInvocationResult:
    """返回 typed 结果。高风险业务必须使用本入口，失败时 ``text`` 恒为 None。"""
    prepared = _with_context_documents(messages, context_documents)
    try:
        route = await _resolve_route(model)
        route = filter_route_by_policy(
            route,
            allowed_trust_zones=allowed_trust_zones,
            client_data=client_data,
        )
    except LLMRuntimeError as exc:
        return _result_from_error(exc, 0)
    from app.services.llm_payload_policy import sanitize_messages

    sanitized = sanitize_messages(
        prepared,
        task_policy=task_mask_policy,
        actor_role=actor_role,
        route=route,
    )
    payload = {
        "messages": sanitized.messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "enable_thinking": enable_thinking,
    }
    return await _sync_completion_result(
        payload,
        route=route,
        effective_mask_policy=sanitized.effective_policy,
        masked_value_count=sanitized.masked_value_count,
        restore_mapping=sanitized.restore_mapping,
    )


async def chat_completion_or_raise(
    messages: list[dict],
    **kwargs,
) -> LLMInvocationResult:
    """成功返回 typed 结果；失败抛 ``LLMInvocationFailed``，不返回占位正文。"""
    result = await chat_completion_result(messages, **kwargs)
    if not result.succeeded:
        raise LLMInvocationFailed(result)
    return result


async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    stream: bool = False,
    context_documents: list[str] | None = None,
    enable_thinking: bool | None = None,
) -> str | AsyncGenerator[str, None]:
    """兼容旧调用；新高风险写入方应改用 ``chat_completion_result``。"""
    messages = _with_context_documents(messages, context_documents)
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


async def _sync_completion_result(
    payload: dict,
    *,
    config: ResolvedLLMConfig | None = None,
    route: list[RouteCandidate] | None = None,
    effective_mask_policy: str | None = None,
    masked_value_count: int = 0,
    restore_mapping: dict[str, str] | None = None,
) -> LLMInvocationResult:
    """执行非流式模型调用并保留 typed 状态和实际路由元数据。"""
    started = time.monotonic()
    if route is None:
        try:
            route = _single_route(config) if config is not None else await _resolve_route(payload.get("model"))
        except LLMRuntimeError as exc:
            return _result_from_error(
                exc,
                int((time.monotonic() - started) * 1000),
                effective_mask_policy=effective_mask_policy,
                masked_value_count=masked_value_count,
            )
    _bind_breaker(route)
    if _breaker.is_open:
        return LLMInvocationResult(
            status=LLMInvocationStatus.unavailable,
            error_code="circuit_open",
            error_message="LLM 服务熔断中，请稍后重试",
            latency_ms=int((time.monotonic() - started) * 1000),
            effective_mask_policy=effective_mask_policy,
            masked_value_count=masked_value_count,
        )

    async with LLM_SLOT.use():
        try:
            text = await route_chat_sync(
                route,
                payload.get("messages", []),
                temperature=float(payload.get("temperature", 0.3)),
                max_tokens=int(payload.get("max_tokens", 2000)),
                enable_thinking=payload.get("enable_thinking"),
                timeout=_LLM_TIMEOUT_SYNC,
            )
            _breaker.record_success()
            if restore_mapping:
                from app.services.llm_payload_policy import restore_masked_values

                text = restore_masked_values(text, restore_mapping)
            outcome = last_route_outcome()
            usage = last_usage()
            latency_ms = int((time.monotonic() - started) * 1000)
            output_rate = (
                round(usage.completion_tokens / (latency_ms / 1000), 3)
                if usage.completion_tokens is not None and latency_ms > 0 else None
            )
            return LLMInvocationResult(
                status=LLMInvocationStatus.success,
                text=text,
                model_id=outcome.model_id if outcome else None,
                model_name=outcome.model_name if outcome else None,
                deployment=outcome.deployment if outcome else None,
                fallback_used=bool(outcome.fallback_used) if outcome else False,
                attempts=outcome.attempts if outcome else (),
                total_tokens=usage.total_tokens or last_total_tokens() or None,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                # 非流式 transport 看不到首 token；宁可空值也不拿总时延冒充 TTFT。
                ttft_ms=None,
                tokens_per_second=output_rate,
                latency_ms=latency_ms,
                effective_mask_policy=effective_mask_policy,
                masked_value_count=masked_value_count,
            )
        except LLMRuntimeError as exc:
            if exc.kind in {"unavailable", "config", "timeout"}:
                _breaker.record_failure()
            logger.warning("LLM 调用失败 code=%s", exc.code)
            return _result_from_error(
                exc,
                int((time.monotonic() - started) * 1000),
                effective_mask_policy=effective_mask_policy,
                masked_value_count=masked_value_count,
            )
        except Exception as exc:  # 调用方接线错误不累计模型熔断
            logger.error("LLM 调用异常: %s", type(exc).__name__, exc_info=True)
            return LLMInvocationResult(
                status=LLMInvocationStatus.unavailable,
                error_code="internal_error",
                error_message="LLM 调用失败，请稍后重试",
                latency_ms=int((time.monotonic() - started) * 1000),
                effective_mask_policy=effective_mask_policy,
                masked_value_count=masked_value_count,
            )


def _result_from_error(
    exc: LLMRuntimeError,
    latency_ms: int,
    *,
    effective_mask_policy: str | None = None,
    masked_value_count: int = 0,
) -> LLMInvocationResult:
    if exc.code == "provider_timeout":
        status = LLMInvocationStatus.timeout
    elif exc.code in {"empty_response", "output_limit", "invalid_response"} or exc.kind == "output":
        status = LLMInvocationStatus.invalid_output
    elif exc.code == "provider_rate_limited" or exc.kind == "request":
        status = LLMInvocationStatus.rejected
    else:
        status = LLMInvocationStatus.unavailable
    return LLMInvocationResult(
        status=status,
        error_code=exc.code,
        error_message=str(exc),
        latency_ms=latency_ms,
        effective_mask_policy=effective_mask_policy,
        masked_value_count=masked_value_count,
    )


async def _sync_completion(
    payload: dict,
    *,
    config: ResolvedLLMConfig | None = None,
    route: list[RouteCandidate] | None = None,
) -> str:
    """非流式兼容入口；所有失败文案只在本函数渲染。"""
    result = await _sync_completion_result(payload, config=config, route=route)
    if result.succeeded:
        return result.text or ""
    # 占位串须原样写在本函数内：既有守卫扫描全部兼容失败前缀。
    if result.error_code == "circuit_open":
        return "[LLM 服务熔断中，请稍后重试]"
    if result.error_code == "provider_timeout":
        return "[LLM 调用超时，请稍后重试]"
    if result.error_code == "output_limit":
        return "⚠️ 思考超出 token 限制，请简化提问或增大 max_tokens 设置。"
    if result.error_code == "empty_response":
        return "⚠️ LLM 未返回有效内容，请重试。"
    if result.error_code in {"provider_unreachable", "invalid_model_config"}:
        return "[LLM 服务暂不可用，请检查模型配置和网络]"
    if result.error_code == "internal_error":
        return "[LLM 调用失败，请稍后重试]"
    return f"[LLM 调用失败: {result.error_message or result.error_code}]"


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

    async with LLM_SLOT.use():
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
