"""切换链路分阶段计时（spec workpaper-sync-switch-performance · P0 / 需求 1）。

═══ 为什么要有 ═══

HTML↔OO 切换慢，但事件表 `working_paper_*_event.occurred_at` 是 PG ``now()`` = **事务开始时间**：
同一事务内的多个阶段共用一个时间戳，看不出 extract / merge / 提交 CPU 段 / 镜像各占多少。
本模块给一次请求开一个计时作用域，各处调用 :func:`mark` 记「距上一个 mark 的耗时」，
作用域退出时输出**一行**结构化日志（logger ``workpaper_sync.timing``，INFO）。

═══ 刻意的形态 ═══

* **零侵入**：没有作用域时 :func:`mark` 是 no-op —— 单测、离线脚本、预热路径里调用它不产生任何副作用。
* **只观测不判定**：不改变任何阶段顺序、不参与任何判据；耗时数字只进日志。
* **ContextVar**：``asyncio.to_thread`` 复制上下文，线程里 mark 的仍是同一个作用域对象。
* logger 单独设 INFO：全局 ``LOG_LEVEL`` 默认 WARNING，不单独设的话计时行在 dev 环境永远不可见；
  根 handler 无级别（NOTSET），因此本 logger 的 INFO 记录会进 stdout 与 ``logs/app.jsonl``。
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger("workpaper_sync.timing")
logger.setLevel(logging.INFO)

#: 日志行前缀（报告工具 / 人工 grep 用）。
TIMING_LOG_PREFIX = "[sync-timing]"


@dataclass
class TimingScope:
    """一次请求的计时轨迹。``phases`` 是 ``(阶段名, 距上一阶段毫秒)`` 的有序列表。"""

    kind: str
    labels: dict[str, str]
    started: float
    last: float
    phases: list[tuple[str, float]] = field(default_factory=list)

    def mark(self, phase: str) -> None:
        now = time.perf_counter()
        self.phases.append((str(phase), round((now - self.last) * 1000.0, 1)))
        self.last = now

    def total_ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000.0, 1)

    def summary(self, *, outcome: str) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "outcome": outcome,
            "total_ms": self.total_ms(),
            "phases": [{"phase": name, "ms": ms} for name, ms in self.phases],
            **self.labels,
        }


_CURRENT: contextvars.ContextVar[TimingScope | None] = contextvars.ContextVar(
    "workpaper_sync_timing_scope", default=None
)


@contextlib.contextmanager
def timing_scope(kind: str, **labels: Any) -> Iterator[TimingScope]:
    """开一个计时作用域；退出时（含异常路径）输出一行结构化日志。

    嵌套时内层作用域独立计时并各自输出，退出后恢复外层（ContextVar token 语义）。
    """
    now = time.perf_counter()
    scope = TimingScope(
        kind=str(kind),
        labels={str(k): str(v) for k, v in labels.items() if v is not None},
        started=now,
        last=now,
    )
    token = _CURRENT.set(scope)
    outcome = "ok"
    try:
        yield scope
    except BaseException:
        outcome = "error"
        raise
    finally:
        _CURRENT.reset(token)
        try:
            logger.info(
                "%s %s",
                TIMING_LOG_PREFIX,
                json.dumps(scope.summary(outcome=outcome), ensure_ascii=False),
            )
        except Exception:  # noqa: BLE001 - 观测失败不得影响业务结果
            pass


def mark(phase: str) -> None:
    """在当前作用域记一个阶段边界；无作用域时什么都不做。"""
    scope = _CURRENT.get()
    if scope is not None:
        scope.mark(phase)


def current_scope() -> TimingScope | None:
    """当前作用域（测试 / 调用方补标签用）；无则 ``None``。"""
    return _CURRENT.get()


__all__ = [
    "TIMING_LOG_PREFIX",
    "TimingScope",
    "current_scope",
    "mark",
    "timing_scope",
]
