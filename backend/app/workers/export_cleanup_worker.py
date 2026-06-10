"""导出 ZIP 文件清理 worker — proposal-remaining-18 task 5.7 / MT-8 配套

每小时检查一次 storage/exports/*.zip + 内存任务记录，清理超过 24h 的过期项。

设计：
- 复用 sla_worker 同款心跳模式（30s 写一次）+ 业务检查间隔（3600s）
- 清理逻辑委托给 ``ExportProgressService.cleanup_expired(max_age_hours)``
- 通过 env 变量 ``EXPORT_CLEANUP_MAX_AGE_HOURS`` 调整保留时长（默认 24h）
- 多副本下通过 leader lock 确保仅一个副本执行清理（心跳仍全副本写）

Validates: requirements.md §三 C-3 配套 + MT-8 文件管理
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.workers.worker_helpers import write_heartbeat

logger = logging.getLogger("audit_platform.export_cleanup_worker")

HEARTBEAT_INTERVAL_SECONDS = 30
CLEANUP_INTERVAL_SECONDS = 3600  # 每小时清理一次


def _resolve_max_age_hours() -> float:
    """从环境变量读取保留时长（小时），默认 24"""
    raw = os.environ.get("EXPORT_CLEANUP_MAX_AGE_HOURS", "24")
    try:
        v = float(raw)
        if v <= 0:
            return 24.0
        return v
    except (TypeError, ValueError):
        return 24.0


async def run(stop_event: asyncio.Event) -> None:
    """ZIP 清理主循环。

    - 每 30s 写心跳
    - 每 3600s（1h）触发一次清理
    - stop_event.set() 后退出
    """
    last_check_at = 0.0
    loop_count = 0

    # 启动时立即跑一次（处理重启前积压的过期文件）
    try:
        from app.services.export_progress_service import export_progress_service
        result = export_progress_service.cleanup_expired(_resolve_max_age_hours())
        logger.info(
            "[export_cleanup] startup cleanup: %s",
            result,
        )
    except Exception as exc:
        logger.warning("[export_cleanup] startup cleanup failed: %s", exc)

    while not stop_event.is_set():
        await write_heartbeat("export_cleanup_worker")

        loop_count += 1
        elapsed = loop_count * HEARTBEAT_INTERVAL_SECONDS

        if elapsed >= CLEANUP_INTERVAL_SECONDS:
            # Leader lock: only one replica should execute cleanup
            from app.workers._leader_lock import try_acquire_leadership

            if not await try_acquire_leadership("export_cleanup_worker", ttl_ms=90_000):
                # Not the leader this round, skip cleanup
                loop_count = 0
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=HEARTBEAT_INTERVAL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    pass
                continue

            try:
                from app.services.export_progress_service import (
                    export_progress_service,
                )
                result = export_progress_service.cleanup_expired(
                    _resolve_max_age_hours()
                )
                if result["removed_files"] or result["removed_tasks"]:
                    logger.info("[export_cleanup] hourly: %s", result)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("[export_cleanup] hourly cleanup error: %s", exc)
            loop_count = 0

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=HEARTBEAT_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            pass
