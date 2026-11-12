"""账簿读缓存失效：直接改库（清理脚本、修复工具）后调用，避免页面在 TTL 内显示旧数据。

涉及的键：
- ``ledger:balance:{project}:{year}:{account|all}``  科目余额汇总（5 分钟）
- ``ledger:win:{kind}:{project}:{dataset}:{user}:{hash}``  序时账 / 辅助明细窗口整页（15 分钟）
- ``ledger:winsum:...``  浏览模式首屏汇总（长效，键含数据集 ID）
正常导入 / 切换数据集不需要调用：窗口缓存键含数据集 ID，会自然失效。
Redis 不可用时静默返回 0。
"""
from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


async def invalidate_ledger_caches(project_id: UUID | str, redis=None) -> int:
    """删除某项目的账簿读缓存，返回删除的键数。"""
    if redis is None:
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
        except Exception:  # noqa: BLE001
            return 0
    if redis is None:
        return 0
    pid = str(project_id)
    patterns = (
        f"ledger:balance:{pid}:*",
        f"ledger:win:*:{pid}:*",
        f"ledger:winsum:*:{pid}:*",
    )
    deleted = 0
    try:
        for pattern in patterns:
            keys = [k async for k in redis.scan_iter(match=pattern, count=500)]
            if keys:
                deleted += int(await redis.delete(*keys))
    except Exception:  # noqa: BLE001
        logger.debug("invalidate_ledger_caches failed", exc_info=True)
    return deleted
