"""后台 worker 唤醒注册表 —— 业务域只依赖本模块，不 import 具体 worker 实现。

🔴 2026-11-14 为什么需要它（domain-boundary 门禁 7 条 forbidden_edge 的根因）
============================================================================
`consolidation` 的 4 个 router + 2 个 service，以及 `formula_settings.propagation`，
都需要「入队后立即唤醒后台 worker」，原先直接::

    from app.workers.consol_operation_worker import wake

于是业务域反向依赖 `backend-workers`（技术实现层）。门禁判它违规是对的 ——
**业务域不该知道「唤醒」是怎么实现的**（进程内 asyncio task？外部队列？轮询？）。
而且仓库里有 3 个 worker 各有自己的 `wake()`（`consol_operation_worker` /
`ai_task_worker` / `knowledge_ocr_worker`），调用方要记住各自模块路径。

现语义：worker 在**自己的模块导入期**调 :func:`register_waker` 注册唤醒函数；
业务域只调 :func:`wake_worker(名字)`，不知道实现、也不 import worker 模块。

兼容：:func:`wake_worker` 在目标没注册时返回 ``None`` 并**不抛**，与原先
`wake()` 在无事件循环时返回 ``None`` 的契约一致（任务丢失由常驻 worker 从 DB 恢复）。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: worker 名字 -> 唤醒函数（``() -> Any``，通常返回 asyncio.Task | None）
_WAKERS: dict[str, Any] = {}

#: 已登记但**预期不注册**的 worker（测试/单进程场景下允许缺席，避免守卫恒红）
_EXPECTED_ABSENT: frozenset[str] = frozenset()


def register_waker(name: str, waker: Any) -> None:
    """worker 自注册唤醒函数（在自己的模块导入期调用）。"""
    _WAKERS[str(name)] = waker


def wake_worker(name: str):
    """唤醒指定 worker；未注册时返回 None（与旧 `wake()` 的无循环契约一致）。

    🔴 不抛异常是有意的：唤醒只是**加速**，真正的执行权由 DB claim/lease 决定
    （见 ``consol_operation_worker`` 文档头）。缺注册时靠常驻轮询兜底，不该让业务请求 500。
    """
    waker = _WAKERS.get(str(name))
    if waker is None:
        if name not in _EXPECTED_ABSENT:
            logger.debug("[worker-wake] %s 未注册唤醒函数（常驻轮询兜底）", name)
        return None
    return waker()


def registered_workers() -> tuple[str, ...]:
    """已注册的 worker 名（供启动自检 / 守卫断言「注册确实发生」）。"""
    return tuple(sorted(_WAKERS))
