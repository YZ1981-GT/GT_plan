"""底稿文件打包导出的耐久任务执行器（spec platform-heavy-jobs-and-capacity-closure B3）。

迁移对象是 ``export_progress_service`` 的「按 wp_ids 打包已存底稿文件 → ZIP」链路。
迁移后：

- Web 提交只做权限 + job INSERT（``create_or_get_job``），立即返回 ``job_id``。
- 执行由 ``platform_job_worker`` 认领：一次查询全部底稿元数据，关闭 DB 后在线程写盘，
  进度经 ``ProgressReporter`` 写 ``platform_jobs`` 行并推 typed SSE。
- 旧 ``export_progress_service`` 只作兼容读：``get_task`` 先查内存（还活着的旧任务），
  再查 ``platform_jobs``（新任务），直到退役日期后整个模块删除。
- 前端 ``ExportProgressBar`` / 状态端点无需改：状态端点已改为优先读 ``platform_jobs``，
  SSE 事件格式不变（``export.progress`` / ``export.complete`` / ``export.failed``）。

文件清理策略不变：ZIP 文件由 ``export_cleanup_worker`` 按 mtime 清理。
"""
from __future__ import annotations

import logging
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from app.core.database import async_session
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.export_progress_service import EXPORT_DIR
from app.services.platform_job_registry import (
    ExecutorOutcome,
    ProgressReporter,
    register_executor,
)
from app.services.platform_job_service import PlatformJobClaim

logger = logging.getLogger(__name__)

OPERATION = "workpaper_pack_export"


@dataclass(frozen=True)
class _ExportFile:
    source: Path
    arcname: str


async def _load_export_files(
    project_id: uuid.UUID,
    wp_ids: list[str],
) -> list[_ExportFile | None]:
    """一次查询全部底稿；返回顺序与请求一致，缺失项以 None 占位。"""
    ids: list[uuid.UUID] = []
    for raw in wp_ids:
        try:
            ids.append(uuid.UUID(raw))
        except ValueError:
            continue
    if not ids:
        return [None] * len(wp_ids)

    async with async_session() as db:
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
                    WorkingPaper.id.in_(ids),
                    WorkingPaper.project_id == project_id,
                    WpIndex.project_id == project_id,
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
    return [by_id.get(raw) for raw in wp_ids]


def _write_zip(
    temp_path: Path,
    final_path: Path,
    files: list[_ExportFile | None],
    on_progress: Any,
) -> None:
    """同步文件工作在线程执行；直接写盘并在成功后原子切换。"""
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, item in enumerate(files, start=1):
                try:
                    if item is not None and item.source.is_file():
                        archive.write(item.source, item.arcname)
                except OSError as exc:
                    logger.warning(
                        "export pack: skip %s due to %s",
                        item.source if item else "missing",
                        exc,
                    )
                finally:
                    if callable(on_progress):
                        on_progress(index)
        temp_path.replace(final_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


async def execute_export_pack(
    claim: PlatformJobClaim,
    report: ProgressReporter,
) -> ExecutorOutcome:
    """耐久任务执行器：按 wp_ids 打包底稿文件 → ZIP → SSE 完成事件。"""
    import asyncio

    from app.services.event_bus import event_bus

    payload = claim.payload_ref
    wp_ids: list[str] = payload.get("wp_ids", [])
    total = len(wp_ids)

    if not await report(0, total, "加载底稿元数据", "loading"):
        return ExecutorOutcome(finalized=False)

    files = await _load_export_files(claim.project_id, wp_ids)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    job_id = str(claim.job_id)
    zip_path = EXPORT_DIR / f"{job_id}.zip"
    temp_path = EXPORT_DIR / f".{job_id}.{uuid.uuid4().hex}.tmp"

    loop = asyncio.get_running_loop()
    progress_done = 0

    def _on_zip_progress(done: int) -> None:
        nonlocal progress_done
        progress_done = done
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(
                report(done, total, f"已打包 {done}/{total}", "packing")
            )
        )

    try:
        await asyncio.to_thread(
            _write_zip,
            temp_path,
            zip_path,
            files,
            _on_zip_progress,
        )
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise

    download_url = f"/api/exports/{job_id}"
    result_ref = {
        "download_url": download_url,
        "zip_path": str(zip_path),
        "total": total,
        "done": progress_done,
    }

    # 推 SSE 完成事件（保持与旧 export_progress_service 相同格式）
    event_bus.broadcast_raw(
        "export.complete",
        {
            "project_id": str(claim.project_id),
            "task_id": job_id,
            "download_url": download_url,
            "total": total,
            "done": progress_done,
            "user_id": str(claim.actor_id),
        },
    )

    return ExecutorOutcome(result_ref=result_ref)


register_executor(OPERATION, execute_export_pack)
