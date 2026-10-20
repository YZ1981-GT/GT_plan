"""知识库扫描件后台 OCR worker（spec dsh-kb-ocr-local-first-routing Task 8）。

认领 / 识别 / 写回在 ``app.services.knowledge_ocr_service``；本模块只管循环、唤醒与心跳：

- 一次处理一份（OCR 重）；多个 worker 进程靠行认领各取各的，互不重复。
- 上传提交后 ``wake()`` 让本进程立即开始；其他进程按 30 秒轮询；进程重启后靠租约过期接手。
- ``KNOWLEDGE_OCR_WORKER_ENABLED=False`` 时不启动（文档照样排队，开启后补识别）。
"""

from __future__ import annotations

import asyncio
import logging

from app.services.knowledge_ocr_service import claim_next, process
from app.workers.worker_helpers import write_heartbeat

logger = logging.getLogger("audit_platform.knowledge_ocr_worker")

POLL_SECONDS = 30.0

_wake_event: asyncio.Event | None = None


def wake() -> None:
    """有新文档排队：本进程的 worker 立即开始（未启动 / 其他进程时无操作，靠轮询）。"""
    if _wake_event is not None:
        _wake_event.set()


def _default_session_factory():
    from app.core.database import async_session

    return async_session()


async def drain(*, session_factory=None, recognize=None, limit: int | None = None) -> int:
    """处理到没有可认领的文档为止，返回处理份数。"""
    factory = session_factory or _default_session_factory
    handled = 0
    while limit is None or handled < limit:
        async with factory() as db:
            claim = await claim_next(db)
        if claim is None:
            return handled
        await process(claim, session_factory=factory, recognize=recognize)
        handled += 1
    return handled


async def run(stop_event: asyncio.Event) -> None:
    from app.core.config import settings

    if not getattr(settings, "KNOWLEDGE_OCR_WORKER_ENABLED", True):
        logger.info("[kb_ocr] KNOWLEDGE_OCR_WORKER_ENABLED=False，后台识别不启动")
        return
    global _wake_event
    _wake_event = asyncio.Event()
    while not stop_event.is_set():
        await write_heartbeat("knowledge_ocr_worker")
        _wake_event.clear()
        try:
            handled = await drain()
            if handled:
                logger.info("[kb_ocr] 本轮处理 %d 份", handled)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — 单轮失败不让 worker 退出
            logger.warning("[kb_ocr] 本轮处理出错：%s", exc)
        stop_wait = asyncio.ensure_future(stop_event.wait())
        wake_wait = asyncio.ensure_future(_wake_event.wait())
        try:
            await asyncio.wait(
                {stop_wait, wake_wait}, timeout=POLL_SECONDS, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for waiter in (stop_wait, wake_wait):
                waiter.cancel()
