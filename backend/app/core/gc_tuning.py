"""进程级 GC 调优（spec writeback-followup-issue-closure R9 / P12）。

实测（同一进程里重放重药安徽 D2 的同一条真实 OO→HTML apply，合并 / 新内容版本摘要逐项相同）：

| 配置 | 冷注册那一轮 | 稳态 apply | 每次 apply 的 GC | gen2 单次最长 |
|---|---|---|---|---|
| 默认阈值 (700, 10, 10) | 48.0 s（gen2 共 14.4 s） | 8.0~8.1 s | 2.1 s | 0.23 s |
| 阈值 (10000, 10, 10) + 预热后 freeze | 37.8 s（gen2 共 4.0 s） | 6.0 s | 0.3 s | 0.10 s |

原因：进程里约 34 万个长寿对象（注册清册、模板结构、契约、模块），默认阈值下全量收集频繁、
且每次都把它们重扫一遍；这些对象在启动预热之后不再变化。

两步：

1. :func:`configure_gc` —— 冷注册之前调用：gen0 阈值 700 → 10000（全量收集次数随之降），
   gen1 / gen2 不变；
2. :func:`run_then_freeze` —— 包住启动预热：预热结束（成功或失败）后 ``gc.collect()`` 清掉
   预热期的临时垃圾，再 ``gc.freeze()``，之后的收集不再扫这批对象。

代价：冻结那一刻还活着的对象，日后即使不再被引用也不会被**循环**回收（引用计数照常释放）；
它们本就是进程寿命的缓存。``collect`` 那一次会停一下事件循环（实测约 0.5 s），只在启动预热
结束时发生一次。环境变量 ``GT_GC_TUNING=0`` 关闭两步（回到解释器默认行为）。
"""

from __future__ import annotations

import asyncio
import gc
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Final
from weakref import WeakKeyDictionary

__all__ = [
    "GC_THRESHOLD",
    "configure_gc",
    "freeze_when_idle",
    "gc_tuning_enabled",
    "get_last_freeze_report",
    "heavy_phase",
    "run_then_freeze",
]

logger = logging.getLogger("audit_platform")

#: (gen0, gen1, gen2)。只抬 gen0；gen1 / gen2 与解释器默认相同。
GC_THRESHOLD: Final[tuple[int, int, int]] = (10_000, 10, 10)

# 每个事件循环一把锁：pytest 会创建多个 loop，不能让某个已关闭 loop 绑定的 Lock 污染下一例。
_HEAVY_LOCKS: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()
_LAST_FREEZE_REPORT: dict[str, object] = {
    "status": "not_run",
    "wait_s": 0.0,
    "requeues": 0,
    "collected": 0,
    "duration_ms": 0.0,
    "freeze_count": 0,
}


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _heavy_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _HEAVY_LOCKS.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _HEAVY_LOCKS[loop] = lock
    return lock


@asynccontextmanager
async def heavy_phase(name: str) -> AsyncIterator[None]:
    """串行化后台 CPU/GIL 重阶段；不用于普通请求。"""
    lock = _heavy_lock()
    waited = time.perf_counter()
    await lock.acquire()
    wait_ms = (time.perf_counter() - waited) * 1000
    if wait_ms >= 100:
        logger.info("[启动] 重阶段 %s 等待前序阶段 %.0fms", name, wait_ms)
    try:
        yield
    finally:
        lock.release()


def get_last_freeze_report() -> dict[str, object]:
    return dict(_LAST_FREEZE_REPORT)


def gc_tuning_enabled() -> bool:
    return os.environ.get("GT_GC_TUNING", "1").strip().lower() not in {"0", "false", "no", "off"}


def configure_gc() -> bool:
    """抬高 gen0 阈值（幂等）。返回是否生效。"""
    if not gc_tuning_enabled():
        return False
    gc.set_threshold(*GC_THRESHOLD)
    return True


async def freeze_when_idle(stop_event: asyncio.Event | None = None) -> bool:
    """只在 HTTP in-flight 连续为 0 的空闲窗口做一次 full collect + freeze。

    GC 是进程全局且持 GIL，``to_thread`` 不能消除 stop-the-world。等待一轮超时后退到队尾再试，
    **绝不**因超时强跑；拿到重阶段锁后再次检查 in-flight，堵住「刚判空闲就进请求」竞态。

    判空闲用 ``value_excluding_streams()``：SSE 长连接在 in-flight 里一挂就是几十分钟，
    用 ``value()`` 的话只要有一个浏览器标签订阅事件流，freeze 就永不发生（现场实测
    wait_s=415.5 / requeues=12 / freeze_count=0）。GC 停顿只影响请求延迟，
    而 SSE 本身是长轮询语义、不计入延迟预算，故可排除。
    """
    from app.middleware.inflight import inflight_counter

    poll_s = _env_float("GT_GC_IDLE_POLL_S", 0.05, minimum=0.001)
    window_s = _env_float("GT_GC_IDLE_WINDOW_S", 0.5, minimum=0.0)
    timeout_s = _env_float("GT_GC_IDLE_TIMEOUT_S", 30.0, minimum=poll_s)
    backoff_s = _env_float("GT_GC_IDLE_RETRY_S", 5.0, minimum=0.0)
    overall_started = time.perf_counter()
    requeues = 0

    while stop_event is None or not stop_event.is_set():
        deadline = time.perf_counter() + timeout_s
        idle_since: float | None = None
        while time.perf_counter() < deadline:
            if stop_event is not None and stop_event.is_set():
                _LAST_FREEZE_REPORT.update(status="cancelled", requeues=requeues)
                return False
            now = time.perf_counter()
            if inflight_counter.value_excluding_streams() == 0:
                idle_since = now if idle_since is None else idle_since
                if now - idle_since >= window_s:
                    break
            else:
                idle_since = None
            await asyncio.sleep(poll_s)
        else:
            requeues += 1
            _LAST_FREEZE_REPORT.update(
                status="requeued",
                wait_s=round(time.perf_counter() - overall_started, 3),
                requeues=requeues,
            )
            logger.info(
                "[启动] GC 等待连续空闲 %.1fs 超时（在途 %d，其中 SSE %d 已排除），%.1fs 后重排",
                window_s, inflight_counter.value(), inflight_counter.streaming(), backoff_s,
            )
            await asyncio.sleep(backoff_s)
            continue

        async with heavy_phase("gc-freeze"):
            # 获取锁期间可能来了请求；二次检查失败就重新等待完整空闲窗口。
            if inflight_counter.value_excluding_streams() != 0:
                requeues += 1
                continue
            started = time.perf_counter()
            try:
                collected = gc.collect()
                gc.freeze()
            except Exception as exc:  # noqa: BLE001 - 调优失败不影响服务
                _LAST_FREEZE_REPORT.update(
                    status="failed",
                    wait_s=round(time.perf_counter() - overall_started, 3),
                    requeues=requeues,
                )
                logger.warning("[启动] GC 冻结失败（忽略）：%s", exc)
                return False
            duration_ms = (time.perf_counter() - started) * 1000
            freeze_count = gc.get_freeze_count()
            _LAST_FREEZE_REPORT.update(
                status="ok",
                wait_s=round(started - overall_started, 3),
                requeues=requeues,
                collected=collected,
                duration_ms=round(duration_ms, 1),
                freeze_count=freeze_count,
            )
            logger.warning(
                "[启动] GC 在连续空闲窗口后冻结长寿对象 %d 个（回收 %d，停顿 %.1fms，重排 %d 次）",
                freeze_count, collected, duration_ms, requeues,
            )
            return True
    _LAST_FREEZE_REPORT.update(status="cancelled", requeues=requeues)
    return False


async def run_then_freeze(
    work: Callable[[], Awaitable[None]],
    *,
    stop_event: asyncio.Event | None = None,
) -> None:
    """串行跑预热，再等待安全空闲窗口 collect/freeze。

    收的是可调用对象而不是协程：任务开跑前被取消时不会留下未 await 协程。预热失败仍尝试
    空闲冻结并原样重抛；关闭取消不冻结。预热本身也走重阶段锁，不与 event replay、lazy
    verifier、OpenAPI 生成并跑。
    """
    try:
        async with heavy_phase("workpaper-prewarm"):
            await work()
    finally:
        task = asyncio.current_task()
        cancelling = task is not None and task.cancelling() > 0
        if gc_tuning_enabled() and not cancelling:
            await freeze_when_idle(stop_event)
