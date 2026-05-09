"""ImportOrchestrator — 账表导入编排器（唯一入口）。

职责（见 design.md §1 / §7 / Sprint 3 Task 39-41）：

1. ``detect(files)``        : 组合 Detector → Identifier → AdapterRegistry，
                              返回 ``LedgerDetectionResult`` 供前端预检弹窗使用。
2. ``submit(upload_token, confirmed_mappings)`` : 用户确认后落 ``ImportJob``，
                              交 worker 走 parser → validator → writer → staged→active 切换。
3. ``resume(job_id)``       : 断点续传 — 复用 ``import_artifacts`` 表，失败作业可 retry。

设计原则：
- detect() 是纯计算（不写 DB），返回 LedgerDetectionResult 供前端预检
- submit() 创建 ImportJob + ImportArtifact，交 worker 异步执行
- resume() 从 import_artifacts 恢复失败作业
"""

from __future__ import annotations

import logging
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .adapters import registry as adapter_registry
from .detection_types import (
    FileDetection,
    LedgerDetectionResult,
    SheetDetection,
    TableType,
)
from .detector import detect_file, detect_file_from_path
from .identifier import identify
from .merge_strategy import merge_sheets
from .year_detector import detect_year

logger = logging.getLogger(__name__)

__all__ = ["ImportOrchestrator", "execute_pipeline", "PipelineResult"]


class ImportOrchestrator:
    """账表导入编排器 — detect / submit / resume 三阶段。

    设计原则：
    - detect() 是纯计算（不写 DB），返回 LedgerDetectionResult 供前端预检
    - submit() 创建 ImportJob + ImportArtifact，交 worker 异步执行
    - resume() 从 import_artifacts 恢复失败作业
    """

    # ---- Phase 1: Detect (read-only, no DB writes) ----

    @staticmethod
    def detect(
        files: list[tuple[str, bytes]],
        *,
        year_override: int | None = None,
        adapter_hint: str | None = None,
    ) -> LedgerDetectionResult:
        """Detect file types, identify sheets, match adapters.

        Args:
            files: List of (filename, content_bytes) tuples.
            year_override: User-specified year (skips auto-detection).
            adapter_hint: User-specified adapter id (e.g. "yonyou").

        Returns:
            LedgerDetectionResult with all detection info for frontend preview.
        """
        upload_token = str(uuid.uuid4())
        file_detections: list[FileDetection] = []
        all_errors: list[Any] = []

        # Step 1: Detect each file
        for filename, content in files:
            fd = detect_file(content, filename)
            file_detections.append(fd)
            all_errors.extend(fd.errors)

        # Steps 2-7: Shared logic
        return ImportOrchestrator._finalize_detection(
            file_detections,
            upload_token=upload_token,
            all_errors=all_errors,
            year_override=year_override,
            adapter_hint=adapter_hint,
        )

    # ---- Phase 2: Submit (creates ImportJob, stores artifacts) ----

    @staticmethod
    def detect_from_paths(
        file_paths: list[str],
        *,
        year_override: int | None = None,
        adapter_hint: str | None = None,
    ) -> LedgerDetectionResult:
        """Detect from file paths — 支持 600MB+ 大文件，不全量读入内存。

        与 detect() 逻辑完全相同，区别仅在于输入是文件路径而非 bytes。
        CSV 只读前 64KB，xlsx 用 openpyxl 流式读取。

        Args:
            file_paths: List of file absolute/relative paths.
            year_override: User-specified year.
            adapter_hint: User-specified adapter id.

        Returns:
            LedgerDetectionResult (same as detect()).
        """
        import os

        upload_token = str(uuid.uuid4())
        file_detections: list[FileDetection] = []
        all_errors: list[Any] = []

        # Step 1: Detect each file from path
        for path in file_paths:
            filename = os.path.basename(path)
            fd = detect_file_from_path(path, filename)
            file_detections.append(fd)
            all_errors.extend(fd.errors)

        # Step 2-7: Same as detect()
        return ImportOrchestrator._finalize_detection(
            file_detections,
            upload_token=upload_token,
            all_errors=all_errors,
            year_override=year_override,
            adapter_hint=adapter_hint,
        )

    @staticmethod
    def _finalize_detection(
        file_detections: list[FileDetection],
        *,
        upload_token: str,
        all_errors: list[Any],
        year_override: int | None = None,
        adapter_hint: str | None = None,
    ) -> LedgerDetectionResult:
        """Shared logic for detect() and detect_from_paths() — Steps 2-7."""

        # Step 2: Identify each sheet
        for fd in file_detections:
            identified_sheets: list[SheetDetection] = []
            for sheet in fd.sheets:
                identified = identify(sheet)
                identified_sheets.append(identified)
            fd.sheets = identified_sheets

        # Step 3: Match best adapter
        adapter_id: str | None = None
        for fd in file_detections:
            if adapter_hint:
                adapter = adapter_registry.get(adapter_hint)
                if adapter:
                    adapter_id = adapter.id
                    break
            best_adapter, score = adapter_registry.detect_best(fd)
            if score > 0.1:
                adapter_id = best_adapter.id
                break

        # Step 4: Year detection
        if year_override is not None:
            detected_year: int | None = year_override
            year_confidence = 100
            year_evidence: dict = {"override": True, "chosen_priority": "user_override"}
        else:
            detected_year, year_confidence, year_evidence = detect_year(
                file_detections
            )

        # Step 5: Merge strategy
        all_sheets = [s for fd in file_detections for s in fd.sheets]
        merged_groups = merge_sheets(all_sheets, strategy="auto")
        merged_tables: dict[TableType, list[tuple[str, str]]] = {}
        for group in merged_groups:
            if len(group.sheets) > 1:
                merged_tables[group.table_type] = group.sheets

        # Step 6: Check missing tables
        detected_types: set[TableType] = {
            s.table_type
            for fd in file_detections
            for s in fd.sheets
            if s.table_type != "unknown"
        }
        required_types: set[TableType] = {"balance", "ledger"}
        missing_tables: list[TableType] = [
            t for t in required_types if t not in detected_types
        ]

        can_derive: dict[TableType, bool] = {}
        if "aux_balance" not in detected_types and "balance" in detected_types:
            can_derive["aux_balance"] = True
        if "aux_ledger" not in detected_types and "ledger" in detected_types:
            can_derive["aux_ledger"] = True

        # Step 7: Determine if manual confirm needed
        requires_manual = any(
            s.confidence_level in ("low", "manual_required")
            for fd in file_detections
            for s in fd.sheets
        )

        return LedgerDetectionResult(
            upload_token=upload_token,
            files=file_detections,
            detected_year=detected_year,
            year_confidence=year_confidence,
            year_evidence=year_evidence,
            merged_tables=merged_tables,
            missing_tables=missing_tables,
            can_derive=can_derive,
            errors=all_errors,
            requires_manual_confirm=requires_manual,
        )

    @staticmethod
    async def submit(
        db: AsyncSession,
        *,
        upload_token: str,
        project_id: UUID,
        year: int,
        confirmed_mappings: list[dict],
        file_manifest: list[dict],
        storage_uri: str,
        total_size_bytes: int = 0,
        force_activate: bool = False,
        created_by: UUID | None = None,
        adapter_id: str | None = None,
    ) -> dict:
        """Create ImportJob + ImportArtifact, return job info.

        Args:
            db: Database session.
            upload_token: Token from detect phase.
            project_id: Target project.
            year: Confirmed accounting year.
            confirmed_mappings: User-confirmed column mappings per sheet.
            file_manifest: List of file info dicts
                [{"file_name": "...", "size_bytes": N, "mime_type": "..."}].
            storage_uri: URI where uploaded files are stored
                (e.g. "local:///tmp/uploads/{upload_token}").
            total_size_bytes: Total size of all uploaded files.
            force_activate: Skip L2/L3 validation.
            created_by: User UUID.
            adapter_id: Matched adapter id.

        Returns:
            {"job_id": UUID, "status": "queued"}
        """
        from app.models.dataset_models import (
            ArtifactStatus,
            ImportArtifact,
            ImportJob,
            JobStatus,
        )

        # Create ImportArtifact (file reference, not raw bytes)
        artifact = ImportArtifact(
            id=uuid.uuid4(),
            project_id=project_id,
            upload_token=upload_token,
            status=ArtifactStatus.active,
            storage_uri=storage_uri,
            total_size_bytes=total_size_bytes,
            file_manifest=file_manifest,
            file_count=len(file_manifest),
            created_by=created_by,
        )
        db.add(artifact)
        await db.flush()

        # Create ImportJob
        job = ImportJob(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            status=JobStatus.queued,
            artifact_id=artifact.id,
            custom_mapping={"confirmed_mappings": confirmed_mappings},
            options={
                "upload_token": upload_token,
                "adapter_id": adapter_id,
                "force_activate": force_activate,
            },
            created_by=created_by,
        )
        db.add(job)
        await db.flush()

        return {"job_id": job.id, "status": "queued"}

    # ---- Phase 3: Resume (断点续传) ----

    @staticmethod
    async def resume(
        db: AsyncSession,
        *,
        job_id: UUID,
    ) -> dict:
        """Resume a failed job by resetting status to queued.

        Reuses existing ImportArtifact (files already uploaded).
        Increments retry_count. Fails if max_retries exceeded.

        Returns:
            {"job_id": UUID, "status": "queued", "retry_count": N}

        Raises:
            ValueError: If job not found, not in failed status, or max retries exceeded.
        """
        from sqlalchemy import select

        from app.models.dataset_models import ImportJob, JobStatus

        stmt = select(ImportJob).where(ImportJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            raise ValueError(f"ImportJob {job_id} not found")

        if job.status not in (JobStatus.failed,):
            raise ValueError(
                f"Cannot resume job in status '{job.status.value}'; "
                "only 'failed' jobs can be resumed"
            )

        if job.retry_count >= job.max_retries:
            raise ValueError(
                f"Job {job_id} has exceeded max retries ({job.max_retries})"
            )

        job.status = JobStatus.queued
        job.retry_count = job.retry_count + 1
        job.error_message = None
        job.progress_pct = 0
        job.current_phase = None
        await db.flush()

        return {
            "job_id": job.id,
            "status": "queued",
            "retry_count": job.retry_count,
        }


# S7-6: execute_pipeline / PipelineResult 已迁到 pipeline.py
# 以下为向后兼容 re-export（调用方可继续 from .orchestrator import ...）
from .pipeline import (  # noqa: E402, F401
    PipelineResult,
    ProgressCallback,
    CancelChecker,
    execute_pipeline,
)
