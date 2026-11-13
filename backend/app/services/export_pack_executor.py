"""底稿文件打包导出的耐久任务执行器（spec platform-heavy-jobs-and-capacity-closure B3）。

迁移对象是 ``export_progress_service`` 的「按 wp_ids 打包已存底稿文件 → ZIP」链路：

* Web 只做权限、可见集过滤和 ``platform_jobs`` INSERT，立即返回 job id。
* worker 认领后**重新**按当前用户/项目可见性 gate 所有底稿；排队期间被撤权不会继续导出。
* 元数据查询和权限检查结束后关闭 AsyncSession；ZIP 在线程中直接写唯一 attempt artifact，
  不持有 DB 连接、不保留 BytesIO 双份。
* 线程里的每一项进度用 ``run_coroutine_threadsafe(...).result()`` 回到 event loop，逐项等
  ``ProgressReporter`` 围栏确认后才继续。因此 progress 一定先于 complete，且取消/丢租约会
  中止线程写入而不是留下一个“已完成”的 ZIP。
* ZIP 写完后 executor 自己在短事务内 ``finish_success``，**commit 成功后**才发
  ``export.complete`` SSE；消费者收到完成事件时状态端点已可下载。每个 attempt 使用唯一
  文件名，旧 lease 即使未退出也不能覆盖新 worker 的产物。

旧内存 ExportProgressService 仅供路由兼容读取，见 ``export_progress_service`` 的退役日期。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from app.core.database import async_session
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services import platform_job_service as jobs
from app.services.export_progress_service import EXPORT_DIR
from app.services.platform_job_registry import (
    ExecutorOutcome,
    ProgressReporter,
    register_executor,
)
from app.services.platform_job_service import PlatformJobClaim

logger = logging.getLogger(__name__)

OPERATION = "workpaper_pack_export"
MAX_EXPORT_ITEMS = 1000


class ExportPackError(RuntimeError):
    """业务失败；打包导出沿用旧行为，失败不自动重试。"""

    retryable = False


class ExportPackLeaseLost(ExportPackError):
    """当前 worker 已不持有 attempt fence，不能再产生任何副作用。"""


@dataclass(frozen=True)
class _ExportFile:
    source: Path
    arcname: str


async def _load_export_files(
    claim: PlatformJobClaim,
    wp_ids: list[str],
) -> list[_ExportFile | None]:
    """执行时重做可见性 gate 后一次查询全部元数据。

    返回列表与请求顺序等长：不可见、已删、无文件路径的项都以 ``None`` 占位，既不进入 ZIP
    也不在回执中点名，防止排队期间权限变化泄露资源存在性。
    """
    from app.services.wp_visibility.entry_integration import make_bulk_visible_filter

    parsed: dict[str, uuid.UUID] = {}
    for raw in wp_ids:
        try:
            parsed[str(raw)] = uuid.UUID(str(raw))
        except (TypeError, ValueError):
            continue
    if not parsed:
        raise ExportPackError("导出任务的底稿标识无效")

    async with async_session() as db:
        user = (
            await db.execute(sa.select(User).where(User.id == claim.actor_id))
        ).scalar_one_or_none()
        if user is None:
            raise ExportPackError("导出任务发起人已不存在")

        visible_filter = make_bulk_visible_filter(
            db,
            user,
            entrypoint="workpaper.detail",
            action="read_detail",
            method="GET",
            entry_kind="worker",
            entry_family="export",
        )
        permitted = {
            raw
            for raw in parsed
            if await visible_filter(parsed[raw], None)
        }
        if not permitted:
            raise ExportPackError("当前已无可导出的底稿，请刷新页面后重试")

        rows = (
            await db.execute(
                sa.select(
                    WorkingPaper.id,
                    WorkingPaper.file_path,
                    WpIndex.audit_cycle,
                    WpIndex.wp_code,
                )
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(
                    WorkingPaper.id.in_([parsed[raw] for raw in permitted]),
                    WorkingPaper.project_id == claim.project_id,
                    WpIndex.project_id == claim.project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WpIndex.is_deleted == sa.false(),
                )
            )
        ).all()

    by_id = {
        str(row[0]): _ExportFile(
            source=Path(row[1]),
            arcname=f"{row[2] or 'OTHER'}/{row[3]}.xlsx",
        )
        for row in rows
        if row[1]
    }
    return [by_id.get(raw) if raw in permitted else None for raw in wp_ids]


def _write_zip(
    temp_path: Path,
    final_path: Path,
    files: list[_ExportFile | None],
    on_progress: Any,
    stop: threading.Event,
) -> int:
    """同步文件工作在线程执行；检查取消/lease 丢失并直接写唯一 artifact。"""
    written = 0
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, item in enumerate(files, start=1):
                if stop.is_set():
                    raise ExportPackLeaseLost("导出任务已取消或租约已失效")
                try:
                    if item is not None and item.source.is_file():
                        archive.write(item.source, item.arcname)
                        written += 1
                except OSError as exc:
                    logger.warning(
                        "export pack: skip %s due to %s",
                        item.source if item else "missing",
                        exc,
                    )
                on_progress(index)
        if stop.is_set():
            raise ExportPackLeaseLost("导出任务已取消或租约已失效")
        temp_path.replace(final_path)
        return written
    except BaseException:
        temp_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise


def _progress_event(claim: PlatformJobClaim, done: int, total: int) -> dict[str, Any]:
    return {
        "project_id": str(claim.project_id),
        "task_id": str(claim.job_id),
        "done": done,
        "total": total,
        "percent": int(done * 100 / max(total, 1)),
        "user_id": str(claim.actor_id),
    }


def _broadcast_failed(claim: PlatformJobClaim, error: str) -> None:
    from app.services.event_bus import event_bus

    event_bus.broadcast_raw(
        "export.failed",
        {
            "project_id": str(claim.project_id),
            "task_id": str(claim.job_id),
            "error": error,
            "user_id": str(claim.actor_id),
        },
    )


async def _finish_cancelled_if_requested(claim: PlatformJobClaim) -> bool:
    """若当前 claim 收到取消，短事务写 terminal 状态并返回是否赢得 fence。"""
    async with async_session() as db:
        if not await jobs.cancellation_requested(db, claim):
            await db.rollback()
            return False
        won = await jobs.finish_cancelled(db, claim, message="导出已取消")
        if won:
            await db.commit()
        else:
            await db.rollback()
        return won


async def _finish_failure_or_cancel(
    claim: PlatformJobClaim,
    error: BaseException,
) -> str | None:
    """将当前 attempt 终态化；返回 ``failed``/``cancelled``，fence 输掉时返回 None。"""
    async with async_session() as db:
        if await jobs.cancellation_requested(db, claim):
            won = await jobs.finish_cancelled(db, claim, message="导出已取消")
            status = "cancelled"
        else:
            won = await jobs.finish_failure(
                db,
                claim,
                error_code=type(error).__name__,
                error_message=str(error) or type(error).__name__,
                retryable=bool(getattr(error, "retryable", False)),
            )
            status = "failed"
        if won:
            await db.commit()
            return status
        await db.rollback()
        return None


async def _finish_success(
    claim: PlatformJobClaim,
    result_ref: dict[str, Any],
) -> str | None:
    """完成 artifact 后以当前 attempt fence 提交结果。

    返回 ``succeeded`` / ``cancelled``；fence 已输给新 worker 时返回 ``None``。两种 False
    不能合并，否则「刚好在终态提交前取消」会被误作 lease 丢失，少发取消事件。
    """
    async with async_session() as db:
        if await jobs.cancellation_requested(db, claim):
            won = await jobs.finish_cancelled(db, claim, message="导出已取消")
            if won:
                await db.commit()
                return "cancelled"
            await db.rollback()
            return None
        won = await jobs.finish_success(
            db,
            claim,
            result_ref=result_ref,
            message="导出完成",
        )
        if won:
            await db.commit()
            return "succeeded"
        await db.rollback()
        return None


async def _unlink(path: Path) -> None:
    await asyncio.to_thread(path.unlink, missing_ok=True)


async def execute_export_pack(
    claim: PlatformJobClaim,
    report: ProgressReporter,
) -> ExecutorOutcome:
    """耐久任务执行器：执行时 re-gate、线程打包、围栏提交、SSE 通知。"""
    from app.services.event_bus import event_bus

    raw_wp_ids = claim.payload_ref.get("wp_ids")
    if not isinstance(raw_wp_ids, list) or not raw_wp_ids:
        error = ExportPackError("导出任务缺少底稿列表")
        terminal = await _finish_failure_or_cancel(claim, error)
        if terminal is not None:
            _broadcast_failed(claim, "导出任务缺少底稿列表")
            return ExecutorOutcome(finalized=True)
        raise error
    if len(raw_wp_ids) > MAX_EXPORT_ITEMS:
        error = ExportPackError("导出任务底稿数量超过 1000 项上限")
        terminal = await _finish_failure_or_cancel(claim, error)
        if terminal is not None:
            _broadcast_failed(claim, str(error))
            return ExecutorOutcome(finalized=True)
        raise error
    wp_ids = [str(value) for value in raw_wp_ids]
    total = len(wp_ids)
    job_id = str(claim.job_id)
    # 同一 job 的不同 attempt 禁止覆盖同一路径：过期 worker 无法替换新 worker 的成功 artifact。
    artifact_name = f"{job_id}.a{claim.attempt}.{claim.lease_token.hex}.zip"
    zip_path = EXPORT_DIR / artifact_name
    temp_path = EXPORT_DIR / f".{artifact_name}.{uuid.uuid4().hex}.tmp"
    stop = threading.Event()
    write_task: asyncio.Task[int] | None = None

    try:
        if not await report(0, total, "校验当前导出权限", "authorizing"):
            raise ExportPackLeaseLost("导出任务租约已失效")
        files = await _load_export_files(claim, wp_ids)
        if not any(files):
            raise ExportPackError("当前已无可导出的底稿，请刷新页面后重试")

        await asyncio.to_thread(EXPORT_DIR.mkdir, parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()

        async def _report_progress(done: int) -> bool:
            accepted = await report(done, total, f"已打包 {done}/{total}", "packing")
            if accepted:
                event_bus.broadcast_raw("export.progress", _progress_event(claim, done, total))
            return accepted

        def _on_zip_progress(done: int) -> None:
            result = asyncio.run_coroutine_threadsafe(_report_progress(done), loop).result()
            if result is not True:
                stop.set()
                raise ExportPackLeaseLost("导出任务已取消或租约已失效")

        write_task = asyncio.create_task(
            asyncio.to_thread(_write_zip, temp_path, zip_path, files, _on_zip_progress, stop)
        )
        written = await write_task

        if not await report(total, total, "正在确认导出结果", "finalizing"):
            raise ExportPackLeaseLost("导出任务租约已失效")

        download_url = f"/api/exports/{job_id}"
        result_ref = {
            "download_url": download_url,
            "zip_path": str(zip_path),
            "total": total,
            "done": total,
            "written": written,
            "attempt": claim.attempt,
        }
        final_status = await _finish_success(claim, result_ref)
        if final_status != "succeeded":
            # 取消或 lease 输掉时，该 attempt 的独有 artifact 不能遗留、更不能通知完成。
            await _unlink(zip_path)
            if final_status == "cancelled":
                from app.services.platform_job_events import broadcast_job_update

                broadcast_job_update(claim, status="cancelled", message="导出已取消")
                _broadcast_failed(claim, "导出已取消")
                return ExecutorOutcome(finalized=True)
            if await _finish_cancelled_if_requested(claim):
                from app.services.platform_job_events import broadcast_job_update

                broadcast_job_update(claim, status="cancelled", message="导出已取消")
                _broadcast_failed(claim, "导出已取消")
                return ExecutorOutcome(finalized=True)
            raise ExportPackLeaseLost("导出任务租约已失效")

        # DB 已 commit：前端收到完成事件后，status/download 都能读到 succeeded + artifact。
        from app.services.platform_job_events import broadcast_job_update

        broadcast_job_update(claim, status="succeeded", current=total, total=total, stage="completed", message="导出完成")
        event_bus.broadcast_raw(
            "export.complete",
            {
                **_progress_event(claim, total, total),
                "download_url": download_url,
            },
        )
        return ExecutorOutcome(result_ref=result_ref, finalized=True)

    except ExportPackLeaseLost:
        stop.set()
        if write_task is not None and not write_task.done():
            await asyncio.gather(asyncio.shield(write_task), return_exceptions=True)
        await _unlink(zip_path)
        if await _finish_cancelled_if_requested(claim):
            from app.services.platform_job_events import broadcast_job_update

            broadcast_job_update(claim, status="cancelled", message="导出已取消")
            _broadcast_failed(claim, "导出已取消")
            return ExecutorOutcome(finalized=True)
        raise
    except asyncio.CancelledError:
        stop.set()
        if write_task is not None and not write_task.done():
            await asyncio.gather(asyncio.shield(write_task), return_exceptions=True)
        await _unlink(zip_path)
        raise
    except BaseException as exc:
        stop.set()
        await _unlink(zip_path)
        terminal = await _finish_failure_or_cancel(claim, exc)
        if terminal is not None:
            from app.services.platform_job_events import broadcast_job_update

            broadcast_job_update(
                claim,
                status=terminal,
                message="导出已取消" if terminal == "cancelled" else str(exc),
                error_code=None if terminal == "cancelled" else type(exc).__name__,
            )
            _broadcast_failed(claim, "导出已取消" if terminal == "cancelled" else str(exc))
            return ExecutorOutcome(finalized=True)
        raise


register_executor(OPERATION, execute_export_pack)
