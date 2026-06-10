"""SIGTERM handler + HTTP drain 逻辑。

在 lifespan 内注册，收到 SIGTERM 后：
1. 置 shutdown_state.draining=True（readyz 立即 503）
2. drain 等待 inflight_counter 归零（上限 GRACEFUL_SHUTDOWN_TIMEOUT）

# Feature: zero-downtime-deployment, Component 3b
"""
import asyncio
import logging
import signal

from app.core.runtime_state import shutdown_state
from app.middleware.inflight import inflight_counter

logger = logging.getLogger(__name__)

# 配置
GRACEFUL_SHUTDOWN_TIMEOUT: float = float(
    __import__("os").getenv("GRACEFUL_SHUTDOWN_TIMEOUT", "30")
)
PRE_DRAIN_DELAY: float = float(
    __import__("os").getenv("PRE_DRAIN_DELAY", "2")
)

_drain_event = asyncio.Event()


def install_sigterm_handler():
    """在 lifespan 内调用，注册 SIGTERM handler。"""
    loop = asyncio.get_running_loop()

    def _on_sigterm():
        shutdown_state.start_draining()
        _drain_event.set()
        logger.info("[Shutdown] SIGTERM received, readyz → 503, starting drain...")

    try:
        loop.add_signal_handler(signal.SIGTERM, _on_sigterm)
    except NotImplementedError:
        # Windows fallback
        signal.signal(signal.SIGTERM, lambda *_: _on_sigterm())


async def drain_http_requests(timeout: float | None = None):
    """等待 in-flight HTTP 请求归零，上限 timeout。"""
    if timeout is None:
        timeout = GRACEFUL_SHUTDOWN_TIMEOUT

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while inflight_counter.value() > 0 and loop.time() < deadline:
        await asyncio.sleep(0.2)

    remaining = inflight_counter.value()
    if remaining > 0:
        logger.warning(
            "[Shutdown] drain 超时（%.1fs），仍有 %d 个 in-flight 请求未完成",
            timeout, remaining,
        )
    else:
        logger.info("[Shutdown] drain 完成，所有 in-flight 请求已处理")
