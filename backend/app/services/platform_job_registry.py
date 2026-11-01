"""平台耐久任务执行器注册表。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.services.platform_job_service import PlatformJobClaim

ProgressReporter = Callable[[int, int | None, str | None, str | None], Awaitable[bool]]


@dataclass(frozen=True)
class ExecutorOutcome:
    result_ref: dict[str, Any] | None = None
    finalized: bool = False


Executor = Callable[[PlatformJobClaim, ProgressReporter], Awaitable[ExecutorOutcome]]

_EXECUTORS: dict[str, Executor] = {}


def register_executor(operation: str, executor: Executor) -> None:
    existing = _EXECUTORS.get(operation)
    if existing is not None and existing is not executor:
        raise RuntimeError(f"platform job executor duplicate: {operation}")
    _EXECUTORS[operation] = executor


def get_executor(operation: str) -> Executor | None:
    return _EXECUTORS.get(operation)


def registered_operations() -> tuple[str, ...]:
    return tuple(sorted(_EXECUTORS))
