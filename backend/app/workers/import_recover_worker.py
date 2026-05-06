"""导入任务恢复 Worker — 每 30 秒检查一次

需求 10.1/10.3/10.5：从 main.py lifespan 中拆出 `_import_recover_loop`。
受 `settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED` 控制；未启用时直接返回。
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger("import_recover")

INTERVAL_SECONDS = 30


async def run(stop_event: asyncio.Event) -> None:
    """导入任务恢复主循环。"""
    if not settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED:
        logger.info("[ImportRecover] disabled by settings, worker exits")
        return

    while not stop_event.is_set():
        try:
            from app.services.import_job_runner import ImportJobRunner
            await ImportJobRunner.recover_jobs()

            # 等待 INTERVAL_SECONDS 或 stop_event
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL_SECONDS)
                break
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[ImportRecover] loop error: %s", e)
