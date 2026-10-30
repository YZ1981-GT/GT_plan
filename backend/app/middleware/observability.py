"""可观测性中间件 — 结构化请求指标采集

记录每个请求的关键指标：
- 路径、方法、状态码
- 响应时间（毫秒）
- 慢请求告警（>3s）

为后续接入 OpenTelemetry/Prometheus 预留接口。

纯 ASGI（spec backend-startup-and-request-overhead R3.1）：计时到下游发出响应头为止（与原版 ``call_next``
返回的时刻相同），在响应头上加 X-Response-Time。
"""

import logging
import time

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.middleware._asgi import request_path

logger = logging.getLogger("audit_platform.metrics")

# 慢请求阈值（毫秒）
_SLOW_REQUEST_MS = 3000

# 不记录的路径前缀
_SKIP_PATHS = ("/api/health", "/api/events/stream", "/docs", "/openapi.json")

# 预期可能超过慢请求阈值的路径（LLM/健康探测），仅记 debug 不打 WARNING
_EXPECTED_SLOW_PATH_MARKERS = ("/ai-generate", "/api/ai/health", "/api/ai/chat")


def _log_decision(duration_ms: float, status: int, path: str) -> tuple[int, str]:
    """保持原日志优先级：慢请求先于状态码；预期慢路径降为 DEBUG。"""
    if duration_ms > _SLOW_REQUEST_MS:
        if any(marker in path for marker in _EXPECTED_SLOW_PATH_MARKERS):
            return logging.DEBUG, "SLOW_OK"
        return logging.WARNING, "SLOW_REQUEST"
    if status >= 500:
        return logging.ERROR, "SERVER_ERROR"
    if status >= 400:
        return logging.INFO, "CLIENT_ERROR"
    return logging.DEBUG, "REQUEST"


class ObservabilityMiddleware:
    """采集请求指标，输出结构化日志"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = request_path(scope)

        # 跳过健康检查和 SSE 等高频/长连接端点
        if any(path.startswith(p) for p in _SKIP_PATHS):
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()

        async def send_with_metrics(message: Message) -> None:
            if message["type"] == "http.response.start":
                duration_ms = (time.perf_counter() - start) * 1000
                status = message["status"]
                level, label = _log_decision(duration_ms, status, path)
                # 生产常用 WARNING 级别下，普通 2xx 是 DEBUG：先判级再构造字典与 Headers，
                # 不为最终会被 logging 丢弃的记录做固定分配。X-Response-Time 响应契约照旧。
                if logger.isEnabledFor(level):
                    log_data = {
                        "method": scope["method"],
                        "path": path,
                        "status": status,
                        "duration_ms": round(duration_ms, 1),
                        "user_agent": Headers(scope=scope).get("user-agent", "")[:50],
                    }
                    if label == "SLOW_OK":
                        logger.debug("SLOW_OK %s", log_data)
                    elif label == "SLOW_REQUEST":
                        logger.warning("SLOW_REQUEST %s", log_data)
                    elif label == "SERVER_ERROR":
                        logger.error("SERVER_ERROR %s", log_data)
                    elif label == "CLIENT_ERROR":
                        logger.info("CLIENT_ERROR %s", log_data)
                    else:
                        logger.debug("REQUEST %s", log_data)

                # 设置响应头（供前端监控使用）
                MutableHeaders(scope=message)["X-Response-Time"] = f"{duration_ms:.0f}ms"
            await send(message)

        await self.app(scope, receive, send_with_metrics)
