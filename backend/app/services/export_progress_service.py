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
import io
import logging
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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


class ExportProgressService:
    """批量导出任务管理器 — 内存维护任务状态 + 后台异步生成 ZIP"""

    def __init__(self) -> None:
        self._tasks: dict[str, ExportTask] = {}

    # ------------------------------------------------------------------
    # 任务创建 + 异步执行
    # ------------------------------------------------------------------

    def create_task(
        self,
        project_id: str,
        user_id: str,
        wp_ids: list[str],
    ) -> ExportTask:
        """创建任务并立即返回；后台 asyncio.create_task 异步处理"""
        task_id = str(uuid.uuid4())
        task = ExportTask(
            task_id=task_id,
            project_id=project_id,
            user_id=user_id,
            wp_ids=[str(x) for x in wp_ids],
            total=len(wp_ids),
        )
        self._tasks[task_id] = task

        # 后台异步执行（不阻塞响应）
        try:
            asyncio.create_task(self._run_export(task))
        except RuntimeError:
            # 测试环境无 running loop 时同步报错记录
            logger.warning("export task %s scheduled outside event loop", task_id)
            task.status = "failed"
            task.error = "no running event loop"
        return task

    def get_task(self, task_id: str) -> Optional[ExportTask]:
        return self._tasks.get(task_id)

    # ------------------------------------------------------------------
    # 后台执行
    # ------------------------------------------------------------------

    async def _run_export(self, task: ExportTask) -> None:
        """实际生成 ZIP 文件 + SSE 推送进度"""
        from app.core.database import async_session as async_session_factory
        from app.services.event_bus import event_bus
        from app.models.workpaper_models import WorkingPaper, WpIndex
        import sqlalchemy as sa

        task.status = "running"
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = EXPORT_DIR / f"{task.task_id}.zip"

        try:
            buffer = io.BytesIO()
            async with async_session_factory() as db:
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for idx, wp_id_str in enumerate(task.wp_ids, start=1):
                        try:
                            await self._add_one_workpaper(db, zf, wp_id_str)
                        except Exception as exc:  # 单个底稿失败不阻断整体
                            logger.warning(
                                "export task %s: skip wp %s due to %s",
                                task.task_id,
                                wp_id_str,
                                exc,
                            )
                        finally:
                            task.done = idx
                            self._broadcast_progress(task)

            # 写入磁盘
            buffer.seek(0)
            zip_path.write_bytes(buffer.read())
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

    async def _add_one_workpaper(self, db, zf: zipfile.ZipFile, wp_id_str: str) -> None:
        """从 DB 加载单个底稿文件并写入 ZIP"""
        from app.models.workpaper_models import WorkingPaper, WpIndex
        import sqlalchemy as sa

        try:
            wp_id = uuid.UUID(wp_id_str)
        except ValueError:
            return
        result = await db.execute(
            sa.select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
        )
        row = result.first()
        if not row:
            return
        wp, idx = row
        if not wp.file_path:
            return
        fp = Path(wp.file_path)
        if not fp.exists():
            return
        arcname = f"{idx.audit_cycle or 'OTHER'}/{idx.wp_code}.xlsx"
        zf.write(fp, arcname)

    def _broadcast_progress(self, task: ExportTask) -> None:
        """推送 export.progress SSE 事件"""
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
