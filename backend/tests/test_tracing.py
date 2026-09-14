"""tracing.setup_tracing 单测。

验证：
- OTEL_ENABLED=False → setup_tracing 不 instrument（mock Instrumentor 断言未调用）
- OTEL_ENABLED=True + console exporter → instrument 链路不抛错（mock 各 Instrumentor）

Requirements: 5.2
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import app.core.tracing as tracing_mod
from app.core.tracing import setup_tracing


@pytest.fixture(autouse=True)
def reset_initialized():
    """每个测试前重置 _initialized 标志，避免测试间干扰。"""
    tracing_mod._initialized = False
    yield
    tracing_mod._initialized = False


class TestSetupTracingDisabled:
    """OTEL_ENABLED=False → setup_tracing 是 no-op，不 instrument 任何组件。"""

    def test_noop_when_disabled(self):
        """setup_tracing 在 OTEL_ENABLED=False 时直接返回，不调用任何 Instrumentor。"""
        mock_app = MagicMock()

        with (
            patch.object(tracing_mod, "settings") as mock_settings,
            patch(
                "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"
            ) as mock_fastapi,
            patch(
                "opentelemetry.instrumentation.asyncpg.AsyncPGInstrumentor"
            ) as mock_asyncpg,
            patch(
                "opentelemetry.instrumentation.redis.RedisInstrumentor"
            ) as mock_redis,
            patch(
                "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor"
            ) as mock_httpx,
        ):
            mock_settings.OTEL_ENABLED = False
            setup_tracing(mock_app)

            # 所有 Instrumentor 都不应被调用
            mock_fastapi.instrument_app.assert_not_called()
            mock_asyncpg.assert_not_called()
            mock_redis.assert_not_called()
            mock_httpx.assert_not_called()

        # _initialized 保持 False
        assert tracing_mod._initialized is False


class TestSetupTracingEnabled:
    """OTEL_ENABLED=True + console exporter → instrument 链路不抛错。"""

    def test_instruments_all_four_components(self):
        """setup_tracing 在 OTEL_ENABLED=True 时调用所有四个 Instrumentor。"""
        mock_app = MagicMock()

        with (
            patch.object(tracing_mod, "settings") as mock_settings,
            patch(
                "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"
            ) as mock_fastapi_cls,
            patch(
                "opentelemetry.instrumentation.asyncpg.AsyncPGInstrumentor"
            ) as mock_asyncpg_cls,
            patch(
                "opentelemetry.instrumentation.redis.RedisInstrumentor"
            ) as mock_redis_cls,
            patch(
                "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor"
            ) as mock_httpx_cls,
            patch("opentelemetry.sdk.trace.TracerProvider"),
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
            patch("opentelemetry.sdk.trace.export.ConsoleSpanExporter"),
            patch("opentelemetry.sdk.resources.Resource"),
            patch("opentelemetry.trace.set_tracer_provider"),
        ):
            mock_settings.OTEL_ENABLED = True
            mock_settings.OTEL_EXPORTER = "console"
            mock_settings.OTEL_OTLP_ENDPOINT = "http://localhost:4317"

            setup_tracing(mock_app)

            # FastAPIInstrumentor.instrument_app(app) 应被调用
            mock_fastapi_cls.instrument_app.assert_called_once_with(mock_app)

            # AsyncPGInstrumentor().instrument() 应被调用
            mock_asyncpg_cls.return_value.instrument.assert_called_once()

            # RedisInstrumentor().instrument() 应被调用
            mock_redis_cls.return_value.instrument.assert_called_once()

            # HTTPXClientInstrumentor().instrument() 应被调用
            mock_httpx_cls.return_value.instrument.assert_called_once()

        # _initialized 应为 True
        assert tracing_mod._initialized is True

    def test_idempotent_no_double_instrument(self):
        """第二次调用 setup_tracing 不会重复 instrument（_initialized 守护）。"""
        mock_app = MagicMock()

        with (
            patch.object(tracing_mod, "settings") as mock_settings,
            patch(
                "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"
            ) as mock_fastapi_cls,
            patch(
                "opentelemetry.instrumentation.asyncpg.AsyncPGInstrumentor"
            ) as mock_asyncpg_cls,
            patch(
                "opentelemetry.instrumentation.redis.RedisInstrumentor"
            ) as mock_redis_cls,
            patch(
                "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor"
            ) as mock_httpx_cls,
            patch("opentelemetry.sdk.trace.TracerProvider"),
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
            patch("opentelemetry.sdk.trace.export.ConsoleSpanExporter"),
            patch("opentelemetry.sdk.resources.Resource"),
            patch("opentelemetry.trace.set_tracer_provider"),
        ):
            mock_settings.OTEL_ENABLED = True
            mock_settings.OTEL_EXPORTER = "console"
            mock_settings.OTEL_OTLP_ENDPOINT = "http://localhost:4317"

            # 第一次调用
            setup_tracing(mock_app)
            # 第二次调用
            setup_tracing(mock_app)

            # FastAPIInstrumentor.instrument_app 只应被调用一次
            mock_fastapi_cls.instrument_app.assert_called_once_with(mock_app)
