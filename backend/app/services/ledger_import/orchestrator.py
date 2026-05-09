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



# ---------------------------------------------------------------------------
# S6-3: execute_pipeline — 纯数据处理管线
#
# 从 import_job_runner._execute_v2 抽出的数据核心部分（不含 Job 状态机/锁）。
# 调用方（Worker）负责状态切换、锁管理、artifact 消费；本函数只做数据流。
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field
from typing import Awaitable, Callable


@dataclass
class PipelineResult:
    """execute_pipeline 返回值。"""

    success: bool
    dataset_id: UUID | None = None
    balance_rows: int = 0
    aux_balance_rows: int = 0
    ledger_rows: int = 0
    aux_ledger_rows: int = 0
    total_rows_parsed: int = 0
    warnings: int = 0
    blocking_findings: int = 0
    year: int | None = None
    error_message: str | None = None
    blocking_messages: list[str] = field(default_factory=list)


# Callback types
ProgressCallback = Callable[[int, str], Awaitable[None]]  # (pct, message)
CancelChecker = Callable[[], Awaitable[bool]]  # returns True if canceled


async def execute_pipeline(
    *,
    job_id: UUID,
    project_id: UUID,
    year: int | None,
    custom_mapping: dict | None,
    created_by: UUID | None,
    file_sources: list[tuple[str, Any]],  # list[(filename, Path)]
    force_activate: bool = False,
    progress_cb: ProgressCallback | None = None,
    cancel_check: CancelChecker | None = None,
) -> PipelineResult:
    """v2 引擎纯数据管线（detect → parse → convert → validate → write → activate）。

    S6-3: 从 import_job_runner._execute_v2 抽出，让 Worker 只负责状态机/锁。

    Args:
        job_id: ImportJob UUID（仅用于日志 trace）
        project_id: 目标项目
        year: 会计年度（None 则 fallback 2025）
        custom_mapping: {"confirmed_mappings": [{file_name, sheet_name, mappings}]}
        created_by: 激活者 UUID
        file_sources: [(filename, Path), ...]，已由 Worker 加载
        force_activate: 跳过 L2/L3 校验强制激活
        progress_cb: 进度回调 async (pct, message)
        cancel_check: 取消检查 async () → True 则抛 RuntimeError("导入已被用户取消")

    Returns:
        PipelineResult

    Raises:
        RuntimeError: 用户取消 / blocking findings / 其他运行时错误
        ValueError: 文件空 / 参数错误
    """
    import os
    from app.core.database import async_session
    from app.models.audit_platform_models import (
        TbAuxBalance, TbAuxLedger, TbBalance, TbLedger,
    )
    from app.services.dataset_service import DatasetService
    from app.services.ledger_import.converter import (
        convert_balance_rows, convert_ledger_rows,
    )
    from app.services.ledger_import.detector import detect_file_from_path
    from app.services.ledger_import.identifier import identify
    from app.services.ledger_import.parsers.csv_parser import iter_csv_rows_from_path
    from app.services.ledger_import.parsers.excel_parser import iter_excel_rows_from_path
    from app.services.ledger_import.validator import evaluate_activation, validate_l1
    from app.services.ledger_import.writer import activate_dataset, prepare_rows_with_raw_extra
    from app.services.smart_import_engine import rebuild_aux_balance_summary

    if not file_sources:
        raise ValueError("无可导入的文件")

    async def _progress(pct: int, msg: str) -> None:
        if progress_cb is not None:
            await progress_cb(pct, msg)

    async def _check_cancel() -> None:
        if cancel_check is not None and await cancel_check():
            raise RuntimeError("导入已被用户取消")

    # ── Detect + Identify ──
    logger.info("Pipeline %s phase=detect_identify", job_id)
    await _progress(10, "识别文件结构")
    detections: dict[str, Any] = {}  # path → FileDetection
    for filename, filepath in file_sources:
        fd = detect_file_from_path(str(filepath), filename)
        for sheet in fd.sheets:
            idx = fd.sheets.index(sheet)
            fd.sheets[idx] = identify(sheet)
        detections[str(filepath)] = fd

    # Resolve confirmed mappings
    confirmed = {}
    if custom_mapping and "confirmed_mappings" in custom_mapping:
        for m in custom_mapping["confirmed_mappings"]:
            sheet_key = f"{m.get('file_name', '')}!{m.get('sheet_name', '')}"
            confirmed[sheet_key] = m.get("mappings", {})

    import_year = year or 2025

    # ── Create staged dataset ──
    logger.info("Pipeline %s phase=create_staged", job_id)
    async with async_session() as stage_db:
        staged = await DatasetService.create_staged(
            stage_db,
            project_id=project_id,
            year=import_year,
            source_type="ledger_import_v2",
            job_id=job_id,
            created_by=created_by,
        )
        staging_dataset_id = staged.id
        await stage_db.commit()
    logger.info("Pipeline %s created staged dataset %s", job_id, staging_dataset_id)

    # S7-2: 用 bulk_insert_staged 通用函数替代 4 个重复的 _insert_* 闭包
    # 自省字段：按 table_model.__table__.columns 过滤 row 字典，
    # 自动注入 id/project_id/year/dataset_id/is_deleted 公共字段
    from app.services.ledger_import.writer import bulk_insert_staged

    async def _insert_balance(rows: list[dict]) -> None:
        await bulk_insert_staged(
            async_session, TbBalance, rows,
            project_id=project_id, year=import_year,
            dataset_id=staging_dataset_id, is_deleted=True,
        )

    async def _insert_aux_balance(rows: list[dict]) -> None:
        await bulk_insert_staged(
            async_session, TbAuxBalance, rows,
            project_id=project_id, year=import_year,
            dataset_id=staging_dataset_id, is_deleted=True,
        )

    async def _insert_ledger(rows: list[dict]) -> None:
        await bulk_insert_staged(
            async_session, TbLedger, rows,
            project_id=project_id, year=import_year,
            dataset_id=staging_dataset_id, is_deleted=True,
        )

    async def _insert_aux_ledger(rows: list[dict]) -> None:
        await bulk_insert_staged(
            async_session, TbAuxLedger, rows,
            project_id=project_id, year=import_year,
            dataset_id=staging_dataset_id, is_deleted=True,
        )

    # ── Parse → Convert → Validate → Write (streaming) ──
    logger.info("Pipeline %s phase=parse_write_streaming", job_id)
    await _progress(20, "解析并写入数据")

    all_findings: list[Any] = []
    total_rows_parsed = 0
    total_balance_written = 0
    total_aux_balance_written = 0
    total_ledger_written = 0
    total_aux_ledger_written = 0

    total_est_rows = sum(
        s.row_count_estimate
        for fd in detections.values()
        for s in fd.sheets
        if s.table_type != "unknown"
    ) or 1

    for filename, filepath in file_sources:
        fd = detections[str(filepath)]
        ext = os.path.splitext(filename)[1].lower()

        for sheet in fd.sheets:
            if sheet.table_type == "unknown":
                logger.info(
                    "Pipeline %s skipping unknown sheet: %s!%s",
                    job_id, filename, sheet.sheet_name,
                )
                continue

            sheet_key = f"{filename}!{sheet.sheet_name}"
            col_mapping = confirmed.get(sheet_key) or {}
            if not col_mapping:
                for cm in sheet.column_mappings:
                    if cm.standard_field and cm.confidence >= 50:
                        col_mapping[cm.column_header] = cm.standard_field
                logger.info(
                    "Pipeline %s %s!%s: auto-detected mapping (%d cols)",
                    job_id, filename, sheet.sheet_name, len(col_mapping),
                )

            headers = sheet.detection_evidence.get("header_cells", [])
            if not headers and sheet.preview_rows:
                headers = [str(c) for c in sheet.preview_rows[0]] if sheet.preview_rows else []

            logger.info(
                "Pipeline %s processing sheet %s!%s: type=%s est=%d cols=%d mapped=%d",
                job_id, filename, sheet.sheet_name,
                sheet.table_type, sheet.row_count_estimate,
                len(headers), len(col_mapping),
            )

            # forward-fill cols (S6-12)
            ff_cols = [
                cm.column_index for cm in sheet.column_mappings
                if cm.standard_field in ("account_code", "account_name")
            ]

            if ext in (".xlsx", ".xlsm"):
                row_iter = iter_excel_rows_from_path(
                    str(filepath), sheet.sheet_name,
                    data_start_row=sheet.data_start_row,
                    forward_fill_cols=ff_cols or None,
                )
            elif ext in (".csv", ".tsv"):
                encoding = fd.encoding or "utf-8"
                row_iter = iter_csv_rows_from_path(
                    str(filepath), encoding=encoding,
                    data_start_row=sheet.data_start_row,
                )
            else:
                continue

            chunk_count = 0
            for chunk in row_iter:
                chunk_count += 1
                dict_rows = []
                for raw_row in chunk:
                    row_dict = {}
                    for i, val in enumerate(raw_row):
                        if i < len(headers):
                            row_dict[headers[i]] = val
                        else:
                            row_dict[f"col_{i}"] = val
                    dict_rows.append(row_dict)

                std_rows, extra_warnings = prepare_rows_with_raw_extra(
                    dict_rows, col_mapping, headers
                )
                all_findings.extend(extra_warnings)

                findings, cleaned = validate_l1(
                    std_rows, sheet.table_type, column_mapping=col_mapping,
                    file_name=filename, sheet_name=sheet.sheet_name,
                )
                all_findings.extend(findings)

                if sheet.table_type in ("balance", "aux_balance"):
                    bal, aux_bal = convert_balance_rows(cleaned)
                    await _insert_balance(bal)
                    await _insert_aux_balance(aux_bal)
                    total_balance_written += len(bal)
                    total_aux_balance_written += len(aux_bal)
                elif sheet.table_type in ("ledger", "aux_ledger"):
                    ledger, aux_ledger, _stats = convert_ledger_rows(cleaned)
                    await _insert_ledger(ledger)
                    await _insert_aux_ledger(aux_ledger)
                    total_ledger_written += len(ledger)
                    total_aux_ledger_written += len(aux_ledger)

                total_rows_parsed += len(chunk)
                pct = min(20 + int(65 * total_rows_parsed / total_est_rows), 85)
                await _progress(pct, f"已处理 {total_rows_parsed:,}/{total_est_rows:,} 行")

                if chunk_count % 5 == 0:
                    await _check_cancel()

    logger.info(
        "Pipeline %s streaming done: %d+%d balance, %d+%d ledger",
        job_id, total_balance_written, total_aux_balance_written,
        total_ledger_written, total_aux_ledger_written,
    )

    # ── Activation gate ──
    logger.info("Pipeline %s phase=activation_gate", job_id)
    await _progress(85, "评估激活条件")
    gate = evaluate_activation(all_findings, force=force_activate)

    if not gate.allowed:
        blocking_msgs = [f.message for f in gate.blocking_findings[:10]]
        logger.warning(
            "Pipeline %s blocking findings (%d), dataset %s kept staged",
            job_id, len(gate.blocking_findings), staging_dataset_id,
        )
        # 清理 staged 数据
        async with async_session() as mf_db:
            await DatasetService.mark_failed(mf_db, staging_dataset_id, cleanup_rows=True)
            await mf_db.commit()
        raise RuntimeError(
            f"校验失败（{len(gate.blocking_findings)} 条阻塞错误），"
            f"数据未激活：{'; '.join(blocking_msgs[:3])}"
        )

    # ── Activate ──
    logger.info("Pipeline %s phase=activate_dataset %s", job_id, staging_dataset_id)
    await _progress(90, "激活数据集")
    async with async_session() as act_db:
        await activate_dataset(
            act_db,
            dataset_id=staging_dataset_id,
            activated_by=created_by,
            record_summary={
                "balance_rows": total_balance_written,
                "aux_balance_rows": total_aux_balance_written,
                "ledger_rows": total_ledger_written,
                "aux_ledger_rows": total_aux_ledger_written,
            },
            validation_summary={
                "warnings": len([f for f in all_findings if not f.blocking]),
                "blocking": len([f for f in all_findings if f.blocking]),
                "force_activated": force_activate,
            },
        )
        await act_db.commit()

    # ── Rebuild aux summary ──
    logger.info("Pipeline %s phase=rebuild_aux_summary", job_id)
    await _progress(93, "重建辅助汇总")
    async with async_session() as summary_db:
        await rebuild_aux_balance_summary(
            project_id, import_year, summary_db,
            dataset_id=staging_dataset_id,
        )
        await summary_db.commit()

    return PipelineResult(
        success=True,
        dataset_id=staging_dataset_id,
        balance_rows=total_balance_written,
        aux_balance_rows=total_aux_balance_written,
        ledger_rows=total_ledger_written,
        aux_ledger_rows=total_aux_ledger_written,
        total_rows_parsed=total_rows_parsed,
        warnings=len([f for f in all_findings if not f.blocking]),
        blocking_findings=len([f for f in all_findings if f.blocking]),
        year=import_year,
    )
