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
from collections.abc import Awaitable, Callable
from typing import Final

__all__ = ["GC_THRESHOLD", "configure_gc", "gc_tuning_enabled", "run_then_freeze"]

logger = logging.getLogger("audit_platform")

#: (gen0, gen1, gen2)。只抬 gen0；gen1 / gen2 与解释器默认相同。
GC_THRESHOLD: Final[tuple[int, int, int]] = (10_000, 10, 10)


def gc_tuning_enabled() -> bool:
    return os.environ.get("GT_GC_TUNING", "1").strip().lower() not in {"0", "false", "no", "off"}


def configure_gc() -> bool:
    """抬高 gen0 阈值（幂等）。返回是否生效。"""
    if not gc_tuning_enabled():
        return False
    gc.set_threshold(*GC_THRESHOLD)
    return True


async def run_then_freeze(work: Callable[[], Awaitable[None]]) -> None:
    """跑完 ``work()``（启动预热）之后，收集一次并冻结此刻存活的对象。

    收的是可调用对象而不是协程：本任务在开跑之前就被取消时（启动随即关闭），不会留下一个
    从未 await 的协程。预热失败也照样冻结（已建好的部分同样是长寿对象）；关闭阶段的取消原样
    抛出、不冻结。冻结本身出错只记日志，绝不影响预热的结果。
    """
    try:
        await work()
    finally:
        task = asyncio.current_task()
        cancelling = task is not None and task.cancelling() > 0
        if gc_tuning_enabled() and not cancelling:
            try:
                collected = gc.collect()
                gc.freeze()
                logger.warning(
                    "[启动] GC 预热后冻结长寿对象 %d 个（本次回收 %d 个）", gc.get_freeze_count(), collected
                )
            except Exception as exc:  # noqa: BLE001 - 调优失败不影响服务
                logger.warning("[启动] GC 冻结失败（忽略）：%s", exc)
