"""OnlyOffice 并发编辑会话限制器。

用 Redis session key（带 TTL）控制同时编辑文档的最大人数，超限拒绝新会话。
前端收到 429 后弹窗提示"当前编辑人数已满，请稍后再试"。

架构（单一真相源 = session key 集合，无独立计数器避免 drift）：
- 会话 key `onlyoffice:session:{user_id}:{doc_key}` — 带 TTL，过期自动消失
- 活跃人数 = 去重后的 user_id 数量（同一人开多个文档/版本只算 1 个席位）
- acquire: 已存在→续期；否则按"去重用户数"判满，未满则 SET
- release: DEL 对应 key
- TTL 兜底：callback 未释放时 key 到期自动消失，计数自然回落（自愈）

性能：会话上限 10，key 极少，SCAN 成本可忽略。
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

# 会话过期时间（秒）—— 兜底清理僵尸会话（正常由 callback release）
_SESSION_TTL = 3600  # 1 小时


def _user_of(key: str) -> str:
    """从 session key 提取 user_id 段：onlyoffice:session:{user_id}:{doc_key}。"""
    parts = key.split(":")
    # parts = ['onlyoffice', 'session', '<user_id>', '<doc_key...>']
    return parts[2] if len(parts) >= 3 else key


async def _scan_session_keys(redis) -> list[str]:
    """SCAN 所有活跃 session key（避免 KEYS 阻塞）。"""
    keys: list[str] = []
    cursor = 0
    while True:
        cursor, batch = await redis.scan(
            cursor=cursor, match=f"{_SESSION_PREFIX}:*", count=100
        )
        keys.extend(b.decode() if isinstance(b, bytes) else b for b in batch)
        if cursor == 0:
            break
    return keys


async def acquire_session(user_id: UUID | str, document_key: str) -> bool:
    """尝试获取一个编辑席位。返回 True=成功（含幂等续期），False=已满。

    席位按"去重用户数"计：同一用户开多个文档/版本只占 1 个席位。
    """
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        logger.warning("Redis unavailable, skipping session limit check")
        return True

    session_key = f"{_SESSION_PREFIX}:{user_id}:{document_key}"

    # 幂等：已存在 → 续期 TTL
    if await redis.exists(session_key):
        await redis.expire(session_key, _SESSION_TTL)
        return True

    # 按去重用户数判满：当前用户已有其他会话则不占新席位
    keys = await _scan_session_keys(redis)
    active_users = {_user_of(k) for k in keys}
    uid = str(user_id)
    if uid not in active_users and len(active_users) >= MAX_SESSIONS:
        return False

    await redis.set(session_key, "1", ex=_SESSION_TTL)
    return True


async def release_session(user_id: UUID | str, document_key: str) -> None:
    """释放一个编辑席位（DEL 对应 session key，幂等）。"""
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        return

    session_key = f"{_SESSION_PREFIX}:{user_id}:{document_key}"
    await redis.delete(session_key)


async def get_active_count() -> int:
    """获取当前活跃编辑席位数（去重用户数）。"""
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        return 0

    keys = await _scan_session_keys(redis)
    return len({_user_of(k) for k in keys})

