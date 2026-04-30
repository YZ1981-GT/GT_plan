from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dataset_models import JobStatus
from app.services.import_job_service import ImportJobService
from app.services.import_queue_service import ImportQueueService
from app.services.ledger_import_upload_service import LedgerImportUploadService
from app.services.smart_import_engine import SmartImportError, smart_import_streaming, smart_parse_files

logger = logging.getLogger(__name__)


class LedgerImportApplicationService:
    SMART_SUGGESTION_RULE_VERSION = "import-rules-2026.04"

    @staticmethod
    def collect_uploads(
        files: list[UploadFile] | None = None,
        file: UploadFile | None = None,
    ) -> list[UploadFile]:
        uploads = list(files or [])
        if file is not None:
            uploads.append(file)
        return [upload for upload in uploads if upload is not None]

    @staticmethod
    def ensure_supported_uploads(files: list[UploadFile]) -> None:
        for upload in files:
            filename = (upload.filename or "").lower()
            if filename.endswith(".xls"):
                raise HTTPException(
                    status_code=400,
                    detail="暂不支持 Excel 97-2003 (.xls) 文件，请先转换为 .xlsx 后再上传",
                )

    @classmethod
    async def resolve_file_sources(
        cls,
        *,
        project_id: UUID,
        user_id: str,
        files: list[UploadFile] | None = None,
        file: UploadFile | None = None,
        upload_token: str | None = None,
    ) -> tuple[str, list[tuple[str, object]]]:
        uploads = cls.collect_uploads(files=files, file=file)
        if upload_token:
            from app.core.database import async_session
            from app.services.import_artifact_service import ImportArtifactService

            async with async_session() as db:
                artifact = await ImportArtifactService.get_by_upload_token(
                    db,
                    project_id=project_id,
                    upload_token=upload_token,
                )
                if artifact and artifact.storage_uri:
                    bundle_dir = ImportArtifactService.materialize_bundle(
                        artifact.storage_uri,
                        upload_token=upload_token,
                    )
                    if bundle_dir is not None:
                        return upload_token, LedgerImportUploadService.get_bundle_files_from_path(bundle_dir)
            return upload_token, LedgerImportUploadService.get_bundle_files(project_id, upload_token)

        if not uploads:
            raise HTTPException(status_code=400, detail="未提供文件")

        cls.ensure_supported_uploads(uploads)
        manifest = await LedgerImportUploadService.create_bundle(project_id, user_id, uploads)
        resolved_token = manifest["upload_token"]
        return resolved_token, LedgerImportUploadService.get_bundle_files(project_id, resolved_token)

    @staticmethod
    def parse_custom_mapping(custom_mapping: str | dict[str, Any] | None) -> dict[str, Any] | None:
        if custom_mapping is None or custom_mapping == "":
            return None
        if isinstance(custom_mapping, dict):
            return custom_mapping
        try:
            parsed = json.loads(custom_mapping)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="自定义列映射JSON格式错误") from exc
        if parsed is None:
            return None
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="自定义列映射必须为JSON对象")
        return parsed

    @staticmethod
    def build_file_label(file_sources: list[tuple[str, object]]) -> str:
        file_label = file_sources[0][0] if file_sources else "upload.xlsx"
        if len(file_sources) > 1:
            file_label = f"{file_label} 等{len(file_sources)}个文件"
        return file_label

    @staticmethod
    def _count_total_records(result: dict[str, Any]) -> int:
        total_accounts = int(result.get("total_accounts") or 0)
        data_sheets_imported = result.get("data_sheets_imported") or {}
        total_data_rows = sum(int(v) for v in data_sheets_imported.values() if isinstance(v, int))
        return total_accounts + total_data_rows

    @staticmethod
    def _normalize_sheet_diagnostics(diagnostics: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for sheet in diagnostics or []:
            column_mapping = sheet.get("column_mapping") or {}
            matched_cols = sheet.get("matched_cols")
            if not isinstance(matched_cols, list):
                matched_cols = sorted(set(column_mapping.values())) if isinstance(column_mapping, dict) else []
            normalized.append({
                "sheet_name": sheet.get("sheet_name") or sheet.get("sheet", ""),
                "guessed_type": sheet.get("guessed_type") or sheet.get("data_type", "unknown"),
                "matched_cols": matched_cols,
                "missing_cols": sheet.get("missing_cols") or [],
                "missing_recommended": sheet.get("missing_recommended") or [],
                "row_count": sheet.get("row_count", 0),
            })
        return normalized

    @staticmethod
    def _stringify_preview_rows(rows: list[dict[str, Any]] | None) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for row in rows or []:
            normalized_row: dict[str, str] = {}
            for key, value in row.items():
                if value is None:
                    normalized_row[str(key)] = ""
                elif hasattr(value, "isoformat"):
                    normalized_row[str(key)] = value.isoformat()
                else:
                    normalized_row[str(key)] = str(value).strip()
            normalized.append(normalized_row)
        return normalized

    @classmethod
    def _build_preview_sheets(cls, diagnostics: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        sheets: list[dict[str, Any]] = []
        for diag in diagnostics or []:
            headers = diag.get("headers")
            preview_rows = diag.get("preview_rows_data")
            if not isinstance(headers, list) or not isinstance(preview_rows, list):
                continue
            sheets.append({
                "sheet_name": diag.get("sheet") or "CSV",
                "headers": headers,
                "rows": cls._stringify_preview_rows(preview_rows),
                "total_rows": diag.get("total_row_estimate") or diag.get("row_count", 0),
                "column_mapping": diag.get("column_mapping") or {},
                "file_type_guess": diag.get("data_type") or "unknown",
                "header_count": diag.get("header_count", 1),
                "header_start": diag.get("header_start", 0),
                "_source_file": diag.get("file"),
                "company_code": diag.get("company_code"),
                "year": diag.get("year"),
            })
        return sheets

    @staticmethod
    def _build_preview_summary(diagnostics: list[dict[str, Any]] | None) -> dict[str, int]:
        balance_est = 0
        aux_balance_est = 0
        ledger_est = 0
        aux_ledger_est = 0
        for diag in diagnostics or []:
            est = diag.get("total_row_estimate") or diag.get("row_count", 0)
            data_type = diag.get("data_type", "")
            if data_type in ("balance", "aux_balance"):
                balance_est += est
                aux_balance_est += int(diag.get("aux_balance_count_est") or 0)
            elif data_type in ("ledger", "aux_ledger"):
                ledger_est += est
                aux_ledger_est += int(diag.get("aux_ledger_count_est") or 0)
        return {
            "balance": balance_est,
            "aux_balance": aux_balance_est,
            "ledger": ledger_est,
            "aux_ledger": aux_ledger_est,
        }

    @classmethod
    def _build_validation_report(cls, diagnostics: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        report: list[dict[str, Any]] = []
        for diag in diagnostics or []:
            sample_rows = cls._stringify_preview_rows((diag.get("preview_rows_data") or [])[:3])
            file_name = diag.get("file")
            sheet_name = diag.get("sheet")
            missing_cols = diag.get("missing_cols") or []
            missing_recommended = diag.get("missing_recommended") or []
            status = diag.get("status")
            message = diag.get("message")
            data_type = diag.get("data_type")

            if status == "error":
                report.append({
                    "file": file_name,
                    "sheet": sheet_name,
                    "rule_code": "parse_error",
                    "severity": "fatal",
                    "message": message or "文件解析失败",
                    "details": {"data_type": data_type},
                    "sample_rows": sample_rows,
                    "blocking": True,
                })
                continue

            if missing_cols:
                report.append({
                    "file": file_name,
                    "sheet": sheet_name,
                    "rule_code": "missing_required_columns",
                    "severity": "error",
                    "message": f"缺少必需列: {', '.join(missing_cols)}",
                    "details": {"data_type": data_type, "missing_columns": missing_cols},
                    "sample_rows": sample_rows,
                    "blocking": True,
                })

            if missing_recommended:
                report.append({
                    "file": file_name,
                    "sheet": sheet_name,
                    "rule_code": "missing_recommended_columns",
                    "severity": "warning",
                    "message": f"缺少推荐列: {', '.join(missing_recommended)}",
                    "details": {"data_type": data_type, "missing_columns": missing_recommended},
                    "sample_rows": sample_rows,
                    "blocking": False,
                })

            if status == "skipped":
                report.append({
                    "file": file_name,
                    "sheet": sheet_name,
                    "rule_code": "sheet_skipped",
                    "severity": "warning",
                    "message": message or "该工作表已跳过",
                    "details": {"data_type": data_type},
                    "sample_rows": sample_rows,
                    "blocking": False,
                })
        return report

    @staticmethod
    def _build_validation_summary(validation: list[dict[str, Any]] | None) -> dict[str, Any]:
        by_severity = {
            "fatal": 0,
            "error": 0,
            "warning": 0,
            "info": 0,
        }
        blocking_count = 0
        for item in validation or []:
            severity = str(item.get("severity") or "info").lower()
            if severity not in by_severity:
                by_severity[severity] = 0
            by_severity[severity] += 1
            if item.get("blocking"):
                blocking_count += 1
        return {
            "total": len(validation or []),
            "blocking_count": blocking_count,
            "has_blocking": blocking_count > 0,
            "by_severity": by_severity,
        }

    @staticmethod
    def _auto_apply_threshold() -> float:
        threshold = float(settings.LEDGER_IMPORT_AUTO_APPLY_CONFIDENCE_THRESHOLD)
        return min(max(threshold, 0.0), 1.0)

    @classmethod
    def _build_suggestion_contract(cls, diagnostics: list[dict[str, Any]] | None) -> dict[str, Any]:
        suggested_mapping: dict[str, str] = {}
        confidence_by_field: dict[str, float] = {}
        reasons: dict[str, str] = {}
        needs_confirmation: list[str] = []
        auto_apply_threshold = cls._auto_apply_threshold()

        for diag in diagnostics or []:
            if diag.get("status") == "error":
                continue
            data_type = str(diag.get("data_type") or "unknown")
            column_mapping = diag.get("column_mapping") or {}
            if not isinstance(column_mapping, dict):
                continue

            header_mapped = diag.get("header_mapped")
            if not isinstance(header_mapped, (set, list, tuple)):
                header_mapped = []
            header_mapped_set = {str(item) for item in header_mapped}
            content_inferred = diag.get("content_inferred") or {}
            if not isinstance(content_inferred, dict):
                content_inferred = {}

            for source_column, standard_field in column_mapping.items():
                if not standard_field:
                    continue
                field_key = f"{data_type}.{standard_field}"
                source_column_str = str(source_column)

                if source_column_str in content_inferred:
                    confidence = 0.76
                    reason = "value_pattern"
                elif not header_mapped_set or source_column_str in header_mapped_set:
                    confidence = 0.92
                    reason = "header_similarity"
                else:
                    confidence = 0.88
                    reason = "manual_or_saved_mapping"

                previous_confidence = confidence_by_field.get(field_key, -1.0)
                if confidence < previous_confidence:
                    continue

                suggested_mapping[field_key] = source_column_str
                confidence_by_field[field_key] = round(confidence, 2)
                reasons[field_key] = reason

        for field_key, confidence in confidence_by_field.items():
            if confidence < auto_apply_threshold:
                needs_confirmation.append(field_key)

        return {
            "suggested_mapping": suggested_mapping,
            "confidence_by_field": confidence_by_field,
            "reasons": reasons,
            "rule_version": cls.SMART_SUGGESTION_RULE_VERSION,
            "auto_apply_threshold": auto_apply_threshold,
            "needs_confirmation": sorted(needs_confirmation),
        }

    @classmethod
    async def preview(
        cls,
        *,
        project_id: UUID,
        user_id: str,
        files: list[UploadFile] | None = None,
        file: UploadFile | None = None,
        upload_token: str | None = None,
        year: int | None = None,
        preview_rows: int = 50,
        custom_mapping: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_token, file_sources = await cls.resolve_file_sources(
            project_id=project_id,
            user_id=user_id,
            files=files,
            file=file,
            upload_token=upload_token,
        )
        result = smart_parse_files(
            file_sources,
            year_override=year,
            custom_mapping=custom_mapping,
            preview_mode=True,
            preview_rows=preview_rows,
        )
        diagnostics = result.get("diagnostics") or []
        validation = cls._build_validation_report(diagnostics)
        suggestion_contract = cls._build_suggestion_contract(diagnostics)
        return {
            "year": result.get("year"),
            "summary": cls._build_preview_summary(diagnostics),
            "aux_dimensions": result.get("aux_dimensions", []),
            "validation": validation,
            "validation_summary": cls._build_validation_summary(validation),
            **suggestion_contract,
            "diagnostics": diagnostics,
            "preview_mode": True,
            "preview_rows": preview_rows,
            "upload_token": resolved_token,
            "sheets": cls._build_preview_sheets(diagnostics),
            "active_sheet": 0,
        }

    @classmethod
    def build_account_chart_result_payload(cls, result: dict[str, Any]) -> dict[str, Any]:
        sheet_diagnostics = result.get("sheet_diagnostics")
        normalized_diagnostics = cls._normalize_sheet_diagnostics(sheet_diagnostics)
        validation = cls._build_validation_report(sheet_diagnostics)
        suggestion_contract = cls._build_suggestion_contract(sheet_diagnostics)
        return {
            "total_imported": int(result.get("total_accounts") or 0),
            "by_category": result.get("by_category") or {},
            "errors": result.get("errors") or [],
            "data_sheets_imported": result.get("data_sheets_imported") or {},
            "sheet_diagnostics": normalized_diagnostics,
            "diagnostics": normalized_diagnostics,
            "validation": validation,
            "validation_summary": cls._build_validation_summary(validation),
            **suggestion_contract,
            "year": result.get("year"),
        }

    @classmethod
    def build_account_chart_failure_payload(
        cls,
        error_message: str,
        *,
        diagnostics: list[dict[str, Any]] | None = None,
        errors: list[str] | None = None,
        year: int | None = None,
    ) -> dict[str, Any]:
        normalized_diagnostics = cls._normalize_sheet_diagnostics(diagnostics)
        validation = cls._build_validation_report(diagnostics)
        suggestion_contract = cls._build_suggestion_contract(diagnostics)
        if not validation:
            validation = [{
                "file": None,
                "sheet": None,
                "rule_code": "import_failed",
                "severity": "fatal",
                "message": f"导入失败: {error_message}",
                "details": {},
                "sample_rows": [],
                "blocking": True,
            }]
        return {
            "total_imported": 0,
            "by_category": {},
            "errors": errors or [f"导入失败: {error_message}"],
            "data_sheets_imported": {},
            "sheet_diagnostics": normalized_diagnostics,
            "diagnostics": normalized_diagnostics,
            "validation": validation,
            "validation_summary": cls._build_validation_summary(validation),
            **suggestion_contract,
            "year": year,
        }

    @classmethod
    def build_ledger_job_result_payload(
        cls,
        result: dict[str, Any],
        *,
        job_batch_id: UUID | None,
    ) -> dict[str, Any]:
        diagnostics = result.get("sheet_diagnostics")
        normalized_diagnostics = cls._normalize_sheet_diagnostics(diagnostics)
        validation = cls._build_validation_report(diagnostics)
        suggestion_contract = cls._build_suggestion_contract(diagnostics)
        return {
            "imported": result.get("data_sheets_imported") or {},
            "year": result.get("year"),
            "diagnostics": normalized_diagnostics,
            "sheet_diagnostics": normalized_diagnostics,
            "validation": validation,
            "validation_summary": cls._build_validation_summary(validation),
            **suggestion_contract,
            "errors": result.get("errors") or [],
            "batch_id": str(job_batch_id) if job_batch_id is not None else None,
        }

    @classmethod
    def build_ledger_failure_payload(
        cls,
        error_message: str,
        *,
        job_batch_id: UUID | None,
        diagnostics: list[dict[str, Any]] | None = None,
        errors: list[str] | None = None,
        year: int | None = None,
    ) -> dict[str, Any]:
        normalized_diagnostics = cls._normalize_sheet_diagnostics(diagnostics)
        validation = cls._build_validation_report(diagnostics)
        suggestion_contract = cls._build_suggestion_contract(diagnostics)
        if not validation:
            validation = [{
                "file": None,
                "sheet": None,
                "rule_code": "import_failed",
                "severity": "fatal",
                "message": f"导入失败: {error_message}",
                "details": {},
                "sample_rows": [],
                "blocking": True,
            }]
        return {
            "imported": {},
            "year": year,
            "diagnostics": normalized_diagnostics,
            "sheet_diagnostics": normalized_diagnostics,
            "validation": validation,
            "validation_summary": cls._build_validation_summary(validation),
            "errors": errors or [f"导入失败: {error_message}"],
            **suggestion_contract,
            "batch_id": str(job_batch_id) if job_batch_id is not None else None,
        }

    @classmethod
    async def run_account_chart_import(
        cls,
        *,
        project_id: UUID,
        user_id: str,
        db: AsyncSession,
        files: list[UploadFile] | None = None,
        file: UploadFile | None = None,
        upload_token: str | None = None,
        year: int | None = None,
        column_mapping: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parsed_mapping = cls.parse_custom_mapping(column_mapping)
        resolved_token, file_sources = await cls.resolve_file_sources(
            project_id=project_id,
            user_id=user_id,
            files=files,
            file=file,
            upload_token=upload_token,
        )
        file_label = cls.build_file_label(file_sources)
        ok, msg, job_batch_id = await ImportQueueService.acquire_lock(
            project_id,
            user_id,
            db,
            source_type="smart_import",
            file_name=file_label,
            year=year or 0,
        )
        if not ok:
            raise HTTPException(status_code=409, detail=msg)

        # Phase 17: 同步导入也创建 ImportJob 记录（确保所有导入可追溯）
        sync_job_id = None
        try:
            sync_job = await ImportJobService.create_job(
                db,
                project_id=project_id,
                year=year or 0,
                custom_mapping=parsed_mapping,
                created_by=UUID(user_id) if user_id else None,
            )
            sync_job_id = sync_job.id
            await ImportJobService.transition(db, sync_job_id, JobStatus.queued, progress_pct=0, progress_message="同步导入已排队")
            await ImportJobService.transition(db, sync_job_id, JobStatus.running, progress_pct=1, progress_message="同步导入开始")
            await db.flush()
        except Exception as e:
            logger.debug("创建同步 ImportJob 失败（降级）: %s", e)

        try:
            ImportQueueService.update_progress(
                project_id,
                2,
                f"开始导入 {len(file_sources)} 个文件…",
            )

            def _on_progress(pct: int, message: str):
                ImportQueueService.update_progress(project_id, min(pct, 99), message)

            result = await smart_import_streaming(
                project_id=project_id,
                file_contents=file_sources,
                db=db,
                year_override=year,
                custom_mapping=parsed_mapping,
                progress_callback=_on_progress,
            )
            result_payload = cls.build_account_chart_result_payload(result)

            # 标记 ImportJob 完成
            if sync_job_id:
                try:
                    await ImportJobService.transition(db, sync_job_id, JobStatus.completed, progress_pct=100, progress_message="导入完成", result_summary=result_payload.get("data_sheets_imported"))
                except Exception:
                    pass

            if job_batch_id is not None:
                await ImportQueueService.complete_job(
                    project_id,
                    job_batch_id,
                    db,
                    message=f"导入完成: {result.get('data_sheets_imported')}",
                    result=result_payload,
                    year=result.get("year"),
                    record_count=cls._count_total_records(result),
                )
            return result_payload
        except Exception as exc:
            # 标记 ImportJob 失败
            if sync_job_id:
                try:
                    await ImportJobService.transition(db, sync_job_id, JobStatus.failed, error_message=str(exc)[:500])
                except Exception:
                    pass

            diagnostics = exc.diagnostics if isinstance(exc, SmartImportError) else None
            failure_errors = exc.errors if isinstance(exc, SmartImportError) else None
            failure_year = exc.year if isinstance(exc, SmartImportError) else year
            failure_payload = cls.build_account_chart_failure_payload(
                str(exc),
                diagnostics=diagnostics,
                errors=failure_errors,
                year=failure_year,
            )
            if job_batch_id is not None:
                await ImportQueueService.fail_job(
                    project_id,
                    job_batch_id,
                    db,
                    message=f"导入失败: {exc}",
                    result=failure_payload,
                    year=year,
                )
            else:
                ImportQueueService.release_lock(project_id)
            raise

    @classmethod
    async def submit_import_job(
        cls,
        *,
        project_id: UUID,
        user_id: str,
        db: AsyncSession,
        files: list[UploadFile] | None = None,
        file: UploadFile | None = None,
        upload_token: str | None = None,
        year: int | None = None,
        custom_mapping: str | dict[str, Any] | None = None,
        payload_style: str = "ledger",
    ) -> dict[str, Any]:
        parsed_mapping = cls.parse_custom_mapping(custom_mapping)
        resolved_token, file_sources = await cls.resolve_file_sources(
            project_id=project_id,
            user_id=user_id,
            files=files,
            file=file,
            upload_token=upload_token,
        )
        file_label = cls.build_file_label(file_sources)
        ok, msg, job_batch_id = await ImportQueueService.acquire_lock(
            project_id,
            user_id,
            db,
            source_type="smart_import",
            file_name=file_label,
            year=year or 0,
        )
        if not ok:
            raise HTTPException(status_code=409, detail=msg)

        from app.services.import_artifact_service import ImportArtifactService

        artifact = await ImportArtifactService.get_by_upload_token(
            db,
            project_id=project_id,
            upload_token=resolved_token,
        )
        created_by = UUID(user_id) if user_id else None
        import_job = await ImportJobService.create_job(
            db,
            project_id=project_id,
            year=year or 0,
            artifact_id=artifact.id if artifact else None,
            custom_mapping=parsed_mapping,
            options={
                "payload_style": payload_style,
                "queue_batch_id": str(job_batch_id) if job_batch_id is not None else None,
                "upload_token": resolved_token,
                "force_activate": False,
            },
            created_by=created_by,
        )
        await ImportJobService.transition(
            db,
            import_job.id,
            JobStatus.queued,
            progress_pct=0,
            progress_message="导入作业已排队",
        )
        await db.commit()

        ImportQueueService.update_progress(project_id, 1, "导入作业已排队")
        if settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED:
            from app.services.import_job_runner import ImportJobRunner
            ImportJobRunner.enqueue(import_job.id)
        return {
            "status": "accepted",
            "message": f"导入任务已提交（{len(file_sources)} 个文件），请轮询进度",
            "project_id": str(project_id),
            "batch_id": str(job_batch_id) if job_batch_id is not None else None,
            "job_id": str(import_job.id),
            "upload_token": resolved_token,
        }
