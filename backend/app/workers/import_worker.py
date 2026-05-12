"""Standalone durable import worker.

Run with:

    python -m app.workers.import_worker

F44 / Sprint 7.12：SIGTERM 协同停机
- 启动时注册 SIGTERM + SIGINT handler → 切换共享 ``stop_event``
- ``stop_event`` 透传给 ``ImportJobRunner.run_forever`` 使其在下一轮 sleep
  结束时优雅退出；同时由 Runner 的类级 ``_stop_event`` 暴露给 pipeline
  的 ``cancel_check`` 回调，让 in-flight 的 chunk 循环也能早停。
- Windows 上 ``loop.add_signal_handler`` 抛 NotImplementedError，
  自动回退到同步 ``signal.signal``。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from app.core.config import settings
from app.core.database import dispose_engine
from app.core.logging_config import setup_logging
from app.services.event_handlers import register_event_handlers
from app.services.gate_rules_phase14 import register_phase14_rules
from app.services.import_job_runner import ImportJobRunner
from app.services.task_event_handlers import register_event_handlers as register_task_handlers


logger = logging.getLogger("import_worker")


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """注册 SIGTERM / SIGINT → stop_event.set 的 handler（Windows 安全）。

    Unix：优先用 ``loop.add_signal_handler``（asyncio-aware，不打断事件循环）。
    Windows：``add_signal_handler`` 仅在 ProactorEventLoop 的部分信号上可用，
    SIGTERM 通常抛 NotImplementedError；回退到 ``signal.signal``，
    由 signal 模块在主线程上投递，handler 内用 ``call_soon_threadsafe``
    切回事件循环再 ``set``。
    """
    loop = asyncio.get_running_loop()

    def _trigger(signame: str) -> None:
        if stop_event.is_set():
            logger.info("[import_worker] %s received again, already shutting down", signame)
            return
        logger.info("[import_worker] %s received, requesting graceful shutdown", signame)
        stop_event.set()

    targets = (("SIGTERM", signal.SIGTERM), ("SIGINT", signal.SIGINT))
    for signame, signum in targets:
        try:
            loop.add_signal_handler(signum, _trigger, signame)
        except (NotImplementedError, RuntimeError):
            # Windows fallback：signal handler 在 signal 线程上跑，
            # 用 call_soon_threadsafe 切回 loop 线程再 set。
            def _handler(_signum, _frame, _signame=signame):
                try:
                    loop.call_soon_threadsafe(_trigger, _signame)
                except RuntimeError:
                    # loop 已关闭（例如 shutdown 中）— 静默
                    pass
            try:
                signal.signal(signum, _handler)
            except (ValueError, OSError):
                # 非主线程或无效信号 — 只能依赖 KeyboardInterrupt 兜底
                logger.warning(
                    "[import_worker] unable to install %s handler (platform=%s)",
                    signame, sys.platform,
                )


async def run_worker(*, poll_interval_seconds: int | None = None, batch_size: int | None = None) -> None:
    setup_logging(level="INFO", json_format=False)
    register_event_handlers()
    register_phase14_rules()
    register_task_handlers()

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    try:
        await ImportJobRunner.run_forever(
            poll_interval_seconds=poll_interval_seconds,
            batch_size=batch_size,
            stop_event=stop_event,
        )
    finally:
        await dispose_engine()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ledger import durable worker")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=settings.LEDGER_IMPORT_WORKER_POLL_INTERVAL_SECONDS,
        help="Seconds between worker polling cycles",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.LEDGER_IMPORT_WORKER_BATCH_SIZE,
        help="Maximum queued jobs to claim per polling cycle",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(
            run_worker(
                poll_interval_seconds=args.poll_interval,
                batch_size=args.batch_size,
            )
        )
    except KeyboardInterrupt:
        logger.info("Import worker interrupted")


if __name__ == "__main__":
    main()
