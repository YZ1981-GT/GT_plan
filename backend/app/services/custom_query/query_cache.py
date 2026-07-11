"""QueryCache — 高级查询短 TTL Redis 缓存（advanced-query-module R12）。

设计对应 design.md Components §9 与 Data Models §4：

- 缓存键 = ``aqm:cache:{sha256(canonical(query_def))}:{project_id}:{accessible_scope_sig}``
  （R12.1 / R12.5，不跨项目、不跨可访问范围复用）。
- 命中未过期直接返回，服务端 ≤ 50ms（R12.2）；TTL 到期失效并重建（R12.4）。
- 可缓存判定：同一 TTL 窗口内重复次数 ≥ 阈值（默认 5，范围 1–1000）才写缓存（R12.1）。
- 缓存击穿保护（R12.6）：``SET NX PX`` 分布式锁 + 进程内 ``asyncio`` 单飞（in-flight
  task 复用）兜底，同键并发仅一次底层 compute，其余等待复用。
- Redis 降级（R12.7）：不可用 → 直接执行 compute 返回正确结果 + 记录一次告警，
  不向调用方报错（复用 ``audit_logger`` 的 Redis ping 降级范式）。

本模块仅消费平台既有 Redis 客户端（``app.core.redis``），不新造连接。
compute 回调应返回 JSON 可序列化的值（如 ``QueryResult`` 的 dict 形态）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# 键命名空间（design Data Models §4）
CACHE_PREFIX = "aqm:cache:"
LOCK_PREFIX = "aqm:lock:"
COUNT_PREFIX = "aqm:cnt:"

# TTL 默认 30s，可配范围 5–300s（R12.1）
DEFAULT_TTL = 30
MIN_TTL = 5
MAX_TTL = 300

# 可缓存阈值默认 5，范围 1–1000（R12.1）
DEFAULT_CACHE_THRESHOLD = 5
MIN_THRESHOLD = 1
MAX_THRESHOLD = 1000

# 分布式锁等待复用时的轮询参数（缓存击穿保护）
_POLL_INTERVAL = 0.02  # 20ms
_POLL_MAX_WAIT = 5.0  # 最长等待另一持锁者产出结果的时间上限（秒）

# 释放锁的原子 Lua（仅当 token 匹配时删除，避免误删他人锁）
_UNLOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class QueryCache:
    """高级查询结果的短 TTL Redis 缓存 + 单飞 + 降级。"""

    def __init__(
        self,
        *,
        default_ttl: int = DEFAULT_TTL,
        cache_threshold: int = DEFAULT_CACHE_THRESHOLD,
    ) -> None:
        self._default_ttl = _clamp(default_ttl, MIN_TTL, MAX_TTL)
        self._cache_threshold = _clamp(cache_threshold, MIN_THRESHOLD, MAX_THRESHOLD)
        # 进程内单飞：同键并发复用同一 in-flight task
        self._inflight: dict[str, asyncio.Task] = {}
        self._inflight_guard = asyncio.Lock()
        self._redis_available: bool | None = None  # None = 未检测

    # ------------------------------------------------------------------ keys

    def cache_key(self, query_def: dict, project_id: str, scope_sig: str) -> str:
        """构造缓存键 ``aqm:cache:{hash}:{project_id}:{scope_sig}``。

        ``canonical_query_def`` 使用键排序的稳定序列化，保证等价查询定义（键顺序
        无关）产生一致哈希（R12.1）；project_id 与 scope_sig 参与键隔离，不跨项目/
        跨可访问范围复用（R12.5）。
        """
        canonical = json.dumps(
            query_def,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"{CACHE_PREFIX}{digest}:{project_id}:{scope_sig}"

    def _lock_key(self, key: str) -> str:
        """单飞分布式锁键（design §4：``aqm:lock:{hash}``）。

        以完整缓存键（含 project_id / scope_sig）派生哈希，确保不同项目/范围的
        并发互不串锁（比仅按 query_def 哈希更强的隔离）。
        """
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{LOCK_PREFIX}{digest}"

    def _count_key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{COUNT_PREFIX}{digest}"

    # --------------------------------------------------------------- redis io

    async def _get_redis(self):
        """获取 Redis 客户端，不可用返回 None（复用 audit_logger 降级范式）。"""
        try:
            from app.core.redis import redis_client

            await asyncio.wait_for(redis_client.ping(), timeout=0.3)
            if self._redis_available is False:
                logger.info("[query_cache] Redis 恢复可用")
            self._redis_available = True
            return redis_client
        except Exception:
            if self._redis_available is not False:
                logger.warning("[query_cache] Redis 不可用，缓存降级为直查 DB")
            self._redis_available = False
            return None

    async def _cache_get(self, redis, key: str) -> Any | None:
        """读缓存；命中返回反序列化值，未命中/异常返回 None（降级）。"""
        if redis is None:
            return None
        try:
            raw = await redis.get(key)
        except Exception:
            logger.warning("[query_cache] 读缓存失败，降级为直查")
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            # 脏数据：当作未命中重建
            return None

    async def _cache_set(self, redis, key: str, value: Any, ttl: int) -> None:
        if redis is None:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False, default=str)
            await redis.set(key, payload, ex=ttl)
        except Exception:
            logger.warning("[query_cache] 写缓存失败，忽略（不影响调用方结果）")

    async def _incr_repeat(self, redis, key: str, ttl: int) -> int:
        """记录同键在 TTL 窗口内的重复次数，返回当前计数。

        首次 INCR 时设置过期为 TTL 窗口，窗口结束后计数自然清零重算（R12.1）。
        Redis 不可用 → 返回 0（不写缓存，纯降级直查）。
        """
        if redis is None:
            return 0
        try:
            count = await redis.incr(self._count_key(key))
            if count == 1:
                await redis.expire(self._count_key(key), ttl)
            return int(count)
        except Exception:
            return 0

    async def _release_lock(self, redis, lock_key: str, token: str) -> None:
        if redis is None:
            return
        try:
            await redis.eval(_UNLOCK_LUA, 1, lock_key, token)
        except Exception:
            # 锁会随 PX 自动过期，释放失败不致命
            pass

    # ------------------------------------------------------------- public API

    async def get_or_compute(
        self,
        key: str,
        compute: Callable[[], Awaitable[Any]],
        *,
        ttl: int = DEFAULT_TTL,
        singleflight: bool = True,
    ) -> Any:
        """命中缓存直接返回，否则单飞执行 ``compute`` 并按阈值写缓存。

        Parameters
        ----------
        key:
            由 :meth:`cache_key` 生成的完整缓存键。
        compute:
            无参 async 回调，返回 JSON 可序列化的查询结果。
        ttl:
            缓存 TTL 秒，自动 clamp 到 [5, 300]（R12.1）。
        singleflight:
            是否启用缓存击穿保护（默认开）。

        降级语义：Redis 不可用时直接执行 ``compute`` 返回正确结果，不报错（R12.7）。
        """
        ttl = _clamp(ttl, MIN_TTL, MAX_TTL)

        redis = await self._get_redis()

        # 1) 命中未过期 → 直接返回（R12.2 / R12.3）
        cached = await self._cache_get(redis, key)
        if cached is not None:
            return cached

        # 2) 不做单飞：直接算 + 按阈值写缓存
        if not singleflight:
            return await self._compute_and_cache(redis, key, compute, ttl)

        # 3) 进程内单飞：同键并发复用同一 in-flight task（R12.6 兜底）
        async with self._inflight_guard:
            task = self._inflight.get(key)
            owner = task is None
            if owner:
                task = asyncio.ensure_future(
                    self._singleflight_compute(key, compute, ttl)
                )
                self._inflight[key] = task

        try:
            return await task
        finally:
            if owner:
                self._inflight.pop(key, None)

    # -------------------------------------------------------------- internals

    async def _singleflight_compute(
        self,
        key: str,
        compute: Callable[[], Awaitable[Any]],
        ttl: int,
    ) -> Any:
        """单飞执行体：先复检缓存，再用分布式锁跨进程去重，最后 compute。"""
        redis = await self._get_redis()

        # 复检：可能在排队期间已被本进程其他协程或他进程写入
        cached = await self._cache_get(redis, key)
        if cached is not None:
            return cached

        # 分布式锁（跨进程单飞）；Redis 不可用则纯靠进程内 in-flight task 兜底
        have_lock = True
        token = uuid.uuid4().hex
        lock_key = self._lock_key(key)
        if redis is not None:
            try:
                have_lock = bool(
                    await redis.set(lock_key, token, nx=True, px=ttl * 1000)
                )
            except Exception:
                # 锁操作失败 → 视为降级，直接计算（不阻塞调用方）
                have_lock = True
                redis = None

            if not have_lock:
                # 他进程正在计算：等待其产出结果后复用
                waited = await self._poll_for_result(redis, key)
                if waited is not None:
                    return waited
                # 等待超时仍无结果 → 兜底自行计算（避免调用方饿死）

        try:
            return await self._compute_and_cache(redis, key, compute, ttl)
        finally:
            if have_lock and redis is not None:
                await self._release_lock(redis, lock_key, token)

    async def _poll_for_result(self, redis, key: str) -> Any | None:
        """轮询等待持锁者写入缓存（缓存击穿等待复用）。"""
        if redis is None:
            return None
        elapsed = 0.0
        while elapsed < _POLL_MAX_WAIT:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
            cached = await self._cache_get(redis, key)
            if cached is not None:
                return cached
            # 锁已释放但仍无缓存（阈值未达/写失败）→ 停止等待，交由调用方兜底
            try:
                if not await redis.exists(self._lock_key(key)):
                    return None
            except Exception:
                return None
        return None

    async def _compute_and_cache(
        self,
        redis,
        key: str,
        compute: Callable[[], Awaitable[Any]],
        ttl: int,
    ) -> Any:
        """执行 compute，并在重复次数达到阈值时写缓存（R12.1）。"""
        result = await compute()

        # 可缓存判定：TTL 窗口内重复次数 ≥ 阈值才写缓存
        count = await self._incr_repeat(redis, key, ttl)
        if count >= self._cache_threshold:
            await self._cache_set(redis, key, result, ttl)
        return result


# 模块级单例（与 audit_logger 一致的使用方式）
query_cache = QueryCache()
