"""统一 LLM 结构化输出（Instructor + vLLM guided_json），走本机优先路由（V197）。

端点、模型名与 Key 来自 ``llm_runtime.resolve_route``（与其余对话调用同一份候选），
不再读 `.env` 冻结的模块级单例；出站同样经 ``resolve_endpoint`` 复核并使用 fake-IP 兼容 transport。
``guided_json`` 是 vLLM 专有参数，只发给本机候选；连接类失败改用下一个候选。
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.models.ai_model_options import AIDeployment

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_guided_unsupported_logged = False

# --- 熔断器：复用 llm_client._breaker 实例（整条路由计数） ---
try:
    from app.services.llm_client import _breaker
except ImportError:
    _breaker = None  # type: ignore[assignment]


class StructuredOutputError(Exception):
    """结构化输出在所有重试后仍失败。"""


async def _resolve_route(model: str | None):
    """对话路由候选（测试替换点）。"""
    from app.core.database import async_session
    from app.models.ai_models import AIModelType
    from app.services.llm_runtime import resolve_route

    async with async_session() as db:
        return await resolve_route(db, AIModelType.chat, requested_model=model)


def _get_instructor_client(config: Any, http_client: httpx.AsyncClient, base_url: str):
    """按候选构造 instructor 客户端（不缓存：路由与 Key 每次重新解析）。"""
    import instructor
    from openai import AsyncOpenAI

    raw = AsyncOpenAI(
        base_url=base_url,
        api_key=config.api_key or "not-needed",
        http_client=http_client,
    )
    return instructor.from_openai(raw)


def _is_guided_rejected(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in ("BadRequestError", "APIStatusError"):
        msg = str(exc).lower()
        return "guided" in msg or "unknown" in msg or "invalid" in msg
    return False


def _is_connection_failure(exc: Exception) -> bool:
    """判断是否为连接/超时类失败（触发熔断）。"""
    from app.services.llm_endpoint_policy import LLMEndpointPolicyError

    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, LLMEndpointPolicyError)):
        return True
    name = type(exc).__name__
    # openai 库包装的连接错误
    if name in ("APIConnectionError", "APITimeoutError"):
        return True
    return False


# openai SDK 状态码异常中可换候选的（与 llm_runtime._raise_for_status 同一口径：5xx / 鉴权 / 不存在）。
_FAILOVER_STATUS_ERRORS = frozenset(
    {"InternalServerError", "AuthenticationError", "PermissionDeniedError", "NotFoundError"}
)


def _should_fail_over(exc: Exception) -> bool:
    """是否改用下一个候选（ADR-ROUTE-003）：连接阶段失败、端点被拦、5xx、鉴权失败、模型不存在。

    读超时、连接建立后的读写错误、400 / 422 / 429 与结构校验失败不换：请求已被接收
    或会在另一端同样失败，重发会让同一请求在两端重复执行。openai SDK 把 httpx 异常
    包成 ``APIConnectionError`` / ``APITimeoutError``，按 ``__cause__`` 判断。
    """
    from app.services.llm_endpoint_policy import LLMEndpointPolicyError

    cause: BaseException | None = exc
    if type(exc).__name__ in ("APIConnectionError", "APITimeoutError"):
        cause = exc.__cause__
    if isinstance(cause, (httpx.ConnectError, httpx.ConnectTimeout, LLMEndpointPolicyError)):
        return True
    return type(exc).__name__ in _FAILOVER_STATUS_ERRORS


async def _create_with_candidate(config: Any, kwargs: dict[str, Any], schema: dict) -> Any:
    """对单个候选执行（含 guided 被拒后的降级）。异常原样抛给路由层判断。"""
    global _guided_unsupported_logged
    from app.services.llm_endpoint_policy import resolve_endpoint

    safe = await resolve_endpoint(config.endpoint_url, config.profile)
    connect_timeout = 10.0
    if config.deployment == AIDeployment.local.value:
        connect_timeout = min(connect_timeout, float(settings.LLM_LOCAL_CONNECT_TIMEOUT_SECONDS))
    async with httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        mounts={},
        timeout=httpx.Timeout(120.0, connect=connect_timeout),
        transport=safe.transport(),
    ) as http_client:
        client = _get_instructor_client(config, http_client, safe.url)
        call = {**kwargs, "model": config.model_name}
        use_guided = (
            settings.LLM_GUIDED_DECODING_ENABLED
            and config.deployment == AIDeployment.local.value
        )
        if use_guided:
            try:
                return await client.chat.completions.create(
                    **call, extra_body={"guided_json": schema}
                )
            except Exception as exc:
                if not _is_guided_rejected(exc):
                    raise
                if not _guided_unsupported_logged:
                    logger.warning("vLLM guided_json 不可用，降级纯 Instructor retry: %s", exc)
                    _guided_unsupported_logged = True
        return await client.chat.completions.create(**call)


async def extract_structured(
    messages: list[dict[str, Any]],
    response_model: type[T],
    *,
    model: str | None = None,
    max_retries: int | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> T:
    """统一结构化输出入口（本机优先、服务器兜底；``model`` 只作优先提示）。"""
    from app.services.llm_route import (
        clear_route_outcome,
        cooling_notes,
        mark_available,
        mark_unavailable,
        note_served,
        plan_attempts,
    )

    # --- 熔断器检查：打开时快速失败 ---
    if _breaker is not None and _breaker.is_open:
        raise StructuredOutputError("Circuit breaker open — LLM 服务熔断中")
    clear_route_outcome()

    retries = (
        settings.LLM_STRUCTURED_MAX_RETRIES if max_retries is None else max_retries
    )
    schema = response_model.model_json_schema()
    kwargs: dict[str, Any] = {
        "messages": messages,
        "response_model": response_model,
        "max_retries": retries,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    route = await _resolve_route(model)
    planned = plan_attempts(route)
    failures: list[str] = []
    last_exc: Exception | None = None
    for candidate in planned:
        if candidate.config is None:
            failures.append(f"{candidate.label}：{candidate.error or '配置无效'}")
            last_exc = candidate.error or StructuredOutputError("模型配置无效")
            continue
        try:
            result = await _create_with_candidate(candidate.config, kwargs, schema)
        except Exception as exc:
            if not _should_fail_over(exc):
                # 不换候选的失败里，读超时之类仍按旧口径计入熔断（整条路由到此为止）。
                if _breaker is not None and _is_connection_failure(exc):
                    _breaker.record_failure()
                raise StructuredOutputError(str(exc)) from exc
            mark_unavailable(candidate.identity, str(exc) or type(exc).__name__)
            failures.append(f"{candidate.label}：{exc}")
            last_exc = exc
            continue
        mark_available(candidate.identity)
        note_served(route, candidate, attempts=tuple(failures + cooling_notes(route, planned)))
        if _breaker is not None:
            _breaker.record_success()
        return result

    if _breaker is not None and last_exc is not None and _is_connection_failure(last_exc):
        _breaker.record_failure()
    skipped = cooling_notes(route, planned)
    if len(failures) > 1 or skipped:
        message = "；".join(failures + skipped)
    else:
        message = str(last_exc or "没有可用的模型配置")
    raise StructuredOutputError(message) from last_exc
