"""可观测性中间件 — 结构化请求指标采集

记录每个请求的关键指标：
- 路径、方法、状态码
- 响应时间（毫秒）
- 慢请求告警（>3s）

为后续接入 OpenTelemetry/Prometheus 预留接口。
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("audit_platform.metrics")

# 慢请求阈值（毫秒）
_SLOW_REQUEST_MS = 3000

# 不记录的路径前缀
_SKIP_PATHS = ("/api/health", "/api/events/stream", "/docs", "/openapi.json")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """采集请求指标，输出结构化日志"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 跳过健康检查和 SSE 等高频/长连接端点
        if any(path.startswith(p) for p in _SKIP_PATHS):
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        # 结构化日志
        log_data = {
            "method": request.method,
            "path": path,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 1),
            "user_agent": request.headers.get("user-agent", "")[:50],
        }

        if duration_ms > _SLOW_REQUEST_MS:
            logger.warning("SLOW_REQUEST %s", log_data)
        elif response.status_code >= 500:
            logger.error("SERVER_ERROR %s", log_data)
        elif response.status_code >= 400:
            logger.info("CLIENT_ERROR %s", log_data)
        else:
            logger.debug("REQUEST %s", log_data)

        # 设置响应头（供前端监控使用）
        response.headers["X-Response-Time"] = f"{duration_ms:.0f}ms"

        return response
