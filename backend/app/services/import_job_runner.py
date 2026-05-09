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
        """Execute import using v2 ledger_import engine (S6-3 薄包装).

        Worker 编排职责保留在这里：
        - 加载 artifact → file_sources
        - ImportJobService 状态机切换（validating/writing/completed/failed）
        - ImportQueueService 锁管理
        - ArtifactService 消费标记
        - staged dataset 失败兜底清理

        核心数据管线（detect/parse/convert/validate/write/activate）由
        `ledger_import.orchestrator.execute_pipeline` 执行（S6-3 架构清洁）。
        """
        # Bootstrap import（任何错误都兜底）
        try:
            from app.services.ledger_import.orchestrator import (
                PipelineResult, execute_pipeline,
            )
        except Exception as imp_exc:
            logger.exception("ImportJob %s: v2 module import failed", job_id)
            async with async_session() as db:
                await ImportJobService.transition(
                    db, job_id, JobStatus.failed,
                    progress_pct=0,
                    error_message=f"v2 模块导入失败: {str(imp_exc)[:500]}",
                    result_summary={
                        "engine": "v2", "phase": "bootstrap_import",
                        "error": str(imp_exc)[:500],
                    },
                )
                await db.commit()
            ImportQueueService.release_lock(project_id)
            return

        logger.info("ImportJob %s: v2 engine starting (project=%s year=%s)",
                    job_id, project_id, year)

        try:
            # ── Phase 1: Load files ──
            logger.info("ImportJob %s phase=load_files", job_id)
            await cls._persist_progress(job_id, 5, "加载上传文件")
            file_sources = await cls._load_file_sources(
                project_id=project_id, upload_token=upload_token
            )
            if not file_sources:
                raise ValueError("无可导入的文件")
            logger.info("ImportJob %s loaded %d file(s)", job_id, len(file_sources))

            # ── Phase 2: Transition to validating ──
            async with async_session() as db:
                await ImportJobService.transition(
                    db, job_id, JobStatus.validating,
                    progress_pct=10, progress_message="识别文件结构",
                )
                await db.commit()

            # ── Phase 3: Transition to writing ──
            async with async_session() as db:
                await ImportJobService.transition(
                    db, job_id, JobStatus.writing,
                    progress_pct=20, progress_message="解析并写入数据",
                )
                await db.commit()

            # ── Define callbacks for pipeline ──
            async def _progress_cb(pct: int, msg: str) -> None:
                await cls._persist_progress(job_id, pct, msg)

            async def _cancel_check() -> bool:
                async with async_session() as check_db:
                    current = await ImportJobService.get_job(check_db, job_id)
                    return current is not None and current.status == JobStatus.canceled

            # ── Phase 4: Run pipeline ──
            force = bool(options.get("force_activate"))
            result: PipelineResult = await execute_pipeline(
                job_id=job_id,
                project_id=project_id,
                year=year,
                custom_mapping=custom_mapping,
                created_by=created_by,
                file_sources=file_sources,
                force_activate=force,
                progress_cb=_progress_cb,
                cancel_check=_cancel_check,
            )

            # ── Phase 5: Complete ──
            logger.info("ImportJob %s phase=complete", job_id)
            await cls._persist_progress(job_id, 98, "收尾")
            async with async_session() as db:
                await ImportJobService.transition(
                    db, job_id, JobStatus.completed,
                    progress_pct=100,
                    progress_message="v2 导入完成",
                    result_summary={
                        "engine": "v2",
                        "dataset_id": str(result.dataset_id) if result.dataset_id else None,
                        "balance_rows": result.balance_rows,
                        "aux_balance_rows": result.aux_balance_rows,
                        "ledger_rows": result.ledger_rows,
                        "aux_ledger_rows": result.aux_ledger_rows,
                        "total_parsed": result.total_rows_parsed,
                        "warnings": result.warnings,
                        "blocking_findings": result.blocking_findings,
                        "year": result.year,
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
                job_id, result.balance_rows, result.aux_balance_rows,
                result.ledger_rows, result.aux_ledger_rows,
            )

        except Exception as exc:
            logger.exception("ImportJob v2 执行失败: %s", job_id)
            # 多层兜底：即使 DB 操作失败也要尽量标记 job 为 failed + 释放锁
            error_msg = str(exc)[:1000] if exc else "未知错误"

            # S6-13: 清理 staged dataset（防止孤儿数据）
            try:
                from app.services.dataset_service import DatasetService as _DS
                async with async_session() as cleanup_db:
                    cleaned = await _DS.mark_failed_for_job(cleanup_db, job_id)
                    await cleanup_db.commit()
                    if cleaned > 0:
                        logger.info(
                            "ImportJob %s cleaned up %d staged dataset(s)",
                            job_id, cleaned,
                        )
            except Exception:
                logger.exception(
                    "ImportJob %s staged cleanup failed", job_id,
                )

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
