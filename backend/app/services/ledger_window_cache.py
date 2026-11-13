"""序时账 / 辅助明细账窗口的 Redis 读缓存。

窗口查询只读、不涉及重新运算，同一数据集下结果是确定的：缓存整页响应，翻页、回翻、刷新、
多人重复打开都直接命中，不再重复跑分页 + 月度汇总 SQL。

缓存键 = 种类 + 项目 + **生效数据集 ID** + 用户 + 查询参数（含游标）：
- 重新导入 / 切换数据集 → 数据集 ID 变化 → 旧键自然不再命中，无需手工失效；
- 游标按用户签名，所以键里带用户，避免把别人的游标发给另一个人；
- TTL 必须小于游标有效期（ledger_window_cursor._TTL_SECONDS = 1800），否则缓存里的下一页游标会先过期。
Redis 不可用时静默退回直接查库。
"""
from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

from app.schemas.ledger_window import LedgerWindowQuery, LedgerWindowResponse
from app.services.ledger_window_service import Kind, LedgerWindowService

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 900


def _cache_key(kind: Kind, project_id: UUID, dataset_id: UUID, subject: str, query: LedgerWindowQuery) -> str:
    digest = hashlib.sha256(query.model_dump_json().encode("utf-8")).hexdigest()[:32]
    return f"ledger:win:{kind}:{project_id}:{dataset_id}:{subject}:{digest}"


SUMMARY_TTL_SECONDS = 6 * 3600


class RedisSummaryCache:
    """浏览模式首窗摘要的长效缓存：与用户、每页条数无关，键含数据集 ID（重新导入自然失效）。

    TTL 6 小时只是兜底；直接改库的修复工具请调 ledger_cache_invalidate.invalidate_ledger_caches。
    """

    def __init__(self, redis) -> None:
        self.redis = redis

    @staticmethod
    def _key(key: str) -> str:
        return f"ledger:winsum:{key}"

    async def get(self, key: str):
        try:
            raw = await self.redis.get(self._key(key))
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            logger.debug("ledger summary cache read failed", exc_info=True)
            return None

    async def set(self, key: str, value) -> None:
        try:
            await self.redis.set(self._key(key), json.dumps(value, ensure_ascii=False), ex=SUMMARY_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            logger.debug("ledger summary cache write failed", exc_info=True)


async def fetch_window_cached(
    redis,
    service: LedgerWindowService,
    kind: Kind,
    project_id: UUID,
    subject: str,
    query: LedgerWindowQuery,
) -> LedgerWindowResponse:
    if redis is None:
        return await service.fetch(kind, project_id, subject, query)
    if hasattr(service, "summary_cache"):
        service.summary_cache = RedisSummaryCache(redis)
    dataset_id = await service._active_dataset(project_id, query.year)
    key = _cache_key(kind, project_id, dataset_id, subject, query)
    try:
        cached = await redis.get(key)
        if cached:
            return LedgerWindowResponse.model_validate_json(cached)
    except Exception:  # noqa: BLE001  缓存故障不得影响查询
        logger.debug("ledger window cache read failed", exc_info=True)
    result = await service.fetch(kind, project_id, subject, query)
    try:
        await redis.set(key, result.model_dump_json(), ex=CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        logger.debug("ledger window cache write failed", exc_info=True)
    return result
