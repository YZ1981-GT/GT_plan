"""通用耐久任务 worker：DB claim、续租、围栏终态与重启接管。"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from uuid import uuid4

from app.core.database import async_session
from app.services import platform_job_service as jobs
from app.services.platform_job_registry import get_executor

logger = logging.getLogger("platform_job_worker")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
POLL_SECONDS = 1.0
LEASE_SECONDS = 300


async def _persist_progress(
    claim: jobs.PlatformJobClaim,
    current: int,
    total: int | None,
    message: str | None,
    stage: str | None,
) -> bool:
    async with async_session() as db:
        updated = await jobs.update_progress(
            db,
            claim,
            current=current,
            total=total,
            message=message,
            stage=stage,
        )
        await db.commit()
        return updated


async def _heartbeat(claim: jobs.PlatformJobClaim, lost: asyncio.Event) -> None:
    interval = max(1.0, claim.lease_seconds / 3)
    try:
        while not lost.is_set():
            await asyncio.sleep(interval)
            async with async_session() as db:
                renewed = await jobs.renew_lease(db, claim)
                await db.commit()
            if not renewed:
                lost.set()
                return
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("platform job heartbeat failed job=%s", claim.job_id)
        lost.set()


async def run_once() -> bool:
    async with async_session() as db:
        claim = await jobs.claim_next(
            db,
            worker_id=WORKER_ID,
            lease_seconds=LEASE_SECONDS,
        )
        await db.commit()
    if claim is None:
        return False

    executor = get_executor(claim.operation)
    if executor is None:
        async with async_session() as db:
            await jobs.finish_failure(
                db,
                claim,
                error_code="executor_missing",
                error_message=f"未注册任务执行器：{claim.operation}",
                retryable=False,
            )
            await db.commit()
        return True

    lost = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat(claim, lost))

    async def report(
        current: int,
        total: int | None = None,
        message: str | None = None,
        stage: str | None = None,
    ) -> bool:
        if lost.is_set():
            return False
        return await _persist_progress(claim, current, total, message, stage)

    try:
        outcome = await executor(claim, report)
        if outcome.finalized:
            return True
        async with async_session() as db:
            if await jobs.cancellation_requested(db, claim):
                await jobs.finish_cancelled(db, claim)
            elif lost.is_set():
                await db.rollback()
                return True
            else:
                await jobs.finish_success(
                    db,
                    claim,
                    result_ref=outcome.result_ref,
                )
            await db.commit()
    except asyncio.CancelledError:
        # 不写失败。租约到期后其他 worker 可安全接管。
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("platform job failed job=%s", claim.job_id)
        async with async_session() as db:
            cancelled = await jobs.cancellation_requested(db, claim)
            retryable = bool(getattr(exc, "retryable", False))
            if cancelled:
                settled = await jobs.finish_cancelled(db, claim)
                terminal = True
            else:
                settled = await jobs.finish_failure(
                    db,
                    claim,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                    retryable=retryable,
                )
                terminal = not retryable or claim.attempt >= claim.max_attempts
            await db.commit()
        cleanup_path = getattr(exc, "cleanup_path", None)
        if settled and terminal and cleanup_path is not None:
            from pathlib import Path

            from app.services.bulk_tab.bulk_async_runner import cleanup_import_spool

            await cleanup_import_spool(Path(cleanup_path))
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
    return True


async def run(stop_event: asyncio.Event) -> None:
    """启动时自动消费 queued/过期 running；停机后租约负责恢复。"""
    # 延迟导入 executor 模块，避免 registry 与业务服务循环依赖。
    from app.services.bulk_tab import durable_job_executor  # noqa: F401
    from app.services import export_pack_executor  # noqa: F401

    while not stop_event.is_set():
        try:
            worked = await run_once()
            if worked:
                continue
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_SECONDS)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("platform job worker iteration failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=POLL_SECONDS)
            except asyncio.TimeoutError:
                pass
