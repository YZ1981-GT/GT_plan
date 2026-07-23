"""ACNR 分布式缓存 Epoch — Redis INCR + pub-sub + 断连重连 + 轮询兜底

维护 per-project 变更计数器 `project_epoch`：
- Redis Key: `acnr:epoch:{project_id}` → int（单调递增）
- Pub-sub Channel: `acnr:invalidate:{project_id}`

Worker 订阅 `acnr:invalidate:*` → 清本地缓存（下次请求重建）。
断连重连：指数退避 5s/10s/20s/30s max；重连后清全部本地缓存。
轮询兜底：每 60s 对比本地 epoch vs Redis epoch → 不一致清缓存。

降级策略（Req-7 + Req-14 + design Error Handling）：
- Redis 不可用时 → epoch=0，每次请求重建 + 记录 fallback metric

**Validates: Requirements 7.1, 7.2, 7.3, 14.1, 14.2, 14.3, 14.4**
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ─── Redis 连接获取 ─────────────────────────────────────────────────────────

_UNSET = object()  # 哨兵：区分「尚未注入」与「显式注入 None（禁用）」

_redis_client: Any = _UNSET


def set_redis_client(client: Any) -> None:
    """注入 Redis 客户端（lifespan 启动时调用）。

    显式传入 None 表示禁用（测试模拟 Redis 不可用时使用），
    此后 get_redis_client() 不再懒解析。
    """
    global _redis_client
    _redis_client = client


def get_redis_client() -> Any:
    """获取当前 Redis 客户端。

    lifespan 注入前若已有调用（如启动期事件回放），懒解析：
    从 app.core.redis 取连接池客户端（惰性连接，不 ping）。
    若 Redis 实际不可用，后续命令抛异常走既有 fallback 分支。
    """
    global _redis_client
    if _redis_client is _UNSET:
        try:
            from app.core.redis import _get_client
            _redis_client = _get_client()
        except Exception:
            return None
    return _redis_client


# ─── 本地缓存清理回调 ──────────────────────────────────────────────────────

_local_cache_clear_callbacks: list = []


def register_local_cache_clear(callback) -> None:
    """注册本地缓存清理回调（worker 启动时注册）。

    callback 签名: (project_id: str) -> None
    """
    _local_cache_clear_callbacks.append(callback)


def _clear_local_caches(project_id: str) -> None:
    """清除对应 project 的本地缓存。"""
    for cb in _local_cache_clear_callbacks:
        try:
            cb(project_id)
        except Exception as exc:
            logger.warning("cache_epoch: local cache clear callback failed: %s", exc)


def _clear_all_local_caches() -> None:
    """清除全部本地缓存（重连后 / 断连期间可能错过消息）。[Req-14.2]"""
    for project_id in list(_local_epoch_store.keys()):
        _clear_local_caches(project_id)
    _local_epoch_store.clear()
    logger.info("cache_epoch: cleared ALL local caches (reconnect / poll mismatch)")


# ─── 本地 Epoch 存储（用于轮询对比）────────────────────────────────────────

_local_epoch_store: dict[str, int] = {}


def get_local_epoch(project_id: str) -> int:
    """获取本地缓存的 epoch（用于轮询对比）。"""
    return _local_epoch_store.get(project_id, 0)


def set_local_epoch(project_id: str, epoch: int) -> None:
    """更新本地缓存的 epoch。"""
    _local_epoch_store[project_id] = epoch


def get_all_local_project_ids() -> list[str]:
    """获取本地缓存的全部 project_id 列表。"""
    return list(_local_epoch_store.keys())


# ─── 核心 API ────────────────────────────────────────────────────────────────

EPOCH_KEY_PREFIX = "acnr:epoch:"
INVALIDATE_CHANNEL_PREFIX = "acnr:invalidate:"


# ─── DB-backed Durable_Epoch helpers (R11.4) ────────────────────────────────

_INCR_DB_SQL = (
    "INSERT INTO acnr_invalidation_epoch (project_id, epoch, updated_at) "
    "VALUES (CAST(:pid AS uuid), 1, now()) "
    "ON CONFLICT (project_id) DO UPDATE "
    "SET epoch = acnr_invalidation_epoch.epoch + 1, updated_at = now() "
    "RETURNING epoch"
)
_READ_DB_SQL = "SELECT epoch FROM acnr_invalidation_epoch WHERE project_id = CAST(:pid AS uuid)"


async def _increment_db_epoch(project_id: str, session=None) -> int:
    """DB 权威单调递增（单语句原子 ON CONFLICT）。

    session 提供 → 在该事务内递增（与业务变更同事务，供 outbox dispatcher/受控入口用）。
    session 为 None → 开短事务自提交。
    """
    import sqlalchemy as sa

    if session is not None:
        val = (await session.execute(sa.text(_INCR_DB_SQL), {"pid": project_id})).scalar_one()
        await session.flush()
        return int(val)

    from app.core.database import async_session
    async with async_session() as s:
        val = (await s.execute(sa.text(_INCR_DB_SQL), {"pid": project_id})).scalar_one()
        await s.commit()
        return int(val)


async def _read_db_epoch(project_id: str, session=None) -> int | None:
    """读 DB Durable_Epoch；行不存在返回 0，异常上抛给调用方兜底。"""
    import sqlalchemy as sa

    if session is not None:
        val = (await session.execute(sa.text(_READ_DB_SQL), {"pid": project_id})).scalar_one_or_none()
        return int(val) if val is not None else 0

    from app.core.database import async_session
    async with async_session() as s:
        val = (await s.execute(sa.text(_READ_DB_SQL), {"pid": project_id})).scalar_one_or_none()
        return int(val) if val is not None else 0


async def increment_epoch(project_id: str, session=None) -> int:
    """递增 project_epoch（DB 权威 + Redis fan-out）并通知其他 worker。

    R11.4：DB-first 单调递增 —— Redis 不可用时 DB 仍递增（不丢失跨 worker 失效）；
    Redis 仅作 commit 后 fan-out。DB 不可用时回退旧 Redis-only 路径（不回归既有能力）。

    Args:
        project_id: 项目 ID
        session: 可选业务事务 session（提供则 epoch 递增与业务变更同事务）

    Returns:
        递增后的 epoch 值；DB 与 Redis 均不可用时返回 0（降级，TTL/poll 兜底）。
    """
    if not project_id:
        return 0

    # 1) DB-first 权威递增（Redis 不可用仍递增）
    try:
        new_epoch = await _increment_db_epoch(project_id, session)
        # best-effort Redis 镜像 + fan-out（失败仅告警，不影响 DB 权威值）
        redis = get_redis_client()
        if redis is not None:
            try:
                await redis.set(f"{EPOCH_KEY_PREFIX}{project_id}", new_epoch)
                await redis.publish(f"{INVALIDATE_CHANNEL_PREFIX}{project_id}", str(new_epoch))
            except Exception as exc:
                logger.warning(
                    "cache_epoch.increment_epoch: Redis fan-out failed (DB epoch=%d, project=%s): %s",
                    new_epoch, project_id, exc,
                )
                _record_fallback_metric(f"increment_epoch redis fan-out: {exc}")
        set_local_epoch(project_id, new_epoch)
        logger.debug("cache_epoch.increment_epoch: project=%s epoch=%d (DB)", project_id, new_epoch)
        return new_epoch
    except Exception as db_exc:
        logger.warning(
            "cache_epoch.increment_epoch: DB-first failed, fallback to Redis-only (project=%s): %s",
            project_id, db_exc,
        )
        _record_fallback_metric(f"increment_epoch DB: {db_exc}")

    # 2) DB 不可用 → 退回旧 Redis-only 路径（不回归既有能力）
    redis = get_redis_client()
    if redis is None:
        _record_fallback_metric("increment_epoch: DB+Redis both unavailable")
        return 0
    try:
        new_epoch = await redis.incr(f"{EPOCH_KEY_PREFIX}{project_id}")
        await redis.publish(f"{INVALIDATE_CHANNEL_PREFIX}{project_id}", str(new_epoch))
        set_local_epoch(project_id, int(new_epoch))
        return int(new_epoch)
    except Exception as exc:
        logger.warning(
            "cache_epoch.increment_epoch: Redis-only fallback error (project=%s): %s",
            project_id, exc,
        )
        _record_fallback_metric(f"increment_epoch redis fallback: {exc}")
        return 0


async def get_epoch(project_id: str, session=None) -> int:
    """获取当前 project_epoch（DB 权威，Redis 回退）。

    Returns:
        当前 epoch 值；DB 与 Redis 均不可用或 key 不存在时返回 0。
    """
    if not project_id:
        return 0

    # DB-first 权威读
    try:
        val = await _read_db_epoch(project_id, session)
        if val is not None:
            set_local_epoch(project_id, val)
            return val
    except Exception as exc:
        logger.warning(
            "cache_epoch.get_epoch: DB read failed, fallback to Redis (project=%s): %s",
            project_id, exc,
        )
        _record_fallback_metric(f"get_epoch DB: {exc}")

    # 回退 Redis
    redis = get_redis_client()
    if redis is None:
        _record_fallback_metric("get_epoch: DB+Redis both unavailable")
        return 0
    try:
        val = await redis.get(f"{EPOCH_KEY_PREFIX}{project_id}")
        epoch = int(val) if val is not None else 0
        set_local_epoch(project_id, epoch)
        return epoch
    except Exception as exc:
        logger.warning(
            "cache_epoch.get_epoch: Redis error, fallback epoch=0 (project=%s): %s",
            project_id, exc,
        )
        _record_fallback_metric(f"get_epoch redis: {exc}")
        return 0


# ─── Metrics helper ──────────────────────────────────────────────────────────

def _record_fallback_metric(reason: str) -> None:
    """记录 Redis 不可用 fallback metric [Req-14.4]。"""
    try:
        from app.services.acnr.metrics import get_acnr_metrics
        get_acnr_metrics().record_fallback(reason, domain="cache_epoch")
    except Exception:
        pass  # metrics 不可用时静默


# ─── 重连配置 ────────────────────────────────────────────────────────────────

RECONNECT_BACKOFF_SCHEDULE = [5, 10, 20, 30]  # 指数退避秒数 [Req-14.1]
RECONNECT_MAX_DELAY = 30  # 最大重连等待秒数
EPOCH_POLL_INTERVAL = 60  # 轮询间隔秒数 [Req-14.3]

# 后台任务引用（用于 lifespan 关闭时取消）
_subscriber_task: asyncio.Task | None = None
_poll_task: asyncio.Task | None = None


# ─── Worker 订阅逻辑 + 断连重连 ──────────────────────────────────────────────

async def start_epoch_subscriber() -> None:
    """启动 worker 级 pub-sub 订阅 + 轮询兜底（lifespan 中调用）。[Req-14]

    启动两个后台 asyncio.Task：
    1. _reconnect_loop: 订阅 + 断连时指数退避重连
    2. _epoch_poll_task: 每 60s 轮询对比 epoch
    """
    global _subscriber_task, _poll_task

    # R11.5: DB 轮询兜底任务始终启动（不依赖 Redis）
    if _poll_task is None or _poll_task.done():
        _poll_task = asyncio.create_task(_epoch_poll_task())
    # R11.5: subscriber 重连循环始终启动；Redis 不可用时其内部指数退避自愈
    if _subscriber_task is None or _subscriber_task.done():
        _subscriber_task = asyncio.create_task(_reconnect_loop())

    redis = get_redis_client()
    if redis is None:
        logger.warning(
            "cache_epoch.start_epoch_subscriber: Redis unavailable at startup; "
            "DB poll fallback started, subscriber will self-heal on Redis recovery"
        )
        _record_fallback_metric("start_epoch_subscriber: Redis unavailable at startup")
    else:
        logger.info("cache_epoch: started subscriber + poll tasks")


async def stop_epoch_subscriber() -> None:
    """停止后台订阅/轮询任务（lifespan 关闭时调用）。"""
    global _subscriber_task, _poll_task
    for task in (_subscriber_task, _poll_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _subscriber_task = None
    _poll_task = None


async def _reconnect_loop() -> None:
    """订阅 + 指数退避重连循环 [Req-14.1, Req-14.2]。

    连接断开时按 5s/10s/20s/30s max 退避重连。
    重连成功后清除全部本地缓存。
    """
    attempt = 0

    while True:
        try:
            redis = get_redis_client()
            if redis is None:
                raise ConnectionError("Redis client is None")

            pubsub = redis.pubsub()
            await pubsub.psubscribe(f"{INVALIDATE_CHANNEL_PREFIX}*")
            logger.info("cache_epoch: subscribed to %s*", INVALIDATE_CHANNEL_PREFIX)

            # 重连成功（非首次连接时清缓存）[Req-14.2]
            if attempt > 0:
                _clear_all_local_caches()
                logger.info(
                    "cache_epoch: reconnected after %d attempts, cleared all local caches",
                    attempt,
                )
            attempt = 0  # 重置退避计数

            # 监听消息
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    channel: str = (
                        message["channel"].decode()
                        if isinstance(message["channel"], bytes)
                        else message["channel"]
                    )
                    project_id = channel.removeprefix(INVALIDATE_CHANNEL_PREFIX)
                    _clear_local_caches(project_id)
                    # 从消息中更新本地 epoch
                    try:
                        data = message.get("data")
                        if data is not None:
                            epoch_val = int(
                                data.decode() if isinstance(data, bytes) else data
                            )
                            set_local_epoch(project_id, epoch_val)
                    except (ValueError, TypeError):
                        pass
                    logger.debug(
                        "cache_epoch: received invalidate for project=%s",
                        project_id,
                    )

        except asyncio.CancelledError:
            # 正常关闭
            logger.info("cache_epoch: _reconnect_loop cancelled, exiting")
            return

        except Exception as exc:
            # 连接断开或异常 → 指数退避重连 [Req-14.1]
            delay = RECONNECT_BACKOFF_SCHEDULE[
                min(attempt, len(RECONNECT_BACKOFF_SCHEDULE) - 1)
            ]
            attempt += 1
            logger.warning(
                "cache_epoch: subscriber disconnected (attempt=%d, "
                "next_retry=%ds): %s",
                attempt, delay, exc,
            )
            _record_fallback_metric(
                f"subscriber disconnected (attempt={attempt}): {exc}"
            )
            await asyncio.sleep(delay)


async def _epoch_poll_task() -> None:
    """每 60s 轮询：对比本地 epoch vs Redis epoch → 不一致清缓存 [Req-14.3]。

    作为 pub-sub 的兜底机制——即使消息丢失，轮询也能在 60s 内修复不一致。
    """
    while True:
        try:
            await asyncio.sleep(EPOCH_POLL_INTERVAL)

            project_ids = get_all_local_project_ids()
            if not project_ids:
                continue

            for project_id in project_ids:
                try:
                    # R11.4: 对比 DB 权威 Durable_Epoch（不依赖 Redis）
                    remote_epoch = await _read_db_epoch(project_id)
                    if remote_epoch is None:
                        continue
                    local_epoch = get_local_epoch(project_id)

                    if remote_epoch != local_epoch:
                        logger.info(
                            "cache_epoch: poll mismatch project=%s "
                            "local=%d remote=%d → clearing cache",
                            project_id, local_epoch, remote_epoch,
                        )
                        _clear_local_caches(project_id)
                        set_local_epoch(project_id, remote_epoch)
                except Exception as exc:
                    logger.warning(
                        "cache_epoch: poll error for project=%s: %s",
                        project_id, exc,
                    )

        except asyncio.CancelledError:
            logger.info("cache_epoch: _epoch_poll_task cancelled, exiting")
            return
        except Exception as exc:
            logger.warning("cache_epoch: _epoch_poll_task error: %s", exc)
            # 继续循环，下次重试
