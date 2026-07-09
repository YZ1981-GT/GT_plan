"""Uvicorn 启动入口 — Windows 下在创建事件循环前切换 Selector 策略。

SQLAlchemy 2.0 异步引擎在 Windows ProactorEventLoop 下经 uvicorn 启动时，
greenlet_spawn 会触发 maximum recursion depth exceeded（迁移 / ORM 查询失败）。
本模块须在 ``asyncio.run()`` 之前设置事件循环策略，并在 uvicorn lifespan 之前
预跑数据库迁移。

用法（替代 ``python -m uvicorn``）::

    python run_uvicorn.py app.main:app --host 0.0.0.0 --port 9980 --reload
"""
from __future__ import annotations

import asyncio
import os
import sys


def _ensure_windows_selector_loop() -> None:
    if sys.platform != "win32":
        return
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn.loops.asyncio as _uv_asyncio_loop

    def _win_asyncio_setup(use_subprocess: bool = False) -> None:  # noqa: ARG001
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    _uv_asyncio_loop.asyncio_setup = _win_asyncio_setup


def _bootstrap_before_uvicorn() -> None:
    """在 uvicorn ASGI lifespan 之前执行迁移等 DB 启动任务。

    Windows 下 uvicorn 的 lifespan 运行在嵌套 greenlet 上下文中，
    SQLAlchemy async 引擎 ``connect()`` 会触发 maximum recursion depth exceeded。
    在独立 ``asyncio.run()`` 中先完成迁移，lifespan 内跳过重复执行。
    """
    if os.environ.get("GT_BOOTSTRAP_DONE") == "1":
        return

    async def _run() -> None:
        import logging

        from app.core.config import settings
        from app.core.logging_config import setup_logging
        from app.core.migration_runner import MigrationRunner

        log_level = os.getenv("LOG_LEVEL", "WARNING").upper()
        setup_logging(level=log_level, json_format=False)
        # 使用独立引擎并在引导结束后 dispose，避免污染 app.core.database.engine
        # （bootstrap 的 asyncio.run 关闭后，共享引擎连接会绑定已死 loop）。
        runner = MigrationRunner(database_url=settings.DATABASE_URL)
        try:
            result = await runner.run_pending()
            if result.executed:
                logging.getLogger("audit_platform").info(
                    "[启动] run_uvicorn 预引导迁移完成: %s", result.executed
                )
        finally:
            await runner.close()
        logging.getLogger("audit_platform").info("[启动] run_uvicorn 预引导完成（迁移）")

    asyncio.run(_run())
    os.environ["GT_BOOTSTRAP_DONE"] = "1"


_ensure_windows_selector_loop()
_bootstrap_before_uvicorn()

from uvicorn.main import main  # noqa: E402


if __name__ == "__main__":
    main()
