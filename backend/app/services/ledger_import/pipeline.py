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
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID

logger = logging.getLogger(__name__)

__all__ = [
    "PipelineResult",
    "ProgressCallback",
    "CancelChecker",
    "PhaseMarker",
    "ProgressState",
    "execute_pipeline",
    "_handle_cancel",
    "_detect_memory_pressure",
]


# ---------------------------------------------------------------------------
# F51 / Sprint 8.31: 内存降级探测
# ---------------------------------------------------------------------------


_MEMORY_PRESSURE_THRESHOLD_PERCENT = 80.0


def _detect_memory_pressure(job_id: UUID | None = None) -> bool:
    """读 psutil.virtual_memory().percent，> 80% 返回 True 触发降级。

    psutil 是可选依赖（未写入 requirements.txt）。未安装或查询失败时
    返回 False（保持默认 calamine + 50k chunk），不影响主流程。

    Args:
        job_id: 仅用于日志 trace

    Returns:
        True：系统内存压力大，需降级到 openpyxl + 10k chunk
        False：内存充足或无法检测，走默认路径
    """
    try:
        import psutil  # noqa: WPS433
    except ImportError:
        return False
    try:
        percent = float(psutil.virtual_memory().percent)
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "Pipeline %s psutil.virtual_memory() failed: %s (skip downgrade)",
            job_id, exc,
        )
        return False
    if percent > _MEMORY_PRESSURE_THRESHOLD_PERCENT:
        logger.warning(
            "memory_pressure_downgrade: job=%s system memory %.1f%% > %.1f%% "
            "→ downgrading to openpyxl + smaller chunks",
            job_id, percent, _MEMORY_PRESSURE_THRESHOLD_PERCENT,
        )
        return True
    logger.debug(
        "Pipeline %s memory check: %.1f%% (below %.1f%% threshold, no downgrade)",
        job_id, percent, _MEMORY_PRESSURE_THRESHOLD_PERCENT,
    )
    return False


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
# F14 / Sprint 4.2: phase checkpoint 回调 — 每个关键 phase 完成后异步写入
# ImportJob.current_phase，用于崩溃后 resume_from_checkpoint 路由。
PhaseMarker = Callable[[str], Awaitable[None]]  # (phase) → None


# ---------------------------------------------------------------------------
# F13: 进度上报节流（Sprint 4.1）
# ---------------------------------------------------------------------------


@dataclass
class ProgressState:
    """进度上报状态 — 支持按百分比或行数阈值触发（F13）。

    _maybe_report_progress 按 5% 或 10k 行（先达到者）触发回调；
    大文档导入避免"每 chunk 都发进度"造成前端/数据库压力，也避免
    "长时间无更新"让前端误判卡死。
    """

    total_rows_est: int
    rows_processed: int = 0
    last_pct_reported: int = -1
    last_rows_reported: int = 0
    last_report_at: datetime | None = None


async def _maybe_report_progress(
    state: ProgressState,
    cb: "ProgressCallback | None",
    message_builder: Callable[[int], str],
) -> None:
    """按 5% 或 10k 行触发 progress_cb。

    - cb is None → 直接返回
    - total_rows_est <= 0 → 无法计算百分比，直接返回
    - 百分比 delta ≥ 5 OR 行数 delta ≥ 10_000 → 触发
    - 更新 state.last_* 三个字段记录上次上报信息
    """
    if cb is None or state.total_rows_est <= 0:
        return
    pct = min(int(state.rows_processed * 100 / state.total_rows_est), 100)
    rows_delta = state.rows_processed - state.last_rows_reported
    pct_delta = pct - state.last_pct_reported
    if pct_delta >= 5 or rows_delta >= 10_000:
        await cb(pct, message_builder(pct))
        state.last_pct_reported = pct
        state.last_rows_reported = state.rows_processed
        state.last_report_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# F15: cancel 清理链（Sprint 4.6）
# ---------------------------------------------------------------------------


async def _handle_cancel(
    *,
    dataset_id: UUID | None,
    job_id: UUID,
) -> None:
    """Cancel 时的完整清理链（F15）。

    步骤（best-effort，任一失败不阻断其他）：
    1. cleanup staged Tb* rows via DatasetService.cleanup_dataset_rows
    2. DatasetService.mark_failed（不再重复清理行，避免双删）
    3. 标记 job 关联的 ImportArtifact 为 consumed
       （防止后续重试读到旧 upload bundle）

    任何步骤异常都 logger.exception 记录、但不上抛 — 本函数语义是"尽力清理"。
    """
    # 延迟 import 避免循环依赖
    from app.core.database import async_session
    from app.services.dataset_service import DatasetService
    from app.services.import_artifact_service import ImportArtifactService
    from app.models.dataset_models import ImportArtifact, ImportJob
    import sqlalchemy as sa

    # Step 1 + 2: staged 行 + dataset 标 failed（都放同一事务，失败回滚）
    if dataset_id is not None:
        try:
            async with async_session() as db:
                await DatasetService.cleanup_dataset_rows(db, dataset_id)
                # cleanup_rows=False 因为上一步已经删了
                await DatasetService.mark_failed(db, dataset_id, cleanup_rows=False)
                await db.commit()
            logger.info(
                "Pipeline %s cancel cleanup: dataset %s cleaned + marked failed",
                job_id, dataset_id,
            )
        except Exception:
            logger.exception(
                "Pipeline %s cleanup_dataset_rows/mark_failed failed (dataset=%s)",
                job_id, dataset_id,
            )

    # Step 3: 标记 job 关联的 artifact 为 consumed（防止 retry 读旧 bundle）
    try:
        async with async_session() as db:
            # ImportJob.artifact_id → ImportArtifact
            result = await db.execute(
                sa.select(ImportJob.artifact_id).where(ImportJob.id == job_id)
            )
            row = result.scalar_one_or_none()
            if row is not None:
                await ImportArtifactService.mark_consumed(db, row)
                await db.commit()
                logger.info(
                    "Pipeline %s cancel cleanup: artifact %s marked consumed",
                    job_id, row,
                )
    except Exception:
        logger.exception(
            "Pipeline %s artifact mark_consumed failed (job=%s)", job_id, job_id,
        )


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
    phase_marker: PhaseMarker | None = None,
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
        phase_marker: F14 checkpoint 回调 async (phase) → None；每个关键 phase
            完成后调用，用于持久化 ``ImportJob.current_phase``。回调内部异常
            被 pipeline 吞掉（持久化失败不应阻断主流程）。

    Returns:
        PipelineResult

    Raises:
        RuntimeError: 用户取消 / blocking findings / 其他运行时错误
        ValueError: 文件空 / 参数错误
    """
    import os
    import time as _time
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
    from .parsers.excel_parser_calamine import iter_excel_rows_from_path_calamine
    from .validator import evaluate_activation, validate_l1
    from .writer import activate_dataset, bulk_write_staged, prepare_rows_with_raw_extra

    if not file_sources:
        raise ValueError("无可导入的文件")

    # B3 + 反思（2026-05-10）：按 "sheet 行数" 而非 "文件字节" 切 engine
    # - calamine 在 get_sheet_by_name 时就要全量解码 sheet XML（Rust 侧）
    # - YG2101 序时账 650k 行 calamine 解码 22s vs openpyxl read_only 30s+
    # - YG4001/YG36 几千~几万行 calamine 解码 <1s vs openpyxl 0.5-2s
    # 真实断点在 ~ 300-500k 行：此之下 calamine 快 3-5×，之上 calamine 不劣但内存高
    # 按"sheet 估算行数 < 500k 用 calamine，≥ 500k 用 openpyxl"比字节阈值更精确
    from app.services.feature_flags import is_enabled

    _CALAMINE_PARSE_MAX_ROWS = 500_000
    use_calamine_global = is_enabled("ledger_import_use_calamine", project_id)

    # F51 / Sprint 8.31: 内存降级
    # 启动时读 psutil.virtual_memory().percent > 80% → 强制走 openpyxl 流式
    # + 降低 chunk_size 到 10k（默认 50k），减少内存峰值。
    # psutil 是可选依赖，未装或查询失败时静默跳过（不阻断主流程）。
    memory_downgrade = _detect_memory_pressure(job_id)
    if memory_downgrade:
        use_calamine_global = False
        current_chunk_size = 10_000
        logger.warning(
            "memory_pressure_downgrade: job=%s forcing openpyxl + chunk_size=%d",
            job_id, current_chunk_size,
        )
    else:
        current_chunk_size = 50_000

    def _choose_excel_iter(sheet_row_estimate: int):
        """按 sheet 行数动态选 parser engine。"""
        if not use_calamine_global:
            return iter_excel_rows_from_path
        if sheet_row_estimate and sheet_row_estimate >= _CALAMINE_PARSE_MAX_ROWS:
            logger.info(
                "Pipeline %s sheet has %d rows ≥ %d, using openpyxl",
                job_id, sheet_row_estimate, _CALAMINE_PARSE_MAX_ROWS,
            )
            return iter_excel_rows_from_path
        return iter_excel_rows_from_path_calamine

    logger.info(
        "Pipeline %s xlsx engine strategy: %s (calamine flag=%s, row threshold=%d, "
        "chunk_size=%d, mem_downgrade=%s)",
        job_id,
        "per-sheet dynamic" if use_calamine_global else "openpyxl (flag off)",
        use_calamine_global, _CALAMINE_PARSE_MAX_ROWS,
        current_chunk_size, memory_downgrade,
    )

    async def _progress(pct: int, msg: str) -> None:
        if progress_cb is not None:
            await progress_cb(pct, msg)

    # F15: staging_dataset_id 先占位，cancel 清理链会用到
    staging_dataset_id: UUID | None = None

    async def _check_cancel() -> None:
        """检查 cancel 信号；若触发则先做 _handle_cancel 清理链（F15），再抛异常。"""
        if cancel_check is not None and await cancel_check():
            # F15（Sprint 4.6）：cancel 清理链 — dataset/artifact 清理幂等
            try:
                await _handle_cancel(dataset_id=staging_dataset_id, job_id=job_id)
            except Exception:
                logger.exception(
                    "Pipeline %s _handle_cancel raised (ignored; cleanup is best-effort)",
                    job_id,
                )
            raise RuntimeError("导入已被用户取消")

    # B3 深度诊断：打点记录各 phase 耗时
    _perf: dict[str, float] = {}
    _perf_t0 = _time.time()
    _last_phase: list[tuple[str, float]] = [("", _perf_t0)]  # mutable for closure

    def _mark(phase: str) -> None:
        """phase 开始前调用，记录"上一个 phase"的累计耗时 + F16 histogram。

        F14 / Sprint 4.2：phase 名同步 fire-and-forget 写入 ImportJob.current_phase，
        用于崩溃后 resume_from_checkpoint 路由。回调异常不阻断主流程。
        """
        now = _time.time()
        _perf[phase] = now
        logger.info("[perf] %s phase=%s cumulative=%.2fs", job_id, phase, now - _perf_t0)
        # F16 (Sprint 4.9)：上一个 phase 的耗时进 histogram
        prev_phase, prev_t = _last_phase[0]
        if prev_phase:
            try:
                from app.services.ledger_import.metrics import observe_phase_duration
                observe_phase_duration(prev_phase, now - prev_t)
            except Exception:  # metrics 问题不能阻断业务
                pass
        _last_phase[0] = (phase, now)
        # F14 / Sprint 4.2：checkpoint 持久化（fire-and-forget）
        if phase_marker is not None:
            try:
                import asyncio as _asyncio
                _asyncio.create_task(phase_marker(phase))
            except Exception:  # 回调调度失败不阻断业务
                logger.debug(
                    "Pipeline %s phase_marker schedule failed for phase=%s",
                    job_id, phase, exc_info=True,
                )

    _mark("start")

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
    _mark("detect_identify_done")

    # Resolve confirmed mappings
    confirmed = {}
    if custom_mapping and "confirmed_mappings" in custom_mapping:
        for m in custom_mapping["confirmed_mappings"]:
            sheet_key = f"{m.get('file_name', '')}!{m.get('sheet_name', '')}"
            confirmed[sheet_key] = m.get("mappings", {})

    import_year = year or 2025

    # ── Create staged dataset ──
    logger.info("Pipeline %s phase=create_staged", job_id)

    # 从 detection_evidence 提取金额单位（取第一个非 None 的）
    _amount_unit: str | None = None
    for _fd in detections.values():
        for _sheet in _fd.sheets:
            _au = (_sheet.detection_evidence or {}).get("amount_unit")
            if _au:
                _amount_unit = _au
                break
        if _amount_unit:
            break

    async with async_session() as stage_db:
        staged = await DatasetService.create_staged(
            stage_db,
            project_id=project_id,
            year=import_year,
            source_type="ledger_import_v2",
            job_id=job_id,
            created_by=created_by,
            source_summary={"amount_unit": _amount_unit} if _amount_unit else None,
        )
        staging_dataset_id = staged.id
        await stage_db.commit()
    logger.info("Pipeline %s created staged dataset %s", job_id, staging_dataset_id)
    _mark("create_staged_done")

    # S7-2 + B2: bulk_write_staged 智能派发（小批 INSERT / 大批 COPY，COPY 失败自动降级）
    async def _insert(table_model, rows: list[dict]) -> None:
        await bulk_write_staged(
            async_session, table_model, rows,
            project_id=project_id, year=import_year,
            dataset_id=staging_dataset_id, is_deleted=False,
        )

    # ── Parse → Convert → Validate → Write (streaming) ──
    logger.info("Pipeline %s phase=parse_write_streaming", job_id)
    await _progress(20, "解析并写入数据")

    # B3 诊断：累计每类操作耗时
    _t_parse = 0.0
    _t_dict = 0.0
    _t_prepare = 0.0
    _t_validate = 0.0
    _t_convert = 0.0
    _t_insert = 0.0
    _t_progress = 0.0
    _t_cancel_check = 0.0
    _n_inserts = 0
    _n_progress_calls = 0

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

    # F13（Sprint 4.1）：进度上报节流 — 按 5% 或 10k 行触发
    progress_state = ProgressState(total_rows_est=total_est_rows)

    def _build_progress_msg(pct: int) -> str:
        # 20~85 区间留给 parse_write_streaming 阶段；细节带实际行数
        real_pct = min(20 + int(65 * pct / 100), 85)
        return (
            f"已处理 {progress_state.rows_processed:,}/{progress_state.total_rows_est:,} 行"
        )

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
                _excel_iter = _choose_excel_iter(sheet.row_count_estimate)
                row_iter = _excel_iter(
                    str(filepath), sheet.sheet_name,
                    data_start_row=sheet.data_start_row,
                    chunk_size=current_chunk_size,
                    forward_fill_cols=ff_cols or None,
                )
            elif ext in (".csv", ".tsv"):
                encoding = fd.encoding or "utf-8"
                row_iter = iter_csv_rows_from_path(
                    str(filepath), encoding=encoding,
                    data_start_row=sheet.data_start_row,
                    chunk_size=current_chunk_size,
                )
            else:
                continue

            chunk_count = 0
            balance_cleaned_accumulated: list[dict] = []
            is_balance_sheet = sheet.table_type in ("balance", "aux_balance")

            # B3 诊断：把 for 循环展开成 while 以便测纯解析耗时
            _parse_iter = iter(row_iter)
            while True:
                _t = _time.time()
                try:
                    chunk = next(_parse_iter)
                except StopIteration:
                    _t_parse += _time.time() - _t
                    break
                _t_parse += _time.time() - _t

                chunk_count += 1
                _t = _time.time()
                dict_rows = []
                for raw_row in chunk:
                    row_dict = {}
                    for i, val in enumerate(raw_row):
                        if i < len(headers):
                            row_dict[headers[i]] = val
                        else:
                            row_dict[f"col_{i}"] = val
                    dict_rows.append(row_dict)
                _t_dict += _time.time() - _t

                _t = _time.time()
                std_rows, extra_warnings = prepare_rows_with_raw_extra(
                    dict_rows, col_mapping, headers
                )
                _t_prepare += _time.time() - _t
                all_findings.extend(extra_warnings)

                _t = _time.time()
                findings, cleaned = validate_l1(
                    std_rows, sheet.table_type, column_mapping=col_mapping,
                    file_name=filename, sheet_name=sheet.sheet_name,
                )
                _t_validate += _time.time() - _t
                all_findings.extend(findings)

                if is_balance_sheet:
                    balance_cleaned_accumulated.extend(cleaned)
                elif sheet.table_type in ("ledger", "aux_ledger"):
                    _t = _time.time()
                    ledger, aux_ledger, _stats = convert_ledger_rows(cleaned)
                    _t_convert += _time.time() - _t
                    _t = _time.time()
                    await _insert(TbLedger, ledger)
                    await _insert(TbAuxLedger, aux_ledger)
                    _t_insert += _time.time() - _t
                    _n_inserts += 2
                    total_ledger_written += len(ledger)
                    total_aux_ledger_written += len(aux_ledger)

                total_rows_parsed += len(chunk)
                progress_state.rows_processed = total_rows_parsed
                # F13: 按 5% / 10k 行节流 — 取代"每 chunk 硬推送"
                _t = _time.time()

                async def _emit_progress(pct: int, msg: str) -> None:
                    # 把 0-100% 映射到 parse_write_streaming 阶段的 20-85%
                    real_pct = min(20 + int(65 * pct / 100), 85)
                    await _progress(real_pct, msg)

                await _maybe_report_progress(
                    progress_state,
                    _emit_progress,
                    _build_progress_msg,
                )
                _t_progress += _time.time() - _t
                _n_progress_calls += 1

                if chunk_count % 5 == 0:
                    _t = _time.time()
                    await _check_cancel()
                    _t_cancel_check += _time.time() - _t

            # Balance sheet 累积完毕，统一 convert + 写入
            if is_balance_sheet and balance_cleaned_accumulated:
                _t = _time.time()
                bal, aux_bal = convert_balance_rows(balance_cleaned_accumulated)
                _t_convert += _time.time() - _t
                logger.info(
                    "Pipeline %s balance sheet %s: cleaned=%d dedup→balance=%d aux=%d",
                    job_id, sheet.sheet_name,
                    len(balance_cleaned_accumulated), len(bal), len(aux_bal),
                )
                _t = _time.time()
                await _insert(TbBalance, bal)
                await _insert(TbAuxBalance, aux_bal)
                _t_insert += _time.time() - _t
                _n_inserts += 2
                total_balance_written += len(bal)
                total_aux_balance_written += len(aux_bal)

    logger.info(
        "Pipeline %s streaming done: %d+%d balance, %d+%d ledger",
        job_id, total_balance_written, total_aux_balance_written,
        total_ledger_written, total_aux_ledger_written,
    )

    # B3 诊断：parse_write_streaming 内部各步累计耗时
    _mark("parse_write_streaming_done")
    logger.info(
        "[perf] %s parse_write_streaming breakdown: parse=%.1fs dict=%.1fs prepare=%.1fs "
        "validate=%.1fs convert=%.1fs insert=%.1fs progress=%.1fs (%d calls) "
        "cancel=%.1fs | inserts=%d",
        job_id, _t_parse, _t_dict, _t_prepare, _t_validate, _t_convert,
        _t_insert, _t_progress, _n_progress_calls, _t_cancel_check, _n_inserts,
    )

    # ── Activation gate ──
    logger.info("Pipeline %s phase=activation_gate", job_id)
    await _progress(85, "评估激活条件")
    gate = evaluate_activation(all_findings, force=force_activate)
    _mark("activation_gate_done")

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
    _mark("activate_dataset_done")

    # ── Rebuild aux summary ──
    logger.info("Pipeline %s phase=rebuild_aux_summary", job_id)
    await _progress(93, "重建辅助汇总")
    async with async_session() as summary_db:
        await rebuild_aux_balance_summary(
            project_id, import_year, summary_db,
            dataset_id=staging_dataset_id,
        )
        await summary_db.commit()
    _mark("rebuild_aux_summary_done")

    # B3 诊断：总耗时拆解日志
    phases = list(_perf.items())
    lines = []
    for idx, (name, t) in enumerate(phases):
        delta = t - phases[idx - 1][1] if idx > 0 else 0
        lines.append(f"{name} +{delta:.1f}s")
    logger.info("[perf] %s phases: %s | total=%.1fs",
                job_id, " → ".join(lines[1:]), _time.time() - _perf_t0)

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
