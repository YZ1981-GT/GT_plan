from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.services.import_queue_service import ImportQueueService
from app.services.ledger_import_upload_service import LedgerImportUploadService
from app.services.smart_import_engine import smart_import_streaming, smart_parse_files

logger = logging.getLogger(__name__)


class LedgerImportApplicationService:
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
        return {
            "year": result.get("year"),
            "summary": cls._build_preview_summary(diagnostics),
            "aux_dimensions": result.get("aux_dimensions", []),
            "validation": cls._build_validation_report(diagnostics),
            "diagnostics": diagnostics,
            "preview_mode": True,
            "preview_rows": preview_rows,
            "upload_token": resolved_token,
            "sheets": cls._build_preview_sheets(diagnostics),
            "active_sheet": 0,
        }

    @classmethod
    def build_account_chart_result_payload(cls, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "total_imported": int(result.get("total_accounts") or 0),
            "by_category": result.get("by_category") or {},
            "errors": result.get("errors") or [],
            "data_sheets_imported": result.get("data_sheets_imported") or {},
            "sheet_diagnostics": cls._normalize_sheet_diagnostics(result.get("sheet_diagnostics")),
            "year": result.get("year"),
        }

    @staticmethod
    def build_account_chart_failure_payload(error_message: str) -> dict[str, Any]:
        return {
            "total_imported": 0,
            "by_category": {},
            "errors": [f"导入失败: {error_message}"],
            "data_sheets_imported": {},
            "sheet_diagnostics": [],
            "year": None,
        }

    @classmethod
    def build_ledger_job_result_payload(
        cls,
        result: dict[str, Any],
        *,
        job_batch_id: UUID | None,
    ) -> dict[str, Any]:
        return {
            "imported": result.get("data_sheets_imported") or {},
            "year": result.get("year"),
            "diagnostics": cls._normalize_sheet_diagnostics(result.get("sheet_diagnostics")),
            "errors": result.get("errors") or [],
            "batch_id": str(job_batch_id) if job_batch_id is not None else None,
        }

    @staticmethod
    def build_ledger_failure_payload(error_message: str, *, job_batch_id: UUID | None) -> dict[str, Any]:
        return {
            "imported": {},
            "year": None,
            "diagnostics": [],
            "errors": [f"导入失败: {error_message}"],
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
            failure_payload = cls.build_account_chart_failure_payload(str(exc))
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

        async def _do_import() -> None:
            try:
                ImportQueueService.update_progress(
                    project_id,
                    2,
                    f"开始导入 {len(file_sources)} 个文件…",
                )

                def _on_progress(pct: int, message: str):
                    ImportQueueService.update_progress(project_id, pct, message)

                async with async_session() as import_db:
                    result = await smart_import_streaming(
                        project_id=project_id,
                        file_contents=file_sources,
                        db=import_db,
                        year_override=year,
                        custom_mapping=parsed_mapping,
                        progress_callback=_on_progress,
                    )

                if payload_style == "account_chart":
                    result_payload = cls.build_account_chart_result_payload(result)
                else:
                    result_payload = cls.build_ledger_job_result_payload(result, job_batch_id=job_batch_id)

                if job_batch_id is not None:
                    async with async_session() as status_db:
                        await ImportQueueService.complete_job(
                            project_id,
                            job_batch_id,
                            status_db,
                            message=f"导入完成: {result.get('data_sheets_imported')}",
                            result=result_payload,
                            year=result.get("year"),
                            record_count=cls._count_total_records(result),
                        )
                else:
                    ImportQueueService.release_lock(project_id)
            except Exception as exc:
                import traceback

                logger.error("异步导入失败: %s\n%s", exc, traceback.format_exc())
                if payload_style == "account_chart":
                    failure_payload = cls.build_account_chart_failure_payload(str(exc))
                else:
                    failure_payload = cls.build_ledger_failure_payload(str(exc), job_batch_id=job_batch_id)

                async with async_session() as status_db:
                    if job_batch_id is not None:
                        await ImportQueueService.fail_job(
                            project_id,
                            job_batch_id,
                            status_db,
                            message=f"导入失败: {exc}",
                            result=failure_payload,
                            year=year,
                        )
                    else:
                        ImportQueueService.release_lock(project_id)

        asyncio.create_task(_do_import())
        return {
            "status": "accepted",
            "message": f"导入任务已提交（{len(file_sources)} 个文件），请轮询进度",
            "project_id": str(project_id),
            "batch_id": str(job_batch_id) if job_batch_id is not None else None,
            "upload_token": resolved_token,
        }
