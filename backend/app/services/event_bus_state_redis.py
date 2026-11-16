"""E2：`EventBusStateAdapter` 的 Redis 实现（多 worker 部署时注入）。

spec: `platform-heavy-jobs-and-capacity-closure` E2。

## 只实现能真正外置的那一面

`EventBusStateAdapter` 覆盖 pending 与 SSE 配额两件事，但**只有配额能外置**：

- **配额**只是「项目 → 当前连接数」的整数计数，天然可以放 Redis。
- **pending** 存的是 `asyncio.TimerHandle`（本进程事件循环句柄），无法序列化到 Redis。
  这一半在 `event_bus.py` 里已如实登记为「不在可外置范围」，本模块不去假装实现它 ——
  `get_pending_payload` / `set_pending_payload` / `pop_pending_payload` 直接抛
  `NotImplementedError`，让「谁在多 worker 下误用了它」当场暴露，而不是静默丢事件。

## 为什么用 Lua 而不是 GET/SET

`INCR` + 超限回退是两步操作：并发下两个请求可能都读到 `n-1` 然后都 `INCR` 到 `n`，
双双通过 ⇒ 上限失效。这里用一段 Lua 把「读 → 判断 → 自增」做成原子的：

```lua
local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
if cur >= tonumber(ARGV[1]) then return 0 end
redis.call('INCR', KEYS[1])
return 1
```

`release` 同样要防止减到负数（多调一次释放不应把计数打成 -1，否则下一次
`acquire` 会多放一个连接进来）：

```lua
local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
if cur <= 0 then return 0 end
redis.call('DECR', KEYS[1])
return 1
```

## TTL 是必须的

进程崩溃不会调 `release`。没有 TTL 时计数只增不减，最终把所有项目永久锁死。
这里给每个项目的 key 一个可配置 TTL（默认 1 小时，远大于单条 SSE 连接寿命），
崩溃留下的计数会自动过期回收。**代价**：正常长连接超过 TTL 时计数会提前归零，
因此 TTL 必须显著大于最长连接时长；运维按实际部署调整。
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from app.services.event_bus_state_adapter import EventBusStateAdapter

logger = logging.getLogger(__name__)

__all__ = ["RedisEventBusStateAdapter", "QUOTA_KEY_PREFIX", "DEFAULT_QUOTA_TTL_SECONDS"]

#: 配额 key 前缀；项目 id 拼在后面
QUOTA_KEY_PREFIX = "gt:eventbus:sse_quota:"

#: 配额 key 的 TTL（秒）。进程崩溃不会调 release，靠它自动回收。
DEFAULT_QUOTA_TTL_SECONDS = 3600

#: 原子申请：cur >= max 时返回 0，否则 INCR 并返回 1
_ACQUIRE_LUA = """
local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
if cur >= tonumber(ARGV[1]) then return 0 end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
"""

#: 原子释放：cur <= 0 时 no-op（幂等），否则 DECR
_RELEASE_LUA = """
local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
if cur <= 0 then return 0 end
redis.call('DECR', KEYS[1])
return 1
"""


class RedisEventBusStateAdapter(EventBusStateAdapter):
    """跨 worker 的 SSE 配额实现；pending 三方法显式不支持。

    Args:
        redis: 已连接的 async Redis 客户端（`redis.asyncio.Redis`）。不在此处建连接，
            由调用方决定连接池与生命周期。
        quota_ttl_seconds: 配额 key 的 TTL。必须显著大于最长 SSE 连接时长。
    """

    def __init__(self, redis: Any, *, quota_ttl_seconds: int = DEFAULT_QUOTA_TTL_SECONDS) -> None:
        if redis is None:
            raise ValueError("RedisEventBusStateAdapter 需要一个已连接的 async Redis 客户端")
        if quota_ttl_seconds <= 0:
            raise ValueError(f"quota_ttl_seconds 必须为正，实际 {quota_ttl_seconds}")
        self._redis = redis
        self._ttl = int(quota_ttl_seconds)

    @staticmethod
    def _key(project_id: UUID) -> str:
        return f"{QUOTA_KEY_PREFIX}{project_id}"

    # ── pending：显式不支持 ──

    async def get_pending_payload(self, dedup_key: str) -> Optional[Any]:
        raise NotImplementedError(
            "debounce pending 存的是本进程 asyncio.TimerHandle，无法外置到 Redis；"
            "多 worker 下不要调用本方法（见 event_bus.py 的架构约束说明）"
        )

    async def set_pending_payload(self, dedup_key: str, payload: Any) -> None:
        raise NotImplementedError(
            "debounce pending 存的是本进程 asyncio.TimerHandle，无法外置到 Redis"
        )

    async def pop_pending_payload(self, dedup_key: str) -> Optional[Any]:
        raise NotImplementedError(
            "debounce pending 存的是本进程 asyncio.TimerHandle，无法外置到 Redis"
        )

    # ── 配额：原子实现 ──

    async def acquire_sse_quota(self, project_id: UUID, max_per_project: int) -> bool:
        """原子申请一个配额；`max_per_project <= 0` 视为不限（与内存实现不同）。

        🔴 与内存实现的口径差异：`InMemoryEventBusStateAdapter` 对 `<= 0` 返回 False
        （即「上限 0 = 拒绝一切」），而生产默认 `max_per_project=0` 表示**不限**。
        本实现按生产语义处理 `<= 0` 为「不限」，避免把「未配置上限」误当成「禁止连接」。
        """
        if max_per_project <= 0:
            return True
        try:
            allowed = await self._redis.eval(
                _ACQUIRE_LUA, 1, self._key(project_id), int(max_per_project), self._ttl,
            )
        except Exception as exc:  # noqa: BLE001 — 配额后端故障不能阻断事件流
            logger.warning("SSE 配额申请失败（降级放行）project=%s: %s", project_id, exc)
            return True
        return bool(int(allowed))

    async def release_sse_quota(self, project_id: UUID) -> None:
        """幂等释放；减到 0 即止，不会打成负数。"""
        try:
            await self._redis.eval(_RELEASE_LUA, 1, self._key(project_id))
        except Exception as exc:  # noqa: BLE001 — 释放失败只记录（TTL 会兜底回收）
            logger.warning("SSE 配额释放失败 project=%s: %s", project_id, exc)

    async def current_quota(self, project_id: UUID) -> int:
        """现读某项目当前占用（诊断 / 运维用；不参与准入判定）。"""
        raw = await self._redis.get(self._key(project_id))
        return int(raw or 0)
