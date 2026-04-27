"""可用性降级服务

Phase 12: LLM故障降级 / 批量中断处理 / 网络恢复 / 锁冲突
"""
from __future__ import annotations

import logging
from uuid import UUID

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AvailabilityFallbackService:
    """可用性降级"""

    @staticmethod
    async def check_llm_available() -> bool:
        """检测 vLLM 服务是否可用。"""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{settings.LLM_BASE_URL}/models")
                return resp.status_code == 200
        except Exception:
            return False

    @staticmethod
    async def set_fallback_flag(enabled: bool) -> None:
        """设置 Redis 降级标志（Redis不可用时静默跳过）。"""
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            if enabled:
                await redis.set("llm_fallback", "true", ex=300)
            else:
                await redis.delete("llm_fallback")
        except Exception:
            logger.debug("Redis不可用，降级标志设置跳过")

    @staticmethod
    async def is_fallback_active() -> bool:
        """检查是否处于降级模式。"""
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            return await redis.get("llm_fallback") == b"true"
        except Exception:
            return False

    @staticmethod
    async def handle_llm_failure() -> dict:
        """AI生成失败时的降级处理。"""
        available = await AvailabilityFallbackService.check_llm_available()
        if not available:
            await AvailabilityFallbackService.set_fallback_flag(True)
            return {"fallback": True, "message": "AI服务暂不可用，已切换为手动模式"}
        await AvailabilityFallbackService.set_fallback_flag(False)
        return {"fallback": False, "message": "AI服务正常"}
