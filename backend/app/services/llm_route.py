"""本机优先路由执行：故障转移、冷却期与实际服务模型记录。

候选的解析与排序在 ``llm_runtime.resolve_route``；本模块只负责：按顺序试、什么错误换下一个
（``LLMRuntimeError.failover``，ADR-ROUTE-003）、失败的候选冷却多久（ADR-ROUTE-004）、
最终是谁回答的（ADR-ROUTE-008）。单个候选的 HTTP 调用仍只有 ``llm_runtime`` 那一份。

冷却记录只在进程内：多 worker 各自探测，代价是每个 worker 在冷却期首个请求多一次失败尝试。
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from app.core.config import settings
from app.services.llm_runtime import (
    LLMRuntimeError,
    RouteCandidate,
    chat_stream,
    chat_sync,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 候选健康记录（冷却期）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateMark:
    """某个候选最近一次实际调用的结果；``until`` 为冷却截止（monotonic，成功时为 0）。"""

    ok: bool
    reason: str
    at: float
    until: float


_MARKS: dict[str, CandidateMark] = {}


def _cooldown_seconds() -> float:
    return max(0.0, float(settings.LLM_ROUTE_COOLDOWN_SECONDS))


def mark_unavailable(identity: str, reason: str) -> None:
    _MARKS[identity] = CandidateMark(
        False, reason, time.time(), time.monotonic() + _cooldown_seconds()
    )


def mark_available(identity: str) -> None:
    _MARKS[identity] = CandidateMark(True, "", time.time(), 0.0)


def candidate_mark(identity: str) -> CandidateMark | None:
    return _MARKS.get(identity)


def is_cooling(identity: str) -> bool:
    mark = _MARKS.get(identity)
    return bool(mark and not mark.ok and time.monotonic() < mark.until)


def reset_route_health() -> None:
    """测试与运维用：清空进程内冷却记录。"""
    _MARKS.clear()


def plan_attempts(route: list[RouteCandidate]) -> list[RouteCandidate]:
    """冷却中的候选在仍有其他候选时跳过；全部在冷却期则按顺序全部尝试。"""
    fresh = [candidate for candidate in route if not is_cooling(candidate.identity)]
    return fresh or list(route)


def route_identity(route: list[RouteCandidate]) -> str:
    """整条路由的身份（熔断器按它绑定，ADR-ROUTE-007）。"""
    return "||".join(candidate.identity for candidate in route)


def cooling_notes(route: list, planned: list) -> list[str]:
    """本次因冷却跳过的候选（成功时写进 attempts，全部失败时并入报错，避免只报一半原因）。

    LLM 与 OCR 候选共用：只依赖 ``identity`` / ``label``。
    """
    notes: list[str] = []
    for candidate in route:
        if candidate not in planned:
            mark = candidate_mark(candidate.identity)
            notes.append(f"{candidate.label}：冷却中（{mark.reason if mark else '最近一次调用失败'}）")
    return notes


# ---------------------------------------------------------------------------
# 实际服务模型（同一请求上下文内可读）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteOutcome:
    model_name: str
    deployment: str
    model_id: UUID | None
    fallback_used: bool
    attempts: tuple[str, ...] = ()


_OUTCOME: ContextVar[RouteOutcome | None] = ContextVar("llm_route_outcome", default=None)


def last_route_outcome() -> RouteOutcome | None:
    """当前上下文最近一次成功的路由调用由谁回答；失败或尚未调用时为 None。"""
    return _OUTCOME.get()


def served_model_label(default: str | None = None) -> str:
    """记录「生成模型」用：优先取实际服务的模型名，没有时回落 ``default`` / `.env` 默认值。"""
    outcome = _OUTCOME.get()
    if outcome is not None:
        return outcome.model_name
    return default or settings.DEFAULT_CHAT_MODEL


def clear_route_outcome() -> None:
    """新一次调用开始：清掉上一次的结果，避免失败时被读到旧模型名。"""
    _OUTCOME.set(None)


def note_served(
    route: list[RouteCandidate], served: RouteCandidate, *, attempts: tuple[str, ...] = ()
) -> None:
    """不经 ``route_chat_*`` 执行的调用方（如结构化输出）记录由谁回答。"""
    fallback = bool(route) and served is not route[0]
    _OUTCOME.set(
        RouteOutcome(served.model_name, served.deployment, served.model_id, fallback, attempts)
    )


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


def _invalid_error(candidate: RouteCandidate) -> LLMRuntimeError:
    return candidate.error or LLMRuntimeError(
        "invalid_model_config", "模型配置无效", kind="config"
    )


def _record_failure(candidate: RouteCandidate, exc: LLMRuntimeError) -> None:
    mark_unavailable(candidate.identity, str(exc))


def _record_success(
    route: list[RouteCandidate],
    planned: list[RouteCandidate],
    served: RouteCandidate,
    failures: list[tuple[RouteCandidate, LLMRuntimeError]],
) -> None:
    mark_available(served.identity)
    notes = [f"{candidate.label}：{exc}" for candidate, exc in failures]
    notes.extend(cooling_notes(route, planned))
    fallback = bool(route) and served is not route[0]
    if failures:
        logger.warning(
            "LLM 路由兜底：%s 不可用，本次由 %s 回答",
            "、".join(candidate.label for candidate, _ in failures),
            served.label,
        )
    _OUTCOME.set(
        RouteOutcome(served.model_name, served.deployment, served.model_id, fallback, tuple(notes))
    )


def _exhausted(
    failures: list[tuple[RouteCandidate, LLMRuntimeError]],
    skipped: tuple[str, ...] | list[str] = (),
) -> LLMRuntimeError:
    """全部候选失败：单候选原样抛出（原因与旧行为一致）；多候选逐个列原因（含冷却跳过的）。"""
    if not failures:
        return LLMRuntimeError("no_model", "没有可用的模型配置", kind="config")
    if len(failures) == 1 and not skipped:
        return failures[0][1]
    last = failures[-1][1]
    detail = "；".join(
        [f"{candidate.label}：{exc}" for candidate, exc in failures] + list(skipped)
    )
    return LLMRuntimeError(last.code, detail, kind=last.kind)


async def route_chat_sync(
    route: list[RouteCandidate],
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    enable_thinking: bool | None = None,
    timeout: float = 30.0,
) -> str:
    """按路由顺序调用；只有可转移错误才换下一个候选。"""
    _OUTCOME.set(None)
    planned = plan_attempts(route)
    failures: list[tuple[RouteCandidate, LLMRuntimeError]] = []
    for candidate in planned:
        if candidate.config is None:
            failures.append((candidate, _invalid_error(candidate)))
            continue
        try:
            text = await chat_sync(
                candidate.config, messages, temperature=temperature, max_tokens=max_tokens,
                enable_thinking=enable_thinking, timeout=timeout,
            )
        except LLMRuntimeError as exc:
            if not exc.failover:
                raise
            _record_failure(candidate, exc)
            failures.append((candidate, exc))
            continue
        _record_success(route, planned, candidate, failures)
        return text
    raise _exhausted(failures, cooling_notes(route, planned))


async def route_chat_stream(
    route: list[RouteCandidate],
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    enable_thinking: bool | None = None,
    timeout: float = 90.0,
) -> AsyncIterator[str]:
    """流式版本：首个片段输出前才转移；已输出后失败按原样抛出（不能把两段回答拼在一起）。"""
    _OUTCOME.set(None)
    planned = plan_attempts(route)
    failures: list[tuple[RouteCandidate, LLMRuntimeError]] = []
    for candidate in planned:
        if candidate.config is None:
            failures.append((candidate, _invalid_error(candidate)))
            continue
        started = False
        try:
            async for chunk in chat_stream(
                candidate.config, messages, temperature=temperature, max_tokens=max_tokens,
                enable_thinking=enable_thinking, timeout=timeout,
            ):
                started = True
                yield chunk
        except LLMRuntimeError as exc:
            if started or not exc.failover:
                raise
            _record_failure(candidate, exc)
            failures.append((candidate, exc))
            continue
        _record_success(route, planned, candidate, failures)
        return
    raise _exhausted(failures, cooling_notes(route, planned))
