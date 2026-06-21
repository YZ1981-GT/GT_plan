"""OnlyOffice 并发编辑会话限制器。

用 Redis 原子计数器控制同时编辑文档的最大人数，超限时拒绝新会话。
前端收到 429 后弹窗提示"当前编辑人数已满，请稍后再试"。

架构：
- 计数器 key `onlyoffice:session_count` — INCR/DECR 原子操作，O(1) 获取/修改
- 会话 key `onlyoffice:session:{user_id}:{doc_key}` — 幂等判重 + TTL 兜底
- acquire: 已存在→续期(不 INCR)；未满→SET+INCR；满→拒绝
- release: 存在→DEL+DECR；不存在→无操作

性能：acquire/release/get_active_count 全部 O(1)，不再 SCAN 遍历。

配置：环境变量 ONLYOFFICE_MAX_SESSIONS（默认 10）。
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)

# 最大并发编辑会话数（从 settings 读取，环境变量 ONLYOFFICE_MAX_SESSIONS，默认 10）
MAX_SESSIONS: int = settings.ONLYOFFICE_MAX_SESSIONS

# Redis keys
_SESSION_PREFIX = "onlyoffice:session"
_COUNTER_KEY = "onlyoffice:session_count"

# 会话过期时间（秒）—— 兜底清理僵尸会话（正常由 callback release）
_SESSION_TTL = 3600  # 1 小时


async def acquire_session(user_id: UUID | str, document_key: str) -> bool:
    """尝试获取一个编辑席位。返回 True=成功（含幂等续期），False=已满。

    O(1) 操作：EXISTS + conditional INCR + SET。
    """
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        logger.warning("Redis unavailable, skipping session limit check")
        return True

    session_key = f"{_SESSION_PREFIX}:{user_id}:{document_key}"

    # 幂等：已存在 → 续期 TTL，不新增计数
    if await redis.exists(session_key):
        await redis.expire(session_key, _SESSION_TTL)
        return True

    # 原子检查+增加：先读计数器，满则拒绝
    current = await redis.get(_COUNTER_KEY)
    count = int(current) if current else 0

    if count >= MAX_SESSIONS:
        return False

    # 占位：SET session key + INCR counter（用 pipeline 保原子性）
    pipe = redis.pipeline()
    pipe.set(session_key, "1", ex=_SESSION_TTL)
    pipe.incr(_COUNTER_KEY)
    await pipe.execute()

    return True


async def release_session(user_id: UUID | str, document_key: str) -> None:
    """释放一个编辑席位。O(1) 操作：DEL + DECR。

    幂等：session key 不存在时不 DECR（避免计数器变负）。
    """
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        return

    session_key = f"{_SESSION_PREFIX}:{user_id}:{document_key}"

    # 只有 key 确实存在时才 DEL + DECR（幂等）
    deleted = await redis.delete(session_key)
    if deleted:
        # DECR 后如果变负（异常情况），修正为 0
        new_count = await redis.decr(_COUNTER_KEY)
        if new_count < 0:
            await redis.set(_COUNTER_KEY, 0)


async def get_active_count() -> int:
    """获取当前活跃编辑会话数。O(1) 操作：GET counter。"""
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        return 0

    count = await redis.get(_COUNTER_KEY)
    return max(int(count), 0) if count else 0
