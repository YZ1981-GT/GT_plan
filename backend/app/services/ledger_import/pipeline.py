"""v2 引擎纯数据管线（S7-6 从 orchestrator.py 拆出）。

职责（对齐 design.md §13）：
- detect → identify → create_staged → parse → convert → validate → write
  → activation_gate → activate_dataset → rebuild_aux_summary
- 不含 ImportJob 状态机、ImportQueueService 锁、ImportArtifactService 消费
  （这些由 Worker 层 `import_job_runner._execute_v2` 包装）

设计原则：
- 通过 `progress_cb` / `cancel_check` 回调抽象 Worker 细节
- 返回 `PipelineResult` 结构化数据，便于 Worker 转换成 result_summary
- 失败时抛 RuntimeError，Worker 外层 except 统一处理
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import UUID

logger = logging.getLogger(__name__)

__all__ = [
    "PipelineResult",
    "ProgressCallback",
    "CancelChecker",
    "execute_pipeline",
]


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
    from app.services.smart_import_engine import rebuild_aux_balance_summary

    from .converter import convert_balance_rows, convert_ledger_rows
    from .detector import detect_file_from_path
    from .identifier import identify
    from .parsers.csv_parser import iter_csv_rows_from_path
    from .parsers.excel_parser import iter_excel_rows_from_path
    from .validator import evaluate_activation, validate_l1
    from .writer import activate_dataset, bulk_insert_staged, prepare_rows_with_raw_extra

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

    # S7-2: bulk_insert_staged 按模型自省字段，注入公共列
    async def _insert(table_model, rows: list[dict]) -> None:
        await bulk_insert_staged(
            async_session, table_model, rows,
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
                    await _insert(TbBalance, bal)
                    await _insert(TbAuxBalance, aux_bal)
                    total_balance_written += len(bal)
                    total_aux_balance_written += len(aux_bal)
                elif sheet.table_type in ("ledger", "aux_ledger"):
                    ledger, aux_ledger, _stats = convert_ledger_rows(cleaned)
                    await _insert(TbLedger, ledger)
                    await _insert(TbAuxLedger, aux_ledger)
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

    # S7: force_activate 审批链——即使 force 跳过 blocking，也记录审计轨迹
    force_skipped_findings = 0
    if force_activate and gate.blocking_findings:
        force_skipped_findings = len(gate.blocking_findings)
        logger.warning(
            "Pipeline %s force_activate=True, skipping %d blocking findings",
            job_id, force_skipped_findings,
        )

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
                "force_skipped_findings": force_skipped_findings,
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
