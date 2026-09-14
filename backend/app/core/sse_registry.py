"""SSE 连接注册表 + drain 优雅关闭。

所有 SSE 端点的生成器在进入时 register、退出时 unregister。
drain 时 close_all() 发 server_draining 事件后关闭，触发客户端重连。

# Feature: zero-downtime-deployment, Component 7a
"""
import asyncio
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class SSEConnection:
    """Represents a single active SSE connection that can be gracefully closed."""

    def __init__(self, conn_id: str, close_callback: Callable[[], Coroutine[Any, Any, None]] | None = None):
        self.conn_id = conn_id
        self._close_callback = close_callback
        self._closed = False

    async def close(self):
        if self._closed:
            return
        self._closed = True
        if self._close_callback:
            try:
                await self._close_callback()
            except Exception as e:
                logger.warning("[SSE] Error closing connection %s: %s", self.conn_id, e)

    @property
    def is_closed(self) -> bool:
        return self._closed


class _SSERegistry:
    """SSE 连接注册表。drain 时统一优雅关闭所有连接。"""

    def __init__(self):
        self._active: dict[str, SSEConnection] = {}
        self._counter: int = 0

    def register(self, close_callback: Callable[[], Coroutine[Any, Any, None]] | None = None) -> SSEConnection:
        """Register a new SSE connection. Returns connection object for unregister."""
        self._counter += 1
        conn_id = f"sse-{self._counter}"
        conn = SSEConnection(conn_id, close_callback)
        self._active[conn_id] = conn
        logger.debug("[SSE] Registered connection %s (active: %d)", conn_id, len(self._active))
        return conn

    def unregister(self, conn: SSEConnection):
        """Unregister a connection (called on normal disconnect)."""
        self._active.pop(conn.conn_id, None)
        logger.debug("[SSE] Unregistered connection %s (active: %d)", conn.conn_id, len(self._active))

    async def close_all(self):
        """Close all active SSE connections (called during drain)."""
        count = len(self._active)
        if count == 0:
            logger.info("[SSE] close_all: no active connections")
            return

        logger.info("[SSE] Closing %d active SSE connections...", count)
        tasks = [conn.close() for conn in list(self._active.values())]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._active.clear()
        logger.info("[SSE] All SSE connections closed")

    @property
    def active_count(self) -> int:
        return len(self._active)


# 进程级单例
sse_registry = _SSERegistry()
