"""重任务通道的统一排队 / 执行计量（spec platform-heavy-jobs-and-capacity-closure 任务 0.2）。

LibreOffice 池（批 A 的 A5）和账表导入 spool admission 各自已有队列上限与快照，本模块补上
剩下两条真实通道，并给 health / Prometheus 一个统一读法：

``LLM_SLOT``
    绑定的是**同一个** ``asyncio.Semaphore`` 实例：``llm_client._llm_semaphore`` 与
    ``ai_chat.native_engine`` 的流式回答都持它。本模块只在它外面计量，不另开第二个
    信号量，也不改变 ``_value`` 语义（``native_engine`` 的模块文档与两条既有守卫都
    依赖这一点）。并发上限的唯一来源是本模块的 ``LLM_MAX_CONCURRENCY``。

``OCR_SLOT``
    OCR **没有**准入队列：``unified_ocr_service`` 走事件循环默认线程池，
    ``ocr_service_v2`` 走自己的 4 线程池，平台从未给 OCR 设过并发上限。因此它的
    ``waiting`` 恒为 0 **不是**「测到没有排队」，而是「不存在准入队列」——快照用
    ``bounded=False`` 显式声明，禁止被读成已限流。真要给 OCR 加上限时，给它绑一个
    semaphore 即可，守卫会要求同步改掉这条声明。

两类通道都记录排队时长与执行时长的**分布**（Histogram），不用平均值掩盖长尾（R1.4）。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

try:
    from prometheus_client import Gauge, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover - 未装 prometheus_client 时退化为空实现
    PROMETHEUS_AVAILABLE = False

    class _MetricStub:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def set(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

    Gauge = Histogram = _MetricStub  # type: ignore[misc,assignment]


_WAIT_BUCKETS = (0.005, 0.025, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120)
_RUN_BUCKETS = (0.05, 0.25, 1, 2, 5, 10, 30, 60, 120, 300, 600)

SLOT_QUEUE_DEPTH = Gauge(
    "platform_slot_queue_depth",
    "Requests waiting for a process-local capacity slot",
    labelnames=("slot",),
)
SLOT_ACTIVE = Gauge(
    "platform_slot_active",
    "Requests currently holding a process-local capacity slot",
    labelnames=("slot",),
)
SLOT_OLDEST_WAIT_SECONDS = Gauge(
    "platform_slot_oldest_wait_seconds",
    "Age of the oldest request waiting for a capacity slot",
    labelnames=("slot",),
)
SLOT_OLDEST_ACTIVE_SECONDS = Gauge(
    "platform_slot_oldest_active_seconds",
    "Age of the oldest in-flight request holding a capacity slot",
    labelnames=("slot",),
)
SLOT_WAIT_SECONDS = Histogram(
    "platform_slot_queue_wait_seconds",
    "Time spent waiting for a capacity slot",
    labelnames=("slot",),
    buckets=_WAIT_BUCKETS,
)
SLOT_RUN_SECONDS = Histogram(
    "platform_slot_run_seconds",
    "Execution time while holding a capacity slot",
    labelnames=("slot",),
    buckets=_RUN_BUCKETS,
)

_REGISTRY: dict[str, "SlotTracker"] = {}


class SlotTracker:
    """一条重任务通道的排队与执行计量。

    ``semaphore`` 与 ``concurrency_limit`` 必须同时给或同时省略：省略即声明该通道
    没有准入控制，``use()`` 不会排队，只计执行时长与在飞数。
    """

    def __init__(
        self,
        name: str,
        *,
        semaphore: asyncio.Semaphore | None = None,
        concurrency_limit: int | None = None,
        register: bool = True,
    ) -> None:
        if (semaphore is None) != (concurrency_limit is None):
            raise ValueError("semaphore 与 concurrency_limit 必须同时提供或同时省略")
        if register and name in _REGISTRY:
            raise RuntimeError(f"capacity slot 重复注册：{name}")
        self.name = name
        self.semaphore = semaphore
        self.concurrency_limit = concurrency_limit
        self._waiting: dict[int, float] = {}
        self._active: dict[int, float] = {}
        self._sequence = 0
        if register:
            _REGISTRY[name] = self

    @property
    def bounded(self) -> bool:
        return self.semaphore is not None

    @asynccontextmanager
    async def use(self) -> AsyncIterator[None]:
        """取槽（无上限则直接进入）→ 执行 → 归还，并记录两段时长。"""
        token = self._sequence = self._sequence + 1
        if self.semaphore is not None:
            queued_at = time.perf_counter()
            self._waiting[token] = queued_at
            self._publish()
            try:
                await self.semaphore.acquire()
            finally:
                # 取消发生在等待期间时只退出队列：没拿到许可就绝不 release。
                self._waiting.pop(token, None)
                self._publish()
            SLOT_WAIT_SECONDS.labels(slot=self.name).observe(
                max(0.0, time.perf_counter() - queued_at)
            )
        entered_at = time.perf_counter()
        self._active[token] = entered_at
        self._publish()
        try:
            yield
        finally:
            self._active.pop(token, None)
            if self.semaphore is not None:
                self.semaphore.release()
            SLOT_RUN_SECONDS.labels(slot=self.name).observe(
                max(0.0, time.perf_counter() - entered_at)
            )
            self._publish()

    def snapshot(self) -> dict[str, object]:
        now = time.perf_counter()
        return {
            "bounded": self.bounded,
            "concurrency_limit": self.concurrency_limit,
            "active": len(self._active),
            "waiting": len(self._waiting),
            "oldest_wait_seconds": round(_oldest(self._waiting, now), 3),
            "oldest_active_seconds": round(_oldest(self._active, now), 3),
        }

    def _publish(self) -> None:
        now = time.perf_counter()
        SLOT_QUEUE_DEPTH.labels(slot=self.name).set(len(self._waiting))
        SLOT_ACTIVE.labels(slot=self.name).set(len(self._active))
        SLOT_OLDEST_WAIT_SECONDS.labels(slot=self.name).set(_oldest(self._waiting, now))
        SLOT_OLDEST_ACTIVE_SECONDS.labels(slot=self.name).set(_oldest(self._active, now))


def _oldest(entries: Mapping[int, float], now: float) -> float:
    return max(0.0, now - min(entries.values())) if entries else 0.0


#: LLM 并发许可的唯一来源。调高对话并发改这里一处，不要在别处另开信号量。
LLM_MAX_CONCURRENCY = 5
LLM_SLOT = SlotTracker(
    "llm",
    semaphore=asyncio.Semaphore(LLM_MAX_CONCURRENCY),
    concurrency_limit=LLM_MAX_CONCURRENCY,
)
#: OCR 无准入上限，见模块文档。
OCR_SLOT = SlotTracker("ocr")


def slot_snapshots() -> dict[str, dict[str, object]]:
    """全部已注册通道的只读快照（health 用；不做任何 I/O）。"""
    return {name: tracker.snapshot() for name, tracker in sorted(_REGISTRY.items())}


__all__ = [
    "LLM_MAX_CONCURRENCY",
    "LLM_SLOT",
    "OCR_SLOT",
    "PROMETHEUS_AVAILABLE",
    "SlotTracker",
    "slot_snapshots",
]
