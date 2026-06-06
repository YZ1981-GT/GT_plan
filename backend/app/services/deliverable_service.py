"""交付物服务 — 扩展 ExportTaskService，交付中心 CRUD + 版本 + 双路径存储"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.models.report_models import AuditReport, ReportStatus
from app.services.export_task_service import ExportTaskService
from app.models.base import ProjectStatus
from app.models.core import Project
from app.services.completeness_service import CompletenessService
from app.services.deliverable_hash_service import DeliverableHashService
from app.services.deliverable_snapshot_service import DeliverableSnapshotService

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage"))
DELIVERABLE_SUBDIR = "deliverables"

TERMINAL_REEXPORT_STATUSES = {"confirmed", "signed", "archived"}


@dataclass
class DeliverableDTO:
    task_id: UUID
    project_id: UUID
    doc_type: str
    status: str
    file_name: str | None
    version_no: int
    file_size: int | None
    exporter_name: str | None
    exported_at: datetime | None
    template_type: str | None
    selected_sections: list | None


@dataclass
class StoreResult:
    version: WordExportTaskVersion
    download_url: str
    platform_persist_failed: bool = False
    file_path: str | None = None
    html_path: str | None = None


@dataclass
class VersionCompareResult:
    version_a: int
    version_b: int
    exported_at_diff: dict | None
    file_size_diff: dict | None
    selected_sections_diff: dict | None


class DeliverableService(ExportTaskService):
    """交付物维度服务"""

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def _deliverable_dir(self, project_id: UUID, task_id: UUID) -> Path:
        return STORAGE_ROOT / DELIVERABLE_SUBDIR / str(project_id) / str(task_id)

    async def _latest_version(self, task_id: UUID) -> WordExportTaskVersion | None:
        result = await self.db.execute(
            sa.select(WordExportTaskVersion)
            .where(WordExportTaskVersion.word_export_task_id == task_id)
            .order_by(WordExportTaskVersion.version_no.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_version_chain(self, task_id: UUID) -> list[WordExportTaskVersion]:
        result = await self.db.execute(
            sa.select(WordExportTaskVersion)
            .where(WordExportTaskVersion.word_export_task_id == task_id)
            .order_by(WordExportTaskVersion.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_version(
        self, task_id: UUID, version_no: int
    ) -> WordExportTaskVersion | None:
        result = await self.db.execute(
            sa.select(WordExportTaskVersion).where(
                WordExportTaskVersion.word_export_task_id == task_id,
                WordExportTaskVersion.version_no == version_no,
            )
        )
        return result.scalar_one_or_none()

    async def create_version(
        self,
        task_id: UUID,
        *,
        file_path: str | None,
        html_path: str | None,
        user_id: UUID,
        source_snapshot_refs: dict | None = None,
        selected_sections: list | None = None,
        file_size: int | None = None,
        created_via: str = "generate",
    ) -> WordExportTaskVersion:
        result = await self.db.execute(
            sa.select(sa.func.coalesce(sa.func.max(WordExportTaskVersion.version_no), 0))
            .where(WordExportTaskVersion.word_export_task_id == task_id)
        )
        max_no = int(result.scalar_one() or 0)
        version_no = max_no + 1

        version = WordExportTaskVersion(
            word_export_task_id=task_id,
            version_no=version_no,
            file_path=file_path,
            html_path=html_path,
            file_size=file_size,
            created_by=user_id,
            source_snapshot_refs=source_snapshot_refs,
            selected_sections=selected_sections,
            created_via=created_via,
        )
        self.db.add(version)
        await self.db.flush()
        return version

    async def export_or_new_deliverable(
        self,
        project_id: UUID,
        doc_type: str,
        template_type: str | None,
        user_id: UUID,
        *,
        existing_task_id: UUID | None = None,
    ) -> tuple[WordExportTask, bool]:
        """终态再导出 → 新建独立交付物；否则复用/追加版本"""
        if existing_task_id:
            task = await self.get_task(existing_task_id)
            if task and task.status in TERMINAL_REEXPORT_STATUSES:
                task = await self.create_task(project_id, doc_type, template_type, user_id)
                return task, True
            if task:
                return task, False

        history = await self.get_history(project_id)
        same_type = [t for t in history if t.doc_type == doc_type]
        if same_type and same_type[0].status in TERMINAL_REEXPORT_STATUSES:
            task = await self.create_task(project_id, doc_type, template_type, user_id)
            return task, True
        if same_type:
            return same_type[0], False

        task = await self.create_task(project_id, doc_type, template_type, user_id)
        return task, True

    async def compare_versions(
        self, task_id: UUID, version_a: int, version_b: int
    ) -> VersionCompareResult:
        va = await self.get_version(task_id, version_a)
        vb = await self.get_version(task_id, version_b)
        if va is None or vb is None:
            raise ValueError("版本不存在")

        if version_a == version_b:
            return VersionCompareResult(version_a, version_b, None, None, None)

        def _diff(field_a, field_b, name: str) -> dict | None:
            if field_a == field_b:
                return None
            return {name: {"a": field_a, "b": field_b}}

        return VersionCompareResult(
            version_a=version_a,
            version_b=version_b,
            exported_at_diff=_diff(va.created_at, vb.created_at, "exported_at"),
            file_size_diff=_diff(va.file_size, vb.file_size, "file_size"),
            selected_sections_diff=_diff(va.selected_sections, vb.selected_sections, "selected_sections"),
        )

    async def capture_snapshot_refs(
        self, project_id: UUID, year: int, doc_type: str = "audit_report"
    ) -> dict:
        snap_svc = DeliverableSnapshotService(self.db)
        return await snap_svc.capture_snapshot_refs(project_id, year, doc_type)

    async def _assert_eqcr_passed(self, project_id: UUID, year: int) -> None:
        result = await self.db.execute(
            sa.select(AuditReport.status).where(
                AuditReport.project_id == project_id,
                AuditReport.year == year,
            )
        )
        status = result.scalar_one_or_none()
        allowed = {ReportStatus.eqcr_approved.value, ReportStatus.final.value}
        if status not in allowed:
            raise ValueError("需先完成 EQCR 复核")

    async def confirm_deliverable(
        self, task_id: UUID, user_id: UUID, year: int
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        await self._assert_eqcr_passed(task.project_id, year)
        return await self.confirm_task(task_id, user_id)

    async def sign(
        self,
        task_id: UUID,
        signer_id: UUID,
        sign_type: str,
        year: int,
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")

        await self._assert_eqcr_passed(task.project_id, year)

        if task.status != WordExportStatus.confirmed.value:
            raise ValueError(
                f"仅 confirmed 状态可签章，当前状态: {task.status}"
            )

        await self.update_status(task_id, WordExportStatus.signed.value)
        task = await self.get_task(task_id)
        assert task is not None
        task.signed_by = signer_id
        task.signed_at = datetime.now(timezone.utc)
        task.sign_type = sign_type
        await self.db.flush()
        logger.info(
            "交付物已签章: task_id=%s, signer=%s, sign_type=%s",
            task_id,
            signer_id,
            sign_type,
        )
        return task

    async def render_and_store(
        self,
        task_id: UUID,
        *,
        docx_bytes: bytes | None = None,
        docx_path: Path | None = None,
        html_content: str | None = None,
        user_id: UUID,
        source_snapshot_refs: dict | None = None,
        selected_sections: list | None = None,
        file_name: str | None = None,
        created_via: str = "generate",
    ) -> StoreResult:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")

        out_dir = self._deliverable_dir(task.project_id, task_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        latest = await self._latest_version(task_id)
        next_no = (latest.version_no + 1) if latest else 1

        ext = ".docx"
        fname = file_name or f"{task.doc_type}_v{next_no}{ext}"
        file_path = out_dir / fname
        html_path = out_dir / f"{task.doc_type}_v{next_no}.html"

        platform_persist_failed = False
        try:
            if docx_path and docx_path.exists():
                file_path.write_bytes(docx_path.read_bytes())
            elif docx_bytes:
                file_path.write_bytes(docx_bytes)
            else:
                raise ValueError("无文件内容可存储")

            if html_content:
                html_path.write_text(html_content, encoding="utf-8")
            file_size = file_path.stat().st_size
        except Exception as exc:
            logger.error("平台存储写入失败 task=%s: %s", task_id, exc)
            platform_persist_failed = True
            file_size = len(docx_bytes) if docx_bytes else 0
            file_path = None
            html_path = None

        version = await self.create_version(
            task_id,
            file_path=str(file_path) if file_path else None,
            html_path=str(html_path) if html_path and html_path.exists() else None,
            user_id=user_id,
            source_snapshot_refs=source_snapshot_refs,
            selected_sections=selected_sections,
            file_size=file_size if not platform_persist_failed else None,
            created_via=created_via,
        )

        if not platform_persist_failed and file_path and file_path.exists():
            await DeliverableHashService(self.db).bind_version_hash(
                version, task, user_id
            )

        if not platform_persist_failed:
            task.file_path = str(file_path)
            task.html_path = str(html_path) if html_path and html_path.exists() else None
            task.file_size = file_size
            task.source_snapshot_refs = source_snapshot_refs
            task.selected_sections = selected_sections
            if task.status == WordExportStatus.draft.value:
                task.status = WordExportStatus.generated.value
            await self.db.flush()

        download_url = f"/api/projects/{task.project_id}/deliverables/{task_id}/versions/{version.version_no}/download"
        return StoreResult(
            version=version,
            download_url=download_url,
            platform_persist_failed=platform_persist_failed,
            file_path=str(file_path) if file_path else None,
            html_path=str(html_path) if html_path and html_path.exists() else None,
        )

    async def list_deliverables(
        self,
        project_id: UUID,
        *,
        doc_type: str | None = None,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        keyword: str | None = None,
    ) -> list[DeliverableDTO]:
        query = (
            sa.select(WordExportTask, User.username)
            .outerjoin(User, User.id == WordExportTask.created_by)
            .where(WordExportTask.project_id == project_id)
        )

        if doc_type:
            query = query.where(WordExportTask.doc_type == doc_type)
        if status:
            query = query.where(WordExportTask.status == status)
        if date_from:
            query = query.where(WordExportTask.created_at >= date_from)
        if date_to:
            query = query.where(WordExportTask.created_at <= date_to)

        result = await self.db.execute(query.order_by(WordExportTask.created_at.desc()))
        rows = result.all()

        dtos: list[DeliverableDTO] = []
        for task, exporter_name in rows:
            version = await self._latest_version(task.id)
            file_name = None
            if task.file_path:
                file_name = Path(task.file_path).name
            elif version and version.file_path:
                file_name = Path(version.file_path).name

            if keyword:
                kw = keyword.lower()
                name_match = file_name and kw in file_name.lower()
                exporter_match = exporter_name and kw in exporter_name.lower()
                if not name_match and not exporter_match:
                    continue

            dtos.append(
                DeliverableDTO(
                    task_id=task.id,
                    project_id=task.project_id,
                    doc_type=task.doc_type,
                    status=task.status,
                    file_name=file_name,
                    version_no=version.version_no if version else 1,
                    file_size=task.file_size or (version.file_size if version else None),
                    exporter_name=exporter_name,
                    exported_at=task.updated_at or task.created_at,
                    template_type=task.template_type,
                    selected_sections=task.selected_sections,
                )
            )
        return dtos

    async def submit_for_approval(
        self, task_id: UUID, user_id: UUID
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        if task.status != WordExportStatus.editing.value:
            raise ValueError(f"仅 editing 状态可提交审批，当前: {task.status}")
        return await self.update_status(
            task_id, WordExportStatus.pending_approval.value
        )

    async def approve(
        self, task_id: UUID, approver_id: UUID, year: int
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        if task.status != WordExportStatus.pending_approval.value:
            raise ValueError(
                f"仅 pending_approval 状态可批准，当前: {task.status}"
            )
        await self._assert_eqcr_passed(task.project_id, year)
        await self.update_status(task_id, WordExportStatus.confirmed.value)
        task = await self.get_task(task_id)
        assert task is not None
        task.approval_by = approver_id
        task.approval_at = datetime.now(timezone.utc)
        task.confirmed_by = approver_id
        task.confirmed_at = datetime.now(timezone.utc)
        task.reject_reason = None
        await self.db.flush()
        return task

    async def reject(
        self, task_id: UUID, approver_id: UUID, reason: str
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        if task.status != WordExportStatus.pending_approval.value:
            raise ValueError(
                f"仅 pending_approval 状态可驳回，当前: {task.status}"
            )
        await self.update_status(task_id, WordExportStatus.editing.value)
        task = await self.get_task(task_id)
        assert task is not None
        task.reject_reason = reason
        task.approval_by = approver_id
        task.approval_at = datetime.now(timezone.utc)
        await self.db.flush()
        return task

    async def archive_project_deliverables(
        self,
        project_id: UUID,
        user_id: UUID,
        year: int,
        *,
        force: bool = False,
    ) -> int:
        check = await CompletenessService(self.db).check(project_id, year)
        if not check.passed and not force:
            raise ValueError(
                "完整性检查未通过，无法归档。"
                + ("；".join(check.warnings) if check.warnings else "")
            )

        result = await self.db.execute(
            sa.select(WordExportTask).where(
                WordExportTask.project_id == project_id,
                WordExportTask.status.in_(
                    [
                        WordExportStatus.confirmed.value,
                        WordExportStatus.signed.value,
                    ]
                ),
            )
        )
        tasks = list(result.scalars().all())
        now = datetime.now(timezone.utc)
        count = 0
        for task in tasks:
            await self.update_status(task.id, WordExportStatus.archived.value)
            task.archived_at = now
            count += 1

        if count > 0:
            project = await self.db.get(Project, project_id)
            if project and project.status != ProjectStatus.archived:
                all_result = await self.db.execute(
                    sa.select(WordExportTask).where(
                        WordExportTask.project_id == project_id
                    )
                )
                all_tasks = list(all_result.scalars().all())
                terminal = {WordExportStatus.archived.value}
                if all_tasks and all(t.status in terminal for t in all_tasks):
                    project.status = ProjectStatus.archived

        await self.db.flush()
        return count

    async def unarchive(
        self,
        task_id: UUID,
        admin_id: UUID,
        reason: str,
    ) -> WordExportTask:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"交付物不存在: {task_id}")
        if task.status != WordExportStatus.archived.value:
            raise ValueError(f"仅 archived 状态可解除归档，当前: {task.status}")

        previous = task.status
        await self.update_status(task_id, WordExportStatus.confirmed.value)
        task = await self.get_task(task_id)
        assert task is not None
        task.archived_at = None

        from app.services.audit_log_helper import append_audit_log

        await append_audit_log(
            self.db,
            {
                "user_id": admin_id,
                "project_id": task.project_id,
                "action": "deliverable_unarchive",
                "resource_type": "word_export_task",
                "resource_id": str(task_id),
                "details": {
                    "event_type": "archive_unarchive",
                    "reason": reason,
                    "previous_status": previous,
                },
            },
        )
        await self.db.flush()
        return task
