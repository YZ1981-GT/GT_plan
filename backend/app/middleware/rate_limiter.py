"""LLM / AI Chat 端点限流中间件 — 令牌桶算法

针对 GPU 密集型 LLM 端点实施限流，防止 vLLM 过载拖垮整个后端。
每用户每分钟最多 N 次 LLM 调用（默认 10 次）。

AI Chat Run API 具有独立限流配置（dsh-agent-panel-integration Task 12 / Req 13.5–13.7）：
- 独立 matcher：精确匹配 POST /api/ai-chat/runs
- 独立配额：AI_CHAT_RATE_LIMIT_PER_MINUTE（默认 20 次/分钟）
- 返回带 remaining/reset/retry_after 的 typed 响应

使用 Redis 实现分布式限流，Redis 不可用时降级放行。
"""

import time
from typing import Optional

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

# LLM 相关路径前缀（匹配需要限流的端点）
_LLM_PATH_PREFIXES = (
    "/api/workpapers/ai",
    "/api/workpapers/chat",
    "/api/disclosure-notes/ai",
    "/api/projects/",  # wp-explanation 路径含 /wp-ai/
    "/api/ai/chat",
)

# 更精确的路径片段匹配
_LLM_PATH_SEGMENTS = (
    "/wp-ai/",
    "/ai-generate",
    "/ai-suggest",
    "/ai-review",
    "/analytical-review",
    "/chat/stream",
    "/fill-suggestion",
    "/explain",
)

# --- AI Chat Run 独立限流（dsh-agent-panel-integration Task 12 / Req 13.5） ---
# 🔴 精确匹配 POST /api/ai-chat/runs，不是前缀；前缀只存在但不消费 = 未接线。
_AI_CHAT_RUN_PATH = "/api/ai-chat/runs"
# 同时对 adopt 和 doc streaming 端点限流（它们共享 AI Chat 配额池）
_AI_CHAT_RATE_LIMITED_PATHS = (
    "/api/ai-chat/runs",
    "/api/ai-chat/adopt",
    "/api/ai-chat/doc/",
)

# 限流配置
LLM_RATE_LIMIT_PER_MINUTE = settings.LLM_RATE_LIMIT_PER_MINUTE
AI_CHAT_RATE_LIMIT_PER_MINUTE = settings.AI_CHAT_RATE_LIMIT_PER_MINUTE
LLM_RATE_LIMIT_WINDOW = 60  # 秒


def _is_llm_endpoint(path: str) -> bool:
    """判断请求路径是否为 LLM 端点（不含 AI Chat Run）"""
    # AI Chat 有独立限流池，不走 LLM 通用池
    if _is_ai_chat_endpoint(path):
        return False
    for seg in _LLM_PATH_SEGMENTS:
        if seg in path:
            return True
    return False


def _is_ai_chat_endpoint(path: str) -> bool:
    """判断请求路径是否属于 AI Chat Run 独立限流域（Req 13.5 精确命中）。"""
    for prefix in _AI_CHAT_RATE_LIMITED_PATHS:
        if path.startswith(prefix):
            return True
    return False


def _rate_limit_key(user_id: str) -> str:
    return f"rate_limit:llm:{user_id}"


def _ai_chat_rate_limit_key(user_id: str) -> str:
    return f"rate_limit:ai_chat:{user_id}"


class LLMRateLimitMiddleware(BaseHTTPMiddleware):
    """LLM / AI Chat 端点限流中间件

    - 对 LLM 相关端点使用 LLM 池（每用户 LLM_RATE_LIMIT_PER_MINUTE 次/分钟）
    - 对 AI Chat Run 端点使用独立池（每用户 AI_CHAT_RATE_LIMIT_PER_MINUTE 次/分钟）
    - 基于 JWT 中的 user_id 限流
    - Redis 不可用时降级放行
    - AI Chat 限流返回 429 + remaining/reset/retry_after（Req 13.6）
    """

    _redis_ok: bool = True
    _redis_check_time: float = 0.0
    _REDIS_CHECK_INTERVAL = 30.0  # Redis 可用性缓存 30 秒

    async def dispatch(self, request: Request, call_next):
        # 只对 POST/PUT 方法限流
        if request.method not in ("POST", "PUT"):
            return await call_next(request)

        path = request.url.path
        is_ai_chat = _is_ai_chat_endpoint(path)
        is_llm = _is_llm_endpoint(path) if not is_ai_chat else False

        if not is_ai_chat and not is_llm:
            return await call_next(request)

        # 提取用户 ID（从 Authorization header 解码）
        user_id = await self._extract_user_id(request)
        if not user_id:
            # 无法识别用户时放行（认证中间件会拦截）
            return await call_next(request)

        # Redis 限流检查
        redis = await self._get_redis()
        if redis:
            if is_ai_chat:
                allowed, remaining, retry_after, reset_at = await self._check_ai_chat_rate_limit(
                    redis, user_id
                )
                if not allowed:
                    # Req 13.6：typed 响应含 remaining/reset/retry_after
                    return JSONResponse(
                        status_code=429,
                        content={
                            "code": 429,
                            "message": f"AI 对话请求过于频繁，每分钟最多 {AI_CHAT_RATE_LIMIT_PER_MINUTE} 次，请 {retry_after} 秒后重试",
                            "data": {
                                "error_code": "rate_limited",
                                "remaining": remaining,
                                "reset": reset_at,
                                "retry_after": retry_after,
                            },
                        },
                        headers={"Retry-After": str(retry_after)},
                    )
            else:
                allowed, retry_after = await self._check_rate_limit(redis, user_id)
                if not allowed:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "code": 429,
                            "message": f"LLM 调用频率超限，每分钟最多 {LLM_RATE_LIMIT_PER_MINUTE} 次，请 {retry_after} 秒后重试",
                            "data": None,
                        },
                        headers={"Retry-After": str(retry_after)},
                    )

        return await call_next(request)

    async def _check_rate_limit(self, redis: Redis, user_id: str) -> tuple[bool, int]:
        """令牌桶检查，返回 (是否允许, 需等待秒数)"""
        key = _rate_limit_key(user_id)
        try:
            current = await redis.get(key)
            if current is None:
                # 首次请求，设置计数器
                await redis.set(key, 1, ex=LLM_RATE_LIMIT_WINDOW)
                return True, 0

            count = int(current)
            if count >= LLM_RATE_LIMIT_PER_MINUTE:
                # 超限，计算剩余等待时间
                ttl = await redis.ttl(key)
                return False, max(ttl, 1)

            # 未超限，递增
            await redis.incr(key)
            return True, 0
        except Exception:
            # Redis 异常时降级放行
            return True, 0

    async def _check_ai_chat_rate_limit(
        self, redis: Redis, user_id: str
    ) -> tuple[bool, int, int, str]:
        """AI Chat 独立限流检查（Req 13.5/13.6）。

        返回 (是否允许, remaining, retry_after, reset ISO timestamp)。
        区别于通用 LLM 限流：返回结构化字段供前端显示中文倒计时。
        """
        key = _ai_chat_rate_limit_key(user_id)
        limit = AI_CHAT_RATE_LIMIT_PER_MINUTE
        try:
            current = await redis.get(key)
            if current is None:
                await redis.set(key, 1, ex=LLM_RATE_LIMIT_WINDOW)
                return True, limit - 1, 0, ""

            count = int(current)
            if count >= limit:
                ttl = await redis.ttl(key)
                retry_after = max(ttl, 1)
                from datetime import datetime, timezone, timedelta
                reset_ts = (
                    datetime.now(timezone.utc) + timedelta(seconds=retry_after)
                ).isoformat()
                return False, 0, retry_after, reset_ts

            await redis.incr(key)
            ttl = await redis.ttl(key)
            return True, limit - count - 1, 0, ""
        except Exception:
            # Redis 异常时降级放行
            return True, limit, 0, ""

    async def _extract_user_id(self, request: Request) -> Optional[str]:
        """从 Authorization header 提取 user_id"""
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:]
        try:
            from app.core.security import decode_token
            payload = decode_token(token)
            return payload.get("sub")
        except Exception:
            return None

    async def _get_redis(self) -> Optional[Redis]:
        """获取 Redis 连接，缓存可用性状态 30 秒避免频繁 ping"""
        import time as _time
        now = _time.time()

        # 缓存期内直接返回
        if now - self._redis_check_time < self._REDIS_CHECK_INTERVAL:
            if not self._redis_ok:
                return None
            try:
                from app.core.redis import redis_client
                return redis_client
            except Exception:
                return None

        # 超过缓存期，重新探测
        try:
            from app.core.redis import redis_client
            await redis_client.ping()
            LLMRateLimitMiddleware._redis_ok = True
            LLMRateLimitMiddleware._redis_check_time = now
            return redis_client
        except Exception:
            LLMRateLimitMiddleware._redis_ok = False
            LLMRateLimitMiddleware._redis_check_time = now
            return None
