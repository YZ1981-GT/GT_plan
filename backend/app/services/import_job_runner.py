"""Database-backed import job runner.

The execution source of truth is the `import_jobs` table. The same runner can be
called by the web process for local development or by an external worker process
for production deployments.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa

from app.core.config import settings
from app.core.database import async_session
from app.models.dataset_models import ArtifactStatus, ImportJob, JobStatus
from app.services.import_artifact_service import ImportArtifactService
from app.services.import_job_service import ImportJobService
from app.services.import_queue_service import ImportQueueService
from app.services.ledger_import_upload_service import LedgerImportUploadService
from app.services.smart_import_engine import SmartImportError, smart_import_streaming

logger = logging.getLogger(__name__)


class ImportJobCanceled(RuntimeError):
    """Raised when a running import job is canceled cooperatively."""


class ImportJobRunner:
    """Run durable import jobs using DB state."""

    _cancel_events: dict[UUID, asyncio.Event] = {}
    _running_tasks: dict[UUID, asyncio.Task] = {}

    @classmethod
    def enqueue(cls, job_id: UUID) -> None:
        existing = cls._running_tasks.get(job_id)
        if existing and not existing.done():
            return
        task = asyncio.create_task(cls.run_job(job_id))
        cls._running_tasks[job_id] = task
        task.add_done_callback(lambda _task, jid=job_id: cls._running_tasks.pop(jid, None))

    @classmethod
    def request_cancel(cls, job_id: UUID) -> None:
        event = cls._cancel_events.get(job_id)
        if event is not None:
            event.set()

    @classmethod
    async def run_worker_once(cls, *, limit: int | None = None) -> int:
        """Enqueue currently queued jobs.

        This is intentionally DB-backed and lightweight. Multiple app instances
        may call it; `claim_queued_job` in `run_job` makes duplicate scheduling
        harmless.
        """
        limit = limit or max(1, settings.LEDGER_IMPORT_WORKER_BATCH_SIZE)
        async with async_session() as db:
            result = await db.execute(
                sa.select(ImportJob.id)
                .where(ImportJob.status == JobStatus.queued)
                .order_by(ImportJob.created_at.asc())
                .limit(limit)
            )
            job_ids = [row[0] for row in result.fetchall()]
        for job_id in job_ids:
            cls.enqueue(job_id)
        return len(job_ids)

    @classmethod
    async def recover_jobs(cls) -> None:
        """Recover queued jobs and timeout stale running jobs."""
        timed_out_jobs: list[ImportJob] = []
        async with async_session() as db:
            timed_out_jobs.extend(await ImportJobService.check_timed_out(db))
            if timed_out_jobs:
                await db.commit()

            stale_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=20)
            running_states = (
                JobStatus.running,
                JobStatus.validating,
                JobStatus.writing,
                JobStatus.activating,
            )
            result = await db.execute(
                sa.select(ImportJob).where(
                    ImportJob.status.in_(running_states),
                    sa.or_(
                        sa.and_(
                            ImportJob.heartbeat_at.is_(None),
                            ImportJob.started_at.isnot(None),
                            ImportJob.started_at < stale_cutoff,
                        ),
                        ImportJob.heartbeat_at < stale_cutoff,
                    ),
                )
            )
            stale_jobs = result.scalars().all()
            for stale in stale_jobs:
                stale.status = JobStatus.timed_out
                stale.error_message = "导入作业心跳丢失，已标记超时"
                stale.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                timed_out_jobs.append(stale)
            if stale_jobs:
                await db.commit()

            queue_result = await db.execute(
                sa.select(ImportJob.id).where(ImportJob.status == JobStatus.queued)
            )
            queued_job_ids = [row[0] for row in queue_result.fetchall()]
            pending_result = await db.execute(
                sa.select(ImportJob.id).where(ImportJob.status == JobStatus.pending)
            )
            pending_job_ids = [row[0] for row in pending_result.fetchall()]
            for pending_id in pending_job_ids:
                await ImportJobService.transition(
                    db,
                    pending_id,
                    JobStatus.queued,
                    progress_pct=0,
                    progress_message="导入作业恢复排队",
                )
            if pending_job_ids:
                await db.commit()

        for jid in queued_job_ids + pending_job_ids:
            cls.enqueue(jid)
        await cls.run_worker_once()
        for job in timed_out_jobs:
            await cls._release_timed_out_job(job)

    @classmethod
    async def run_forever(
        cls,
        *,
        poll_interval_seconds: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        """Run the durable worker loop until cancelled."""
        interval = max(1, poll_interval_seconds or settings.LEDGER_IMPORT_WORKER_POLL_INTERVAL_SECONDS)
        limit = max(1, batch_size or settings.LEDGER_IMPORT_WORKER_BATCH_SIZE)
        logger.info("ImportJob worker started: interval=%ss batch_size=%s", interval, limit)
        while True:
            try:
                await cls.recover_jobs()
                await cls.run_worker_once(limit=limit)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("ImportJob worker stopping")
                raise
            except Exception:
                logger.warning("ImportJob worker loop error", exc_info=True)
                await asyncio.sleep(interval)

    @classmethod
    async def _release_timed_out_job(cls, job: ImportJob) -> None:
        ImportQueueService.release_lock(job.project_id)
        batch_id_raw = (job.options or {}).get("queue_batch_id")
        try:
            async with async_session() as status_db:
                from app.services.dataset_service import DatasetService

                await DatasetService.mark_failed_for_job(status_db, job.id)
                if not batch_id_raw:
                    await status_db.commit()
                    return
                await ImportQueueService.fail_job(
                    job.project_id,
                    UUID(batch_id_raw),
                    status_db,
                    message=job.error_message or "导入作业超时",
                    year=job.year,
                )
        except Exception:
            logger.debug("ImportJob timeout lock release failed: %s", job.id, exc_info=True)

    @classmethod
    async def run_job(cls, job_id: UUID) -> None:
        async with async_session() as db:
            job = await ImportJobService.get_job(db, job_id)
            if not job:
                logger.warning("ImportJob not found: %s", job_id)
                return
            if job.status == JobStatus.pending:
                await ImportJobService.transition(db, job_id, JobStatus.queued, progress_pct=0, progress_message="导入作业已排队")
                await db.commit()
            elif job.status != JobStatus.queued:
                logger.info("ImportJob %s skipped because status=%s", job_id, job.status.value)
                return

        await cls._execute(job_id)

    @classmethod
    async def _load_file_sources(cls, *, project_id: UUID, upload_token: str):
        if not upload_token:
            raise ValueError("ImportJob 缺少 upload_token，无法恢复上传产物")

        async with async_session() as db:
            artifact = await ImportArtifactService.get_by_upload_token(
                db,
                project_id=project_id,
                upload_token=upload_token,
            )
            if artifact and artifact.status == ArtifactStatus.expired:
                raise ValueError("上传产物已过期，请重新上传")
            if artifact and artifact.storage_uri:
                bundle_dir = ImportArtifactService.materialize_bundle(
                    artifact.storage_uri,
                    upload_token=upload_token,
                )
                if bundle_dir is not None:
                    return LedgerImportUploadService.get_bundle_files_from_path(bundle_dir)

        return LedgerImportUploadService.get_bundle_files(project_id, upload_token)

    @classmethod
    async def _execute(cls, job_id: UUID) -> None:
        async with async_session() as state_db:
            job = await ImportJobService.get_job(state_db, job_id)
            if not job:
                return
            if await ImportJobService.active_project_job_exists(
                state_db,
                job.project_id,
                excluding_job_id=job_id,
            ):
                logger.info("ImportJob %s waits because project %s has an active job", job_id, job.project_id)
                return
            claimed = await ImportJobService.claim_queued_job(state_db, job_id)
            if claimed is None:
                logger.info("ImportJob %s was already claimed or canceled", job_id)
                return
            await state_db.commit()

        async with async_session() as read_db:
            job = await ImportJobService.get_job(read_db, job_id)
            if not job:
                return
            options = dict(job.options or {})
            project_id = job.project_id
            year = job.year or None
            custom_mapping = job.custom_mapping
            created_by = job.created_by
            batch_id_raw = options.get("queue_batch_id")
            payload_style = options.get("payload_style") or "ledger"
            upload_token = options.get("upload_token")

        file_sources = await cls._load_file_sources(project_id=project_id, upload_token=upload_token)

        # v2 引擎分支（对齐 design §13）
        from app.services.feature_flags import is_enabled
        if is_enabled("ledger_import_v2", project_id):
            await cls._execute_v2(
                job_id,
                project_id=project_id,
                year=year,
                options=options,
                custom_mapping=custom_mapping,
                created_by=created_by,
                upload_token=upload_token,
            )
            return
        # 以下为旧 smart_import_engine 逻辑...

        cancel_event = asyncio.Event()
        cls._cancel_events[job_id] = cancel_event

        async def _monitor_cancel() -> None:
            while not cancel_event.is_set():
                await asyncio.sleep(1)
                try:
                    async with async_session() as cancel_db:
                        current = await ImportJobService.get_job(cancel_db, job_id)
                        if current and current.status == JobStatus.canceled:
                            cancel_event.set()
                            return
                except Exception:
                    logger.debug("ImportJob cancel monitor failed: %s", job_id, exc_info=True)

        monitor_task = asyncio.create_task(_monitor_cancel())

        def _on_progress(pct: int, message: str) -> None:
            if cancel_event.is_set():
                raise ImportJobCanceled("导入作业已取消")
            ImportQueueService.update_progress(project_id, pct, message)
            asyncio.create_task(cls._persist_progress(job_id, pct, message))

        try:
            async with async_session() as import_db:
                await ImportJobService.transition(
                    import_db,
                    job_id,
                    JobStatus.validating,
                    progress_pct=3,
                    progress_message="校验导入输入",
                )
                await import_db.commit()

            async with async_session() as import_db:
                await ImportJobService.transition(
                    import_db,
                    job_id,
                    JobStatus.writing,
                    progress_pct=10,
                    progress_message="写入 staged 数据",
                )
                await import_db.commit()

                result = await smart_import_streaming(
                    project_id=project_id,
                    file_contents=file_sources,
                    db=import_db,
                    year_override=year,
                    custom_mapping=custom_mapping,
                    progress_callback=_on_progress,
                    job_id=job_id,
                    created_by=created_by,
                    force_activate=bool(options.get("force_activate")),
                )

            from app.services.ledger_import_application_service import LedgerImportApplicationService

            if payload_style == "account_chart":
                result_payload = LedgerImportApplicationService.build_account_chart_result_payload(result)
            else:
                result_payload = LedgerImportApplicationService.build_ledger_job_result_payload(
                    result,
                    job_batch_id=UUID(batch_id_raw) if batch_id_raw else None,
                )

            async with async_session() as state_db:
                await ImportJobService.transition(
                    state_db,
                    job_id,
                    JobStatus.activating,
                    progress_pct=95,
                    progress_message="数据集已激活，正在收尾",
                )
                await ImportJobService.transition(
                    state_db,
                    job_id,
                    JobStatus.completed,
                    progress_pct=100,
                    progress_message="导入完成",
                    result_summary=result_payload,
                )
                await state_db.commit()

            if upload_token:
                async with async_session() as artifact_db:
                    artifact = await ImportArtifactService.get_by_upload_token(
                        artifact_db,
                        project_id=project_id,
                        upload_token=upload_token,
                    )
                    if artifact:
                        await ImportArtifactService.mark_consumed(artifact_db, artifact.id)
                        await artifact_db.commit()

            if batch_id_raw:
                async with async_session() as status_db:
                    await ImportQueueService.complete_job(
                        project_id,
                        UUID(batch_id_raw),
                        status_db,
                        message=f"导入完成: {result.get('data_sheets_imported')}",
                        result=result_payload,
                        year=result.get("year"),
                        record_count=LedgerImportApplicationService._count_total_records(result),
                    )
            else:
                ImportQueueService.release_lock(project_id)

        except Exception as exc:
            logger.exception("ImportJob 执行失败: %s", job_id)
            from app.services.ledger_import_application_service import LedgerImportApplicationService

            is_canceled = isinstance(exc, ImportJobCanceled)
            diagnostics = exc.diagnostics if isinstance(exc, SmartImportError) else None
            failure_errors = exc.errors if isinstance(exc, SmartImportError) else None
            failure_year = exc.year if isinstance(exc, SmartImportError) else year
            failure_message = "导入已取消" if is_canceled else str(exc)
            if payload_style == "account_chart":
                failure_payload = LedgerImportApplicationService.build_account_chart_failure_payload(
                    failure_message,
                    diagnostics=diagnostics,
                    errors=failure_errors,
                    year=failure_year,
                )
            else:
                failure_payload = LedgerImportApplicationService.build_ledger_failure_payload(
                    failure_message,
                    job_batch_id=UUID(batch_id_raw) if batch_id_raw else None,
                    diagnostics=diagnostics,
                    errors=failure_errors,
                    year=failure_year,
                )

            async with async_session() as state_db:
                try:
                    current = await ImportJobService.get_job(state_db, job_id)
                    if current and current.status == JobStatus.canceled:
                        pass
                    else:
                        await ImportJobService.transition(
                            state_db,
                            job_id,
                            JobStatus.failed,
                            progress_pct=0,
                            error_message=failure_message[:1000],
                            result_summary=failure_payload,
                        )
                    await state_db.commit()
                except Exception:
                    await state_db.rollback()

            if batch_id_raw:
                async with async_session() as status_db:
                    await ImportQueueService.fail_job(
                        project_id,
                        UUID(batch_id_raw),
                        status_db,
                        message=failure_message if is_canceled else f"导入失败: {exc}",
                        result=failure_payload,
                        year=failure_year,
                    )
            else:
                ImportQueueService.release_lock(project_id)
        finally:
            monitor_task.cancel()
            cls._cancel_events.pop(job_id, None)
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

    @classmethod
    async def _execute_v2(
        cls,
        job_id: UUID,
        *,
        project_id: UUID,
        year: int | None,
        options: dict,
        custom_mapping: dict | None,
        created_by: UUID | None,
        upload_token: str | None,
    ) -> None:
        """Execute import using v2 ledger_import engine.

        Full pipeline: detect → parse → convert → validate → write → activate.
        """
        import os
        from pathlib import Path

        try:
            from app.services.ledger_import.converter import convert_balance_rows, convert_ledger_rows
            from app.services.ledger_import.detector import detect_file_from_path
            from app.services.ledger_import.identifier import identify
            from app.services.ledger_import.parsers.csv_parser import iter_csv_rows_from_path
            from app.services.ledger_import.parsers.excel_parser import iter_excel_rows_from_path
            from app.services.ledger_import.validator import evaluate_activation, validate_l1
            from app.services.ledger_import.writer import prepare_rows_with_raw_extra
        except Exception as imp_exc:
            logger.exception("ImportJob %s: v2 module import failed", job_id)
            async with async_session() as db:
                await ImportJobService.transition(
                    db, job_id, JobStatus.failed,
                    progress_pct=0,
                    error_message=f"v2 模块导入失败: {str(imp_exc)[:500]}",
                )
                await db.commit()
            ImportQueueService.release_lock(project_id)
            return

        logger.info("ImportJob %s: v2 engine starting", job_id)

        try:
            # ── Phase 1: Load files ──
            await cls._persist_progress(job_id, 5, "加载上传文件")
            file_sources = await cls._load_file_sources(
                project_id=project_id, upload_token=upload_token
            )
            if not file_sources:
                raise ValueError("无可导入的文件")

            # ── Phase 2: Detect + Identify ──
            await cls._persist_progress(job_id, 10, "识别文件结构")
            async with async_session() as db:
                await ImportJobService.transition(
                    db, job_id, JobStatus.validating,
                    progress_pct=10, progress_message="识别文件结构",
                )
                await db.commit()

            # file_sources is list[(filename, Path)]
            file_paths = [str(p) for _, p in file_sources]
            detections = {}  # path → FileDetection
            for filename, filepath in file_sources:
                fd = detect_file_from_path(str(filepath), filename)
                for sheet in fd.sheets:
                    sheet_identified = identify(sheet)
                    # Replace with identified version
                    idx = fd.sheets.index(sheet)
                    fd.sheets[idx] = sheet_identified
                detections[str(filepath)] = fd

            # ── Phase 3: Parse → Convert → Validate → Write (streaming) ──
            await cls._persist_progress(job_id, 20, "解析并写入数据")
            async with async_session() as db:
                await ImportJobService.transition(
                    db, job_id, JobStatus.writing,
                    progress_pct=20, progress_message="解析并写入数据",
                )
                await db.commit()

            # Resolve confirmed mappings
            confirmed = {}
            if custom_mapping and "confirmed_mappings" in custom_mapping:
                for m in custom_mapping["confirmed_mappings"]:
                    sheet_key = f"{m.get('file_name', '')}!{m.get('sheet_name', '')}"
                    confirmed[sheet_key] = m.get("mappings", {})

            # Clear old data ONCE before streaming inserts start
            from app.services.smart_import_engine import (
                _clear_project_year_tables,
                rebuild_aux_balance_summary,
            )
            from app.models.audit_platform_models import (
                TbBalance, TbLedger, TbAuxBalance, TbAuxLedger,
            )
            from sqlalchemy import insert

            import_year = year or 2025
            async with async_session() as clear_db:
                await _clear_project_year_tables(project_id, import_year, clear_db)
                await clear_db.commit()

            # Bulk insert params: 14 columns × 1000 rows = 14000 params (< PG 65535 limit)
            INSERT_CHUNK_SIZE = 1000

            async def _insert_balance(rows: list[dict]) -> None:
                if not rows:
                    return
                async with async_session() as db:
                    for i in range(0, len(rows), INSERT_CHUNK_SIZE):
                        batch = rows[i:i + INSERT_CHUNK_SIZE]
                        stmt = insert(TbBalance).values([
                            {
                                "id": uuid4(),
                                "project_id": project_id,
                                "year": import_year,
                                "account_code": r["account_code"],
                                "account_name": r.get("account_name", ""),
                                "company_code": r.get("company_code") or "default",
                                "opening_balance": r.get("opening_balance"),
                                "opening_debit": r.get("opening_debit"),
                                "opening_credit": r.get("opening_credit"),
                                "debit_amount": r.get("debit_amount"),
                                "credit_amount": r.get("credit_amount"),
                                "closing_balance": r.get("closing_balance"),
                                "closing_debit": r.get("closing_debit"),
                                "closing_credit": r.get("closing_credit"),
                                "level": r.get("level", 1),
                                "currency_code": r.get("currency_code", "CNY"),
                                "raw_extra": r.get("raw_extra"),
                            }
                            for r in batch
                        ])
                        await db.execute(stmt)
                    await db.commit()

            async def _insert_aux_balance(rows: list[dict]) -> None:
                if not rows:
                    return
                async with async_session() as db:
                    for i in range(0, len(rows), INSERT_CHUNK_SIZE):
                        batch = rows[i:i + INSERT_CHUNK_SIZE]
                        stmt = insert(TbAuxBalance).values([
                            {
                                "id": uuid4(),
                                "project_id": project_id,
                                "year": import_year,
                                "account_code": r["account_code"],
                                "account_name": r.get("account_name", ""),
                                "company_code": r.get("company_code") or "default",
                                "aux_type": r.get("aux_type"),
                                "aux_code": r.get("aux_code"),
                                "aux_name": r.get("aux_name"),
                                "opening_balance": r.get("opening_balance"),
                                "opening_debit": r.get("opening_debit"),
                                "opening_credit": r.get("opening_credit"),
                                "debit_amount": r.get("debit_amount"),
                                "credit_amount": r.get("credit_amount"),
                                "closing_balance": r.get("closing_balance"),
                                "closing_debit": r.get("closing_debit"),
                                "closing_credit": r.get("closing_credit"),
                                "currency_code": r.get("currency_code", "CNY"),
                                "raw_extra": r.get("raw_extra"),
                            }
                            for r in batch
                        ])
                        await db.execute(stmt)
                    await db.commit()

            async def _insert_ledger(rows: list[dict]) -> None:
                if not rows:
                    return
                async with async_session() as db:
                    for i in range(0, len(rows), INSERT_CHUNK_SIZE):
                        batch = rows[i:i + INSERT_CHUNK_SIZE]
                        stmt = insert(TbLedger).values([
                            {
                                "id": uuid4(),
                                "project_id": project_id,
                                "year": import_year,
                                "account_code": r["account_code"],
                                "account_name": r.get("account_name", ""),
                                "company_code": r.get("company_code") or "default",
                                "voucher_date": r.get("voucher_date"),
                                "voucher_no": r.get("voucher_no", ""),
                                "voucher_type": r.get("voucher_type"),
                                "debit_amount": r.get("debit_amount"),
                                "credit_amount": r.get("credit_amount"),
                                "summary": r.get("summary"),
                                "preparer": r.get("preparer"),
                                "currency_code": r.get("currency_code", "CNY"),
                                "raw_extra": r.get("raw_extra"),
                            }
                            for r in batch
                        ])
                        await db.execute(stmt)
                    await db.commit()

            async def _insert_aux_ledger(rows: list[dict]) -> None:
                if not rows:
                    return
                async with async_session() as db:
                    for i in range(0, len(rows), INSERT_CHUNK_SIZE):
                        batch = rows[i:i + INSERT_CHUNK_SIZE]
                        stmt = insert(TbAuxLedger).values([
                            {
                                "id": uuid4(),
                                "project_id": project_id,
                                "year": import_year,
                                "account_code": r["account_code"],
                                "account_name": r.get("account_name", ""),
                                "company_code": r.get("company_code") or "default",
                                "voucher_date": r.get("voucher_date"),
                                "voucher_no": r.get("voucher_no", ""),
                                "voucher_type": r.get("voucher_type"),
                                "accounting_period": r.get("accounting_period"),
                                "aux_type": r.get("aux_type"),
                                "aux_code": r.get("aux_code") or "",
                                "aux_name": r.get("aux_name") or "",
                                "aux_dimensions_raw": r.get("aux_dimensions_raw"),
                                "debit_amount": r.get("debit_amount"),
                                "credit_amount": r.get("credit_amount"),
                                "summary": r.get("summary"),
                                "preparer": r.get("preparer"),
                                "currency_code": r.get("currency_code", "CNY"),
                                "raw_extra": r.get("raw_extra"),
                            }
                            for r in batch
                        ])
                        await db.execute(stmt)
                    await db.commit()

            all_findings = []
            total_rows_parsed = 0
            total_balance_written = 0
            total_aux_balance_written = 0
            total_ledger_written = 0
            total_aux_ledger_written = 0

            # Pre-compute total estimated rows across all sheets for accurate progress
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
                            "ImportJob %s skipping unknown sheet: %s!%s",
                            job_id, filename, sheet.sheet_name,
                        )
                        continue

                    # Build column mapping: confirmed → fallback auto-detection
                    sheet_key = f"{filename}!{sheet.sheet_name}"
                    col_mapping = confirmed.get(sheet_key) or {}
                    # P1-5 fallback: 如果 confirmed 缺失或为空，用自动检测
                    if not col_mapping:
                        for cm in sheet.column_mappings:
                            if cm.standard_field and cm.confidence >= 50:
                                col_mapping[cm.column_header] = cm.standard_field
                        logger.info(
                            "ImportJob %s %s!%s: using auto-detected mapping (%d cols)",
                            job_id, filename, sheet.sheet_name, len(col_mapping),
                        )

                    headers = sheet.detection_evidence.get("header_cells", [])
                    if not headers and sheet.preview_rows:
                        headers = [str(c) for c in sheet.preview_rows[0]] if sheet.preview_rows else []

                    logger.info(
                        "ImportJob %s processing sheet %s!%s: type=%s est_rows=%d cols=%d mapped=%d",
                        job_id, filename, sheet.sheet_name,
                        sheet.table_type, sheet.row_count_estimate,
                        len(headers), len(col_mapping),
                    )

                    # Stream parse rows
                    if ext in (".xlsx", ".xlsm"):
                        row_iter = iter_excel_rows_from_path(
                            str(filepath),
                            sheet.sheet_name,
                            data_start_row=sheet.data_start_row,
                        )
                    elif ext in (".csv", ".tsv"):
                        encoding = fd.encoding or "utf-8"
                        row_iter = iter_csv_rows_from_path(
                            str(filepath),
                            encoding=encoding,
                            data_start_row=sheet.data_start_row,
                        )
                    else:
                        continue

                    # Process chunks — streaming write per chunk
                    chunk_count = 0
                    for chunk in row_iter:
                        chunk_count += 1
                        # Convert raw list rows to dict rows using headers
                        dict_rows = []
                        for raw_row in chunk:
                            row_dict = {}
                            for i, val in enumerate(raw_row):
                                if i < len(headers):
                                    row_dict[headers[i]] = val
                                else:
                                    row_dict[f"col_{i}"] = val
                            dict_rows.append(row_dict)

                        # Apply column mapping → standard field rows + raw_extra
                        std_rows, extra_warnings = prepare_rows_with_raw_extra(
                            dict_rows, col_mapping, headers
                        )
                        all_findings.extend(extra_warnings)

                        # L1 validation
                        findings, cleaned = validate_l1(
                            std_rows, sheet.table_type, column_mapping=col_mapping,
                            file_name=filename, sheet_name=sheet.sheet_name,
                        )
                        all_findings.extend(findings)

                        # Convert + immediate write (streaming — no memory accumulation)
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

                        # Heartbeat + cancel check every chunk
                        pct = min(20 + int(65 * total_rows_parsed / total_est_rows), 85)
                        await cls._persist_progress(
                            job_id, pct,
                            f"已处理 {total_rows_parsed:,}/{total_est_rows:,} 行",
                        )

                        # Check for cancellation every 5 chunks (~250k rows)
                        if chunk_count % 5 == 0:
                            async with async_session() as check_db:
                                current = await ImportJobService.get_job(check_db, job_id)
                                if current and current.status == JobStatus.canceled:
                                    logger.info("ImportJob %s canceled by user", job_id)
                                    raise RuntimeError("导入已被用户取消")

            logger.info(
                "ImportJob %s streaming done: %d balance + %d aux_balance + %d ledger + %d aux_ledger rows written",
                job_id, total_balance_written, total_aux_balance_written,
                total_ledger_written, total_aux_ledger_written,
            )

            # ── Phase 4: Activation gate (basic — only blocking findings) ──
            await cls._persist_progress(job_id, 87, "评估激活条件")
            force = bool(options.get("force_activate"))
            gate = evaluate_activation(all_findings, force=force)

            if not gate.allowed:
                blocking_msgs = [f.message for f in gate.blocking_findings[:5]]
                # 注意：数据已写入，这里只是警告用户
                logger.warning(
                    "ImportJob %s has %d blocking findings but data already written",
                    job_id, len(gate.blocking_findings),
                )

            # ── Phase 5: Rebuild aux summary ──
            await cls._persist_progress(job_id, 92, "重建辅助汇总")
            async with async_session() as summary_db:
                await rebuild_aux_balance_summary(project_id, import_year, summary_db)
                await summary_db.commit()

            # ── Phase 6: Complete ──
            await cls._persist_progress(job_id, 98, "收尾")
            async with async_session() as db:
                await ImportJobService.transition(
                    db, job_id, JobStatus.completed,
                    progress_pct=100,
                    progress_message="v2 导入完成",
                    result_summary={
                        "engine": "v2",
                        "balance_rows": total_balance_written,
                        "aux_balance_rows": total_aux_balance_written,
                        "ledger_rows": total_ledger_written,
                        "aux_ledger_rows": total_aux_ledger_written,
                        "total_parsed": total_rows_parsed,
                        "warnings": len([f for f in all_findings if not f.blocking]),
                        "blocking_findings": len([f for f in all_findings if f.blocking]),
                        "year": import_year,
                    },
                )
                await db.commit()

            # Mark artifact consumed
            if upload_token:
                async with async_session() as artifact_db:
                    artifact = await ImportArtifactService.get_by_upload_token(
                        artifact_db, project_id=project_id, upload_token=upload_token,
                    )
                    if artifact:
                        await ImportArtifactService.mark_consumed(artifact_db, artifact.id)
                        await artifact_db.commit()

            ImportQueueService.release_lock(project_id)
            logger.info(
                "ImportJob %s v2 completed: %d+%d balance, %d+%d ledger rows",
                job_id, total_balance_written, total_aux_balance_written,
                total_ledger_written, total_aux_ledger_written,
            )

        except Exception as exc:
            logger.exception("ImportJob v2 执行失败: %s", job_id)
            # 多层兜底：即使 DB 操作失败也要尽量标记 job 为 failed + 释放锁
            error_msg = str(exc)[:1000] if exc else "未知错误"
            for attempt in range(3):
                try:
                    async with async_session() as db:
                        await ImportJobService.transition(
                            db, job_id, JobStatus.failed,
                            progress_pct=0,
                            error_message=error_msg,
                            result_summary={"engine": "v2", "error": str(exc)[:500]},
                        )
                        await db.commit()
                    break
                except Exception as db_exc:
                    logger.warning(
                        "ImportJob %s transition to failed attempt %d failed: %s",
                        job_id, attempt + 1, db_exc,
                    )
                    await asyncio.sleep(1)
            try:
                ImportQueueService.release_lock(project_id)
            except Exception:
                logger.exception("ImportQueueService.release_lock failed for %s", project_id)

    @staticmethod
    async def _persist_progress(job_id: UUID, pct: int, message: str) -> None:
        try:
            async with async_session() as db:
                await ImportJobService.set_progress(
                    db,
                    job_id,
                    progress_pct=pct,
                    progress_message=message,
                    current_phase="writing" if pct < 90 else "activating",
                )
                await db.commit()
        except Exception:
            logger.debug("ImportJob progress persist failed: %s", job_id, exc_info=True)
