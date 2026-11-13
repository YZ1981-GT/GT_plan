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

    # 启动时跑一次证据与运行记录清理（AQF §6.6）
    await _run_aqf_cleanup()

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

            # 每小时一次证据与运行记录清理（AQF §6.6）
            await _run_aqf_cleanup()
            loop_count = 0

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=HEARTBEAT_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            pass


async def _run_aqf_cleanup() -> None:
    """清理过期的查询证据文件与运行记录（AQF §6.6，R8.3）。

    - 证据文件到期 → 删文件、status 改 purged（每批 500 条）
    - 运行记录超期或每人超 500 条 → 删除（被未清理证据引用的跳过）
    - 证据目录里超过 1 天的 .partial 残留一并清除
    失败只记 WARNING，不阻断 worker。
    """
    from app.services.custom_query.query_evidence import query_evidence_available

    try:
        from app.core.database import async_session
        async with async_session() as db:
            async with db.begin():
                if not await query_evidence_available(db):
                    return

        deleted_artifacts = 0
        deleted_runs = 0

        # ── 清理过期证据文件 ────────────────────────────────────────────────
        from app.services.custom_query.query_artifacts import _artifact_root
        from sqlalchemy import text

        async with async_session() as db:
            while True:
                async with db.begin():
                    rows = (await db.execute(text("""
                        SELECT id, storage_key FROM query_artifacts
                         WHERE status = 'ready' AND retention_until < now()
                         LIMIT 500
                    """))).fetchall()
                if not rows:
                    break
                root = _artifact_root()
                for row_id, sk in rows:
                    try:
                        fp = root / sk
                        if fp.exists():
                            fp.unlink()
                    except OSError:
                        pass
                    async with async_session() as upd:
                        async with upd.begin():
                            await upd.execute(text("""
                                UPDATE query_artifacts
                                   SET status = 'purged', purged_at = now(), updated_at = now()
                                 WHERE id = :id
                            """), {"id": str(row_id)})
                    deleted_artifacts += 1

        # ── 清理 .partial 残留（超过 1 天）──────────────────────────────────
        try:
            import time
            root = _artifact_root()
            for year_dir in root.iterdir():
                if not year_dir.is_dir():
                    continue
                for month_dir in year_dir.iterdir():
                    if not month_dir.is_dir():
                        continue
                    for f in month_dir.glob(".*.partial"):
                        age = time.time() - f.stat().st_mtime
                        if age > 86400:
                            try:
                                f.unlink()
                            except OSError:
                                pass
        except Exception:
            pass

        # ── 清理超期运行记录 ────────────────────────────────────────────────
        from app.core.config import settings
        keep = getattr(settings, "QUERY_RUN_KEEP_PER_USER", 500)
        ret_days = getattr(settings, "QUERY_RUN_RETENTION_DAYS", 90)

        async with async_session() as db:
            while True:
                async with db.begin():
                    cnt = (await db.execute(text("""
                        DELETE FROM query_runs
                         WHERE id IN (
                             SELECT qr.id FROM query_runs qr
                              WHERE qr.last_executed_at < now() - interval '1 day' * :days
                                AND NOT EXISTS (
                                    SELECT 1 FROM query_artifacts qa
                                     WHERE qa.run_id = qr.id AND qa.status = 'ready'
                                )
                             UNION
                             SELECT id FROM (
                                 SELECT id,
                                        ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY last_executed_at DESC) AS rn
                                   FROM query_runs
                             ) t WHERE t.rn > :keep
                             LIMIT 1000
                         )
                    """), {"days": ret_days, "keep": keep})).rowcount
                    deleted_runs += cnt
                if cnt == 0:
                    break

        if deleted_artifacts or deleted_runs:
            logger.info(
                "[export_cleanup] AQF cleanup: purged_artifacts=%d pruned_runs=%d",
                deleted_artifacts, deleted_runs,
            )
    except Exception as exc:
        logger.warning("[export_cleanup] AQF cleanup error: %s", exc)
