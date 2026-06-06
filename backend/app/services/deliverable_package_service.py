"""交付物异步打包 — ZIP + manifest + SSE 进度"""

from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase13_models import ExportJobStatus, WordExportStatus, WordExportTask
from app.services.completeness_service import CompletenessService
from app.services.export_job_service import ExportJobService

logger = logging.getLogger(__name__)

PACKAGE_STORAGE = Path("storage") / "deliverable_packages"


class DeliverablePackageService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._job_svc = ExportJobService(db)

    async def create_package_job(
        self,
        project_id: UUID,
        year: int,
        user_id: UUID,
        *,
        ignore_incomplete: bool = False,
    ) -> tuple[UUID, list[str]]:
        """创建打包任务；返回 (job_id, warnings)"""
        warnings: list[str] = []
        if not ignore_incomplete:
            check = await CompletenessService(self.db).check(project_id, year)
            if not check.passed:
                warnings = list(check.warnings)

        result = await self.db.execute(
            sa.select(WordExportTask).where(
                WordExportTask.project_id == project_id,
                WordExportTask.status == WordExportStatus.confirmed.value,
            )
        )
        confirmed_tasks = list(result.scalars().all())

        latest_by_type: dict[str, WordExportTask] = {}
        for task in confirmed_tasks:
            prev = latest_by_type.get(task.doc_type)
            if prev is None or (task.updated_at or task.created_at) > (
                prev.updated_at or prev.created_at
            ):
                latest_by_type[task.doc_type] = task

        job = await self._job_svc.create_job(
            project_id,
            "deliverable_package",
            {"year": year, "warnings": warnings},
            user_id,
            total=max(len(latest_by_type), 1),
        )
        for task in latest_by_type.values():
            await self._job_svc.add_item(job.id, task.id)

        return job.id, warnings

    async def run_package_job(self, job_id: UUID) -> Path | None:
        """执行打包并更新进度（后台调用）"""
        from app.services.event_bus import event_bus

        job = await self._job_svc.get_job(job_id)
        if job is None:
            return None

        items = await self._job_svc.get_job_items(job_id)
        PACKAGE_STORAGE.mkdir(parents=True, exist_ok=True)
        zip_path = PACKAGE_STORAGE / f"{job_id}.zip"

        manifest_lines = [
            f"# 交付物清单 — 生成于 {datetime.now(timezone.utc).isoformat()}",
            f"project_id={job.project_id}",
        ]
        done = 0
        failed = 0

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for idx, item in enumerate(items):
                task = None
                if item.word_export_task_id:
                    task = await self.db.get(WordExportTask, item.word_export_task_id)
                if task is None or not task.file_path:
                    failed += 1
                    await self._job_svc.update_item_status(
                        item.id, ExportJobStatus.failed.value, "无文件"
                    )
                    continue

                src = Path(task.file_path)
                if not src.exists():
                    failed += 1
                    await self._job_svc.update_item_status(
                        item.id, ExportJobStatus.failed.value, "文件不存在"
                    )
                    continue

                arcname = f"{task.doc_type}/{src.name}"
                zf.write(src, arcname)
                manifest_lines.append(
                    f"{task.doc_type}\t{src.name}\t{task.file_size or src.stat().st_size}"
                )
                await self._job_svc.update_item_status(
                    item.id, ExportJobStatus.succeeded.value
                )
                done += 1

                event_bus.broadcast_raw(
                    "deliverable.package.progress",
                    {
                        "project_id": str(job.project_id),
                        "job_id": str(job_id),
                        "done": done,
                        "total": job.progress_total,
                    },
                )
                await asyncio.sleep(0)  # yield for SSE

            zf.writestr("deliverable_manifest.txt", "\n".join(manifest_lines))

        zip_path.write_bytes(buf.getvalue())
        await self._job_svc.update_progress(job_id, done, failed)
        payload = dict(job.payload or {})
        payload["zip_path"] = str(zip_path)
        job.payload = payload
        await self.db.flush()

        event_bus.broadcast_raw(
            "deliverable.package.complete",
            {
                "project_id": str(job.project_id),
                "job_id": str(job_id),
                "download_url": f"/api/projects/{job.project_id}/deliverables/package/{job_id}/download",
            },
        )
        return zip_path
