"""OpenTelemetry 全链路追踪（endpoint-fuzz-and-tracing spec）。

setup_tracing(app) 在 main.py 启动时调用，自动 instrument FastAPI/asyncpg/redis/httpx，
产生贯穿后端→PG→Redis→vLLM(httpx) 的 trace span。

OTEL_ENABLED=False（默认）时 setup_tracing 是 no-op，零运行时开销。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

from app.core.config import settings

logger = logging.getLogger(__name__)
_initialized = False


def setup_tracing(app: "FastAPI") -> None:
    """Instrument FastAPI/asyncpg/redis/httpx；OTEL_ENABLED=False 时 no-op 零开销。

    Args:
        app: FastAPI 应用实例（必须在 app 创建后、add_middleware 前调用）。
    """
    global _initialized

    if not settings.OTEL_ENABLED:
        return

    if _initialized:
        return

    # OTel 包可能未安装（可选依赖），优雅降级
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except ImportError:
        logger.warning(
            "OpenTelemetry SDK packages not installed; tracing disabled. "
            "Install: pip install opentelemetry-sdk opentelemetry-api"
        )
        return

    # --- TracerProvider ---
    resource = Resource.create({SERVICE_NAME: "audit-platform-backend"})
    provider = TracerProvider(resource=resource)

    # --- Exporter ---
    if settings.OTEL_EXPORTER == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(
                endpoint=settings.OTEL_OTLP_ENDPOINT, insecure=True
            )
        except ImportError:
            logger.warning(
                "opentelemetry-exporter-otlp not installed; falling back to console exporter."
            )
            exporter = ConsoleSpanExporter()
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # --- Instrumentors ---
    # FastAPI
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        logger.warning("opentelemetry-instrumentation-fastapi not installed; skipped.")

    # AsyncPG
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

        AsyncPGInstrumentor().instrument()
    except ImportError:
        logger.warning("opentelemetry-instrumentation-asyncpg not installed; skipped.")
    except Exception as exc:
        logger.warning("AsyncPG instrument skipped: %s", exc)

    # Redis
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except ImportError:
        logger.warning("opentelemetry-instrumentation-redis not installed; skipped.")

    # HTTPXClient
    # NOTE: httpx instrumentation 通过 W3C TraceContext 标准在 HTTP 请求 header 中注入
    # trace context（traceparent/tracestate），实现跨服务 trace 传播。
    # 这是纯 header 注入机制，不经过环境变量代理（HTTP_PROXY/HTTPS_PROXY），
    # 因此不会破坏全仓 httpx 客户端的 trust_env=False 约束。
    # trust_env=False 仅阻止 httpx 读取 env proxy 配置，与 OTel header 注入互不干扰。
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except ImportError:
        logger.warning("opentelemetry-instrumentation-httpx not installed; skipped.")

    _initialized = True
    logger.info(
        "OpenTelemetry tracing enabled (exporter=%s, service=audit-platform-backend)",
        settings.OTEL_EXPORTER,
    )
