"""bulk-tab 导入的通用耐久任务执行器。"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from app.core.database import async_session
from app.models.core import User
from app.services import platform_job_service as jobs
from app.services.bulk_tab.bulk_progress import bulk_progress_service
from app.services.bulk_tab.snapshot_guard import AtomicityMode
from app.services.platform_job_registry import (
    ExecutorOutcome,
    ProgressReporter,
    register_executor,
)

OPERATION = "bulk_tab_import"


class BulkImportJobError(RuntimeError):
    retryable = False

    def __init__(self, spool_path: Path, cause: BaseException):
        self.cleanup_path = spool_path
        super().__init__(str(cause) or type(cause).__name__)


def _validated_spool(project_id, raw_path: object) -> Path:
    from app.services.bulk_tab.bulk_async_runner import BULK_IMPORT_DIR

    root = (BULK_IMPORT_DIR / str(project_id)).resolve()
    path = Path(str(raw_path or "")).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("批量导入 spool 路径越界") from exc
    if path.suffix.lower() != ".zip" or not path.is_file():
        raise FileNotFoundError("批量导入 spool 已丢失")
    return path


def _manifest_count(path: Path) -> int:
    from app.services.bulk_tab.zip_handler import ZipReader

    with ZipReader.from_path(path) as reader:
        files = reader.manifest.get("files", [])
        return len(files) if isinstance(files, list) else 0


class _Progress:
    def __init__(
        self,
        task_id: str,
        total: int,
        reporter: ProgressReporter,
    ) -> None:
        self.task_id = task_id
        self.current = 0
        self.total = total
        self.reporter = reporter
        self.tasks: set[asyncio.Task] = set()
        self.failed = False

    def _done(self, task: asyncio.Task) -> None:
        self.tasks.discard(task)
        try:
            if task.result() is not True:
                self.failed = True
        except BaseException:
            self.failed = True

    def tick(self, message: str = "") -> None:
        self.current += 1
        bulk_progress_service.tick(self.task_id, message)
        task = asyncio.create_task(
            self.reporter(
                self.current,
                self.total,
                message,
                "importing",
            )
        )
        self.tasks.add(task)
        task.add_done_callback(self._done)

    async def drain(self) -> None:
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        if self.failed:
            raise RuntimeError("任务进度租约已失效")


async def execute_bulk_import(
    claim: jobs.PlatformJobClaim,
    report: ProgressReporter,
) -> ExecutorOutcome:
    from app.services.bulk_tab import bulk_import_service
    from app.services.bulk_tab.bulk_async_runner import (
        cleanup_import_spool,
        hash_spool_file,
    )
    from app.services.wp_visibility.entry_integration import make_bulk_preflight

    payload = claim.payload_ref
    path = _validated_spool(claim.project_id, payload.get("spool_path"))
    actual_sha256, actual_size = await asyncio.to_thread(hash_spool_file, path)
    if (
        actual_sha256 != str(payload.get("sha256") or "")
        or actual_size != int(payload.get("size") or -1)
    ):
        raise BulkImportJobError(path, ValueError("批量导入 spool 摘要不匹配"))
    task_id = str(claim.job_id)
    total = await asyncio.to_thread(_manifest_count, path)
    bulk_progress_service.create_task(
        str(claim.project_id),
        str(claim.actor_id),
        "import",
        total,
        task_id=task_id,
    )
    bulk_progress_service.set_total(task_id, total)
    bulk_progress_service.resume(task_id)
    if not await report(0, total, "开始导入", "validating"):
        raise BulkImportJobError(path, RuntimeError("任务租约已失效"))
    progress = _Progress(task_id, total, report)

    try:
        async with async_session() as db:
            user = (
                await db.execute(sa.select(User).where(User.id == claim.actor_id))
            ).scalar_one_or_none()
            if user is None:
                raise ValueError("用户不存在")
            preflight = make_bulk_preflight(db, user, entry_kind="worker")
            report_result = await bulk_import_service.run(
                db=db,
                project_id=str(claim.project_id),
                zip_bytes=path,
                strategy=str(payload.get("strategy") or "overwrite"),
                user=user,
                atomicity=AtomicityMode(
                    str(payload.get("atomicity") or AtomicityMode.PER_SHEET.value)
                ),
                progress=progress,
                preflight=preflight,
            )
            await progress.drain()
            result_ref = {"report": report_result.to_dict()}
            won = await jobs.finish_success(
                db,
                claim,
                result_ref=result_ref,
                message="导入完成",
            )
            if not won:
                await db.rollback()
                raise RuntimeError("任务租约已失效，导入事务已回滚")
            await db.commit()

        bulk_progress_service.set_result(task_id, report_result.to_dict())
        bulk_progress_service.complete(task_id, "导入完成")
        await cleanup_import_spool(path)
        return ExecutorOutcome(result_ref=result_ref, finalized=True)
    except BaseException as exc:
        try:
            await progress.drain()
        except BaseException:
            pass
        if isinstance(exc, asyncio.CancelledError):
            raise
        bulk_progress_service.fail(task_id, str(exc))
        raise BulkImportJobError(path, exc) from exc


register_executor(OPERATION, execute_bulk_import)
