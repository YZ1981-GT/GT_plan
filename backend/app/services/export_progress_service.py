"""批量导出 SSE 进度推送 — proposal-remaining-18 C-3

异步处理批量导出任务：
- 接受 wp_ids 列表后立即返回 task_id
- 后台 asyncio.create_task 处理导出
- 通过 event_bus.broadcast_raw 推送 export.progress / export.complete / export.failed
- ZIP 文件存到 storage/exports/{task_id}.zip，提供 GET /api/exports/{task_id} 下载

ZIP 文件清理策略：完成 24h 后清理（已实现，由 export_cleanup_worker 每小时触发；
保留时长由环境变量 ``EXPORT_CLEANUP_MAX_AGE_HOURS`` 控制，默认 24h）

Validates: requirements.md §三 C-3 批量导出进度反馈
"""

from __future__ import annotations

import asyncio
import logging
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 导出目录：storage/exports/
EXPORT_DIR = Path("storage") / "exports"


@dataclass
class ExportTask:
    """批量导出任务状态"""
    task_id: str
    project_id: str
    user_id: str
    wp_ids: list[str]
    total: int
    done: int = 0
    status: str = "pending"  # pending / running / complete / failed
    file_path: Optional[Path] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


@dataclass(frozen=True)
class ExportFile:
    """已完成权限/项目过滤、可安全交给文件线程的导出项。"""

    source: Path
    arcname: str


class ExportProgressService:
    """批量导出任务管理器。

    任务状态暂按旧契约保存在内存；ZIP 查询一次完成，数据库会话关闭后才在线程中
    压缩到临时文件，避免大 ZIP 阻塞事件循环或在内存中保留两份。耐久任务迁移由
    ``platform-heavy-jobs-and-capacity-closure`` 批 B 承接。
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ExportTask] = {}
        self._background_tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # 任务创建 + 异步执行
    # ------------------------------------------------------------------

    def create_task(
        self,
        project_id: str,
        user_id: str,
        wp_ids: list[str],
    ) -> ExportTask:
        """创建任务并立即返回；后台任务保留强引用直至结束。"""
        task_id = str(uuid.uuid4())
        task = ExportTask(
            task_id=task_id,
            project_id=project_id,
            user_id=user_id,
            wp_ids=[str(x) for x in wp_ids],
            total=len(wp_ids),
        )
        self._tasks[task_id] = task

        coro = self._run_export(task)
        try:
            background = asyncio.create_task(coro)
        except RuntimeError:
            coro.close()
            logger.warning("export task %s scheduled outside event loop", task_id)
            task.status = "failed"
            task.error = "no running event loop"
        else:
            self._background_tasks.add(background)
            background.add_done_callback(self._background_tasks.discard)
        return task

    def get_task(self, task_id: str) -> Optional[ExportTask]:
        return self._tasks.get(task_id)

    # ------------------------------------------------------------------
    # 后台执行
    # ------------------------------------------------------------------

    async def _load_export_files(self, task: ExportTask) -> list[ExportFile | None]:
        """一次查询全部底稿；返回顺序与请求一致，缺失项以 None 占位。"""
        import sqlalchemy as sa

        from app.core.database import async_session as async_session_factory
        from app.models.workpaper_models import WorkingPaper, WpIndex

        try:
            project_id = uuid.UUID(task.project_id)
        except ValueError:
            return [None] * task.total
        ids: list[uuid.UUID] = []
        for raw in task.wp_ids:
            try:
                ids.append(uuid.UUID(raw))
            except ValueError:
                continue
        if not ids:
            return [None] * task.total

        async with async_session_factory() as db:
            rows = (await db.execute(
                sa.select(
                    WorkingPaper.id,
                    WorkingPaper.file_path,
                    WpIndex.audit_cycle,
                    WpIndex.wp_code,
                )
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(
                    WorkingPaper.id.in_(ids),
                    WorkingPaper.project_id == project_id,
                    WpIndex.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WpIndex.is_deleted == sa.false(),
                )
            )).all()

        by_id = {
            str(row[0]): ExportFile(
                source=Path(row[1]),
                arcname=f"{row[2] or 'OTHER'}/{row[3]}.xlsx",
            )
            for row in rows
            if row[1]
        }
        return [by_id.get(raw) for raw in task.wp_ids]

    @staticmethod
    def _write_zip(
        temp_path: Path,
        final_path: Path,
        files: list[ExportFile | None],
        progress: Callable[[int], None],
    ) -> None:
        """同步文件工作在线程执行；直接写盘并在成功后原子切换。"""
        try:
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for index, item in enumerate(files, start=1):
                    try:
                        if item is not None and item.source.is_file():
                            archive.write(item.source, item.arcname)
                    except OSError as exc:
                        logger.warning("export: skip %s due to %s", item.source if item else "missing", exc)
                    finally:
                        progress(index)
            temp_path.replace(final_path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

    async def _run_export(self, task: ExportTask) -> None:
        """批量取元数据，关闭 DB 会话后在线程直接生成 ZIP。"""
        from app.services.event_bus import event_bus

        task.status = "running"
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = EXPORT_DIR / f"{task.task_id}.zip"
        temp_path = EXPORT_DIR / f".{task.task_id}.{uuid.uuid4().hex}.tmp"
        try:
            files = await self._load_export_files(task)
            loop = asyncio.get_running_loop()
            await asyncio.to_thread(
                self._write_zip,
                temp_path,
                zip_path,
                files,
                lambda done: loop.call_soon_threadsafe(self._set_progress, task, done),
            )
            # call_soon_threadsafe 的逐项进度排在 to_thread 完成通知之前；再让出一次，确保
            # complete 永远晚于最后一条 progress。
            await asyncio.sleep(0)
            task.file_path = zip_path
            task.status = "complete"
            task.completed_at = datetime.now(timezone.utc)
            event_bus.broadcast_raw(
                "export.complete",
                {
                    "project_id": task.project_id,
                    "task_id": task.task_id,
                    "download_url": f"/api/exports/{task.task_id}",
                    "total": task.total,
                    "done": task.done,
                    "user_id": task.user_id,
                },
            )
            logger.info(
                "export task %s complete: %d/%d, file=%s",
                task.task_id,
                task.done,
                task.total,
                zip_path,
            )
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            logger.exception("export task %s failed", task.task_id)
            task.status = "failed"
            task.error = str(exc)
            event_bus.broadcast_raw(
                "export.failed",
                {
                    "project_id": task.project_id,
                    "task_id": task.task_id,
                    "error": str(exc),
                    "user_id": task.user_id,
                },
            )

    def _set_progress(self, task: ExportTask, done: int) -> None:
        task.done = done
        self._broadcast_progress(task)

    def _broadcast_progress(self, task: ExportTask) -> None:
        """推送 export.progress SSE 事件。"""
        from app.services.event_bus import event_bus

        percent = int(task.done * 100 / max(task.total, 1))
        event_bus.broadcast_raw(
            "export.progress",
            {
                "project_id": task.project_id,
                "task_id": task.task_id,
                "done": task.done,
                "total": task.total,
                "percent": percent,
                "user_id": task.user_id,
            },
        )

    # ------------------------------------------------------------------
    # 清理（task 5.7 / MT-8 配套，2026-05-22）
    # ------------------------------------------------------------------

    def cleanup_expired(self, max_age_hours: float = 24.0) -> dict[str, int]:
        """清理超过 max_age_hours 的 ZIP 文件 + 内存任务记录。

        三类清理目标：
          1. ``EXPORT_DIR/*.zip`` 中超过 max_age_hours 的物理文件（基于 mtime）
          2. ``self._tasks`` 中超过 max_age_hours 的内存任务（基于 completed_at 或 created_at）
          3. 孤儿文件（zip 在磁盘但 task 已被清理）也归入分类 1

        Returns
        -------
        ``{"removed_files": N, "removed_tasks": M, "kept_files": K}``
        """
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=max_age_hours)

        removed_files = 0
        kept_files = 0
        if EXPORT_DIR.exists():
            for fp in EXPORT_DIR.glob("*.zip"):
                try:
                    mtime = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc)
                    if mtime < cutoff:
                        fp.unlink()
                        removed_files += 1
                    else:
                        kept_files += 1
                except OSError as exc:
                    logger.warning(
                        "[export] cleanup zip %s failed: %s", fp.name, exc
                    )

        removed_tasks = 0
        for task_id, task in list(self._tasks.items()):
            ref_time = task.completed_at or task.created_at
            if ref_time and ref_time < cutoff:
                self._tasks.pop(task_id, None)
                removed_tasks += 1

        if removed_files or removed_tasks:
            logger.info(
                "[export] cleanup: removed %d files, %d tasks; kept %d files",
                removed_files, removed_tasks, kept_files,
            )
        return {
            "removed_files": removed_files,
            "removed_tasks": removed_tasks,
            "kept_files": kept_files,
        }


# 全局单例
export_progress_service = ExportProgressService()
