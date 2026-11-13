"""E2 骨架：EventBus / 耐久任务 / SSE 配额等进程内状态的可外置接口。

目标（spec: `platform-heavy-jobs-and-capacity-closure` E2）：
    - **单 worker**（当前默认部署）保持 100% 内存实现、零改动行为；
    - **多 worker** 验证时通过 ``install_event_bus_state_adapter(...)`` 注入
      Redis / DB 实现，调用方（EventBus、platform_jobs worker、SSE 路由）零修改；
    - **真实 2/4/8 worker 零丢失 / 零重复验证**仍属 ``[ ]*``（需专用容量环境部署 +
      分布式 Locust，见其 spec tasks 的 E2 条目）。

本模块只定义**接口 + 内存默认实现 + 模块级 hook**：
    - ``EventBusStateAdapter``：抽象基类
    - ``InMemoryEventBusStateAdapter``：默认实现（当前进程内行为等价）
    - ``get_event_bus_state_adapter()`` / ``install_event_bus_state_adapter()`` /
      ``reset_event_bus_state_adapter()``：外部注入点

切流量的改动（让 ``EventBus._pending``、``platform_jobs.capacity``、SSE 配额都经过
adapter）不属本轮骨架，会在 E2 真实验证前的小 spec 里逐个替换，再由本接口做 A/B。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from uuid import UUID


__all__ = [
    "EventBusStateAdapter",
    "InMemoryEventBusStateAdapter",
    "get_event_bus_state_adapter",
    "install_event_bus_state_adapter",
    "reset_event_bus_state_adapter",
]


class EventBusStateAdapter(ABC):
    """跨 worker 状态存储抽象。

    覆盖三件事：

    1. **Debounce pending**：``EventBus._build_dedup_key`` 产生的 ``dedup_key`` →
       最近一次聚合后的 payload。单 worker 时直接用 dict；多 worker 时必须共享
       （否则同一事件会被每个 worker 各自 debounce 一次 ⇒ 下游重复派发）。
    2. **SSE per-project quota**：同一项目的 SSE 连接上限（当前进程内没显式上限，
       多 worker 时需统一计数防止总连接数无控）。接口返回 True 代表许可、False
       代表超限（调用方应拒绝新连接 + 返回 429 / 503）。
    3. **归档 stale flag（轻量 presence 类）**：预留接口不在骨架落地；业务 stale
       仍写 ORM 列（``disclosure_notes.is_stale`` 等），不在本 adapter 范围。

    每个子类**必须自己保证线程安全 / 事务一致性**；本抽象基类不加锁。
    """

    @abstractmethod
    async def get_pending_payload(self, dedup_key: str) -> Optional[Any]:
        """读当前 dedup_key 聚合的 pending payload；None = 无未发布事件。"""

    @abstractmethod
    async def set_pending_payload(self, dedup_key: str, payload: Any) -> None:
        """覆盖 dedup_key 对应的 pending payload（EventBus debounce 合并后写入）。"""

    @abstractmethod
    async def pop_pending_payload(self, dedup_key: str) -> Optional[Any]:
        """取出并清除 dedup_key 的 pending payload；用于 dispatch 开始时。"""

    @abstractmethod
    async def acquire_sse_quota(self, project_id: UUID, max_per_project: int) -> bool:
        """为 project 的新 SSE 订阅申请一个配额；超限返回 False。"""

    @abstractmethod
    async def release_sse_quota(self, project_id: UUID) -> None:
        """订阅断开时释放一个配额；在 0 处多调应是幂等 no-op。"""


class InMemoryEventBusStateAdapter(EventBusStateAdapter):
    """默认内存实现：单 worker 跑它的全部值为真 —— 直接 dict + 计数器。

    等价于 ``EventBus._pending`` + ``_sse_queues`` 的当前行为；改用多 worker 时
    换成 Redis / DB 实现。**本实现不是线程安全**：asyncio 单循环下够用，跨线程
    或多进程需要换另一套实现。
    """

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}
        self._sse_counts: dict[UUID, int] = {}

    async def get_pending_payload(self, dedup_key: str) -> Optional[Any]:
        return self._pending.get(dedup_key)

    async def set_pending_payload(self, dedup_key: str, payload: Any) -> None:
        self._pending[dedup_key] = payload

    async def pop_pending_payload(self, dedup_key: str) -> Optional[Any]:
        return self._pending.pop(dedup_key, None)

    async def acquire_sse_quota(self, project_id: UUID, max_per_project: int) -> bool:
        if max_per_project <= 0:
            return False
        current = self._sse_counts.get(project_id, 0)
        if current >= max_per_project:
            return False
        self._sse_counts[project_id] = current + 1
        return True

    async def release_sse_quota(self, project_id: UUID) -> None:
        current = self._sse_counts.get(project_id, 0)
        if current > 0:
            self._sse_counts[project_id] = current - 1


# ---------------------------------------------------------------------------
# 模块级单例 + 注入 hook
# ---------------------------------------------------------------------------


_installed_adapter: EventBusStateAdapter = InMemoryEventBusStateAdapter()


def get_event_bus_state_adapter() -> EventBusStateAdapter:
    """获取当前已安装的 adapter；默认是 ``InMemoryEventBusStateAdapter``。"""
    return _installed_adapter


def install_event_bus_state_adapter(adapter: EventBusStateAdapter) -> None:
    """安装 adapter；本地默认内存，部署多 worker 时按需换 Redis / DB。

    必须在**任何 EventBus publish / subscribe 之前**（进程启动期）调用；中途换
    adapter 会丢掉 pending debounce 窗口（无原子迁移），不做"动态切换"语义。
    """
    global _installed_adapter
    _installed_adapter = adapter


def reset_event_bus_state_adapter() -> None:
    """测试用：恢复到全新的 ``InMemoryEventBusStateAdapter``。"""
    global _installed_adapter
    _installed_adapter = InMemoryEventBusStateAdapter()
