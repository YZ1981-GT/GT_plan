"""Ordered startup task registry, serial executor, and runtime report.

platform-architecture-convergence Tasks 10–12:
- ``STARTUP_TASKS`` order matches ``lifespan`` in ``app.main`` (pre-refactor).
- Serial executor: critical failures re-raise; best_effort records and continues.
- Process-local readonly report snapshot for ``/api/health``.
- Each worker has a stable name in the report (not a bare count).
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Sequence

Criticality = Literal["critical", "best_effort"]
TaskStatus = Literal["ok", "skipped", "failed"]

logger = logging.getLogger("audit_platform")

# Sensitive fragments redacted from report ``detail`` (Req 6.6).
_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(token|api[_-]?key|secret|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(postgres(?:ql)?|redis|mysql|mongodb)://[^\s\"']+"),
    re.compile(r"(?i)(DATABASE_URL|REDIS_URL|CONNECTION_STRING)\s*[:=]\s*\S+"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
)


def desensitize_detail(text: str | None) -> str | None:
    """Strip connection strings / passwords / tokens from a detail string."""
    if text is None:
        return None
    out = str(text)
    for pat in _SENSITIVE_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    # Truncate long traces; never ship full stacks with embedded credentials.
    if len(out) > 500:
        out = out[:500] + "…"
    return out


@dataclass
class StartupContext:
    """Mutable bag shared across serial startup tasks."""

    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    worker_tasks: list[asyncio.Task] = field(default_factory=list)
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "WARNING").upper())
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StartupTaskSpec:
    name: str
    phase: str
    criticality: Criticality
    run: Callable[[StartupContext], Awaitable[None] | None]
    timeout_seconds: float | None = None
    skip_condition: Callable[[StartupContext], str | None] | None = None


@dataclass(frozen=True)
class StartupTaskResult:
    name: str
    phase: str
    status: TaskStatus
    duration_ms: int
    detail: str | None


# ---------------------------------------------------------------------------
# Process-local readonly runtime report
# ---------------------------------------------------------------------------

_runtime_report: tuple[StartupTaskResult, ...] | None = None


def get_startup_report() -> tuple[StartupTaskResult, ...] | None:
    """Return the last completed startup report snapshot (or None if not run)."""
    return _runtime_report


def reset_startup_report() -> None:
    """Test helper: clear the process-local report."""
    global _runtime_report
    _runtime_report = None


def _set_runtime_report(results: Sequence[StartupTaskResult]) -> None:
    global _runtime_report
    _runtime_report = tuple(results)


def startup_report_as_dict(
    results: Sequence[StartupTaskResult] | None = None,
) -> dict[str, Any]:
    """Health-facing isomorphic projection; details are desensitized."""
    snapshot = results if results is not None else _runtime_report
    if snapshot is None:
        return {
            "status": "not_run",
            "tasks": [],
            "task_count": 0,
            "failed": [],
            "skipped": [],
        }
    tasks = [
        {
            "name": r.name,
            "phase": r.phase,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "detail": desensitize_detail(r.detail),
        }
        for r in snapshot
    ]
    return {
        "status": "complete",
        "tasks": tasks,
        "task_count": len(tasks),
        "failed": [t["name"] for t in tasks if t["status"] == "failed"],
        "skipped": [t["name"] for t in tasks if t["status"] == "skipped"],
    }


# ---------------------------------------------------------------------------
# Serial executor
# ---------------------------------------------------------------------------

async def run_startup_tasks(
    tasks: Sequence[StartupTaskSpec] | None = None,
    *,
    context: StartupContext | None = None,
) -> list[StartupTaskResult]:
    """Run startup tasks serially in registry order.

    - ``critical`` failures are recorded then re-raised.
    - ``best_effort`` failures are recorded; execution continues.
    - No DAG / parallelism / automatic retry.
    """
    specs = tuple(tasks) if tasks is not None else STARTUP_TASKS
    ctx = context if context is not None else StartupContext()
    results: list[StartupTaskResult] = []

    for spec in specs:
        skip_reason: str | None = None
        if spec.skip_condition is not None:
            try:
                skip_reason = spec.skip_condition(ctx)
            except Exception as exc:  # noqa: BLE001 — treat skip probe failure as continue
                skip_reason = None
                logger.warning(
                    "[startup] skip_condition error for %s: %s", spec.name, exc
                )

        if skip_reason:
            results.append(
                StartupTaskResult(
                    name=spec.name,
                    phase=spec.phase,
                    status="skipped",
                    duration_ms=0,
                    detail=desensitize_detail(skip_reason),
                )
            )
            continue

        started = time.perf_counter()
        status: TaskStatus = "ok"
        detail: str | None = None
        raised: BaseException | None = None
        try:
            outcome = spec.run(ctx)
            if inspect.isawaitable(outcome):
                if spec.timeout_seconds is not None:
                    await asyncio.wait_for(outcome, timeout=spec.timeout_seconds)
                else:
                    await outcome
        except Exception as exc:
            status = "failed"
            detail = desensitize_detail(f"{type(exc).__name__}: {exc}")
            raised = exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        results.append(
            StartupTaskResult(
                name=spec.name,
                phase=spec.phase,
                status=status,
                duration_ms=duration_ms,
                detail=detail,
            )
        )
        _set_runtime_report(results)

        if raised is not None:
            if spec.criticality == "critical":
                raise raised
            logger.warning(
                "[startup] best_effort task %s failed (non-blocking): %s",
                spec.name,
                detail,
            )

    _set_runtime_report(results)
    return results


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

def _skip_if_bootstrap_done(_ctx: StartupContext) -> str | None:
    if os.environ.get("GT_BOOTSTRAP_DONE") == "1":
        return "GT_BOOTSTRAP_DONE=1"
    return None


def _skip_if_import_runner_disabled(_ctx: StartupContext) -> str | None:
    from app.core.config import settings

    if not settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED:
        return "LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED=False"
    return None


# ---------------------------------------------------------------------------
# Task implementations (order-preserving extract from former main.lifespan)
# ---------------------------------------------------------------------------

def _task_setup_logging(ctx: StartupContext) -> None:
    from app.core.logging_config import setup_logging

    setup_logging(level=ctx.log_level, json_format=False)


async def _task_run_migrations(_ctx: StartupContext) -> None:
    """Database versioned migrations (best-effort; failures recorded in DB/health)."""
    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner

    log = logging.getLogger("audit_platform")
    try:
        runner = MigrationRunner(database_url=settings.DATABASE_URL)
        result = await runner.run_pending()
        if result.executed:
            log.info("[启动] 数据库迁移完成，执行了版本: %s", result.executed)
        if result.failed:
            for f in result.failed:
                log.error(
                    "[启动] 迁移 %s 失败 (%s): %s",
                    f.filename, f.error_type, f.error_message[:200],
                )
            log.error(
                "[启动] 共 %d 个迁移失败，已写入 schema_migration_failures 表 / health=degraded",
                len(result.failed),
            )
        await runner.close()
    except Exception as mig_err:
        log.warning(
            "[启动] 数据库迁移调度失败（应用仍继续启动）: %s", mig_err
        )


def _task_migration_mark_complete(_ctx: StartupContext) -> None:
    from app.core.runtime_state import migration_state

    migration_state.mark_complete()


async def _task_acnr_redis_inject(_ctx: StartupContext) -> None:
    from app.core.redis import get_redis
    from app.services.acnr.cache_epoch import set_redis_client

    acnr_redis = await get_redis()
    if acnr_redis is not None:
        set_redis_client(acnr_redis)


def _task_register_event_handlers(_ctx: StartupContext) -> None:
    from app.services.event_handlers import register_event_handlers

    register_event_handlers()


def _task_register_a13_event_handlers(_ctx: StartupContext) -> None:
    from app.services.a13_event_handler import register_a13_event_handlers

    register_a13_event_handlers()


def _task_register_phase_handlers(_ctx: StartupContext) -> None:
    from app.services.gate_rules_phase14 import register_phase14_rules
    from app.services.gate_rules_eqcr import register_eqcr_gate_rules
    from app.services.gate_rules_cross_check import register_cross_check_rules
    import app.services.gate_rules_round6  # noqa: F401
    import app.services.gate_rules_b60  # noqa: F401
    import app.services.gate_rules_ai_content  # noqa: F401
    import app.services.gate_rules_cross_module_conflict  # noqa: F401
    from app.services.task_event_handlers import (
        register_event_handlers as register_task_handlers,
    )

    register_phase14_rules()
    register_eqcr_gate_rules()
    register_cross_check_rules()
    register_task_handlers()

    try:
        from app.services.event_bus import event_bus
        from app.services.consol_note_stale_handler import register_stale_handler
        from app.services.consol_trial_stale_handler import (
            register_consol_trial_stale_handler,
        )
        from app.services.consol_elimination_recalc_handler import (
            register_consol_elimination_recalc_handler,
        )

        register_stale_handler(event_bus)
        register_consol_trial_stale_handler(event_bus)
        register_consol_elimination_recalc_handler(event_bus)
    except Exception as e:
        logging.getLogger("audit_platform").warning(
            "[启动] 合并 stale handler 注册失败: %s", e
        )


async def _task_replay_startup_events(_ctx: StartupContext) -> None:
    from app.core.config import settings
    from app.services.event_bus import event_bus

    try:
        replayed = await asyncio.wait_for(event_bus.replay_pending_events(), timeout=5.0)
        if replayed:
            logging.getLogger("audit_platform").info(
                "[启动] 恢复了 %s 个未处理事件", replayed
            )
    except Exception:
        pass

    try:
        from app.core.database import async_session
        from app.services.import_event_outbox_service import ImportEventOutboxService

        async with async_session() as db:
            max_attempts = int(settings.LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS or 0)
            replay_kwargs: dict[str, Any] = {"limit": 100}
            if max_attempts > 0:
                replay_kwargs["max_attempts"] = max_attempts
            outbox_report = await ImportEventOutboxService.replay_pending(db, **replay_kwargs)
            await db.commit()
        if outbox_report.get("published_count"):
            logging.getLogger("audit_platform").info(
                "[启动] 重放导入事件 outbox: %s", outbox_report
            )
    except Exception:
        pass


def _task_validate_grammar(_ctx: StartupContext) -> None:
    from app.services.acnr.grammar import validate_grammar_on_startup

    validate_grammar_on_startup()


async def _task_check_gin_index(_ctx: StartupContext) -> None:
    try:
        from app.core.database import async_session
        from app.services.gin_index_monitor import check_index_building_status

        async with async_session() as session:
            await check_index_building_status(session)
    except Exception as e:
        logging.getLogger("audit_platform").debug(
            "[启动] GIN index status check skipped (non-PG or unavailable): %s", e
        )


async def _task_check_libreoffice(_ctx: StartupContext) -> None:
    try:
        from app.services.libreoffice_pool import startup_health_check

        await startup_health_check()
    except Exception as e:
        logging.getLogger("audit_platform").debug(
            "[启动] LibreOffice health check skipped: %s", e
        )


def _task_validate_procedure_rollout(_ctx: StartupContext) -> None:
    from app.core.config import settings

    log = logging.getLogger("audit_platform.procedure_rollout")
    mode = settings.PROCEDURE_ROW_TASK_WRITE_MODE
    enabled = settings.PROCEDURE_ROW_TASKS_ENABLED
    dispatcher = settings.PROCEDURE_TASK_DISPATCHER_ENABLED

    valid_modes = {"legacy", "dual", "task_source", "paused"}
    if mode not in valid_modes:
        log.critical(
            "PROCEDURE_ROW_TASK_WRITE_MODE=%r 非法（合法值: %s），拒绝启动",
            mode, sorted(valid_modes),
        )
        sys.exit(1)

    if mode == "task_source" and not enabled:
        log.critical(
            "PROCEDURE_ROW_TASK_WRITE_MODE=task_source 但 PROCEDURE_ROW_TASKS_ENABLED=False "
            "（task overlay 不叠加 → 状态机写入无可见效果），拒绝启动",
        )
        sys.exit(1)

    if mode == "paused" and dispatcher:
        log.critical(
            "PROCEDURE_ROW_TASK_WRITE_MODE=paused 但 PROCEDURE_TASK_DISPATCHER_ENABLED=True "
            "（paused 态不应投递通知），拒绝启动",
        )
        sys.exit(1)

    log.info(
        "procedure rollout: mode=%s enabled=%s dispatcher=%s — OK",
        mode, enabled, dispatcher,
    )


async def _task_validate_template_manifest(_ctx: StartupContext) -> None:
    log = logging.getLogger("audit_platform")
    try:
        from app.services.template_manifest_loader import get_template_manifest_loader

        loader = get_template_manifest_loader()
        warnings = loader.validate()
        if warnings:
            log.warning(
                "[启动] 模板 manifest 校验 %d 项警告（version=%s）",
                len(warnings),
                loader.version() or "unknown",
            )
            for w in warnings[:8]:
                log.warning("  %s", w)
            if len(warnings) > 8:
                log.warning("  ... 还有 %d 项，详见 validate_template_manifest.py", len(warnings) - 8)
        else:
            log.info(
                "[启动] 模板 manifest 校验通过（version=%s）",
                loader.version() or "unknown",
            )
    except Exception as e:
        log.warning("[启动] 模板 manifest 校验失败（不阻塞启动）: %s", e)


async def _task_run_schema_drift_check(_ctx: StartupContext) -> None:
    from app.core.database import engine
    from app.core.schema_drift_detector import run_drift_check_with_timeout

    log = logging.getLogger("audit_platform")
    try:
        items = await run_drift_check_with_timeout(engine, timeout_seconds=60.0)
        if items:
            critical_count = sum(
                1 for it in items if it.drift_type in ("orm_extra", "enum_mismatch")
            )
            health_status = "degraded" if critical_count > 0 else "healthy"
            log.warning(
                "[启动] 检测到 %d 个 schema 漂移（critical=%d）/ health=%s",
                len(items), critical_count, health_status,
            )
            for it in items[:5]:
                log.warning(
                    "  [%s] %s%s: %s",
                    it.drift_type, it.table,
                    f".{it.column}" if it.column else "",
                    it.detail,
                )
            if len(items) > 5:
                log.warning("  ... 还有 %d 项详见 /api/health", len(items) - 5)
            if critical_count > 0:
                print(
                    f"[GT-Backend] WARNING: {len(items)} schema drifts detected "
                    f"(critical={critical_count})"
                )
    except Exception as e:
        log.warning("[启动] schema 漂移检测失败（不阻塞启动）: %s", e)


async def _task_warm_render_caches(_ctx: StartupContext) -> None:
    log = logging.getLogger("audit_platform")
    try:
        from app.routers import wp_render_strategies  # noqa: F401
        _ = wp_render_strategies.RENDERER_DISPATCH
        from app.services.procedure_table_auto_service import _load_templates

        _load_templates()
        log.info(
            "[启动] render 热路径预热完成（RENDERER_DISPATCH=%d）",
            len(wp_render_strategies.RENDERER_DISPATCH),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[启动] render 热路径预热失败（忽略，改由首请求惰性导入）: %s", e)


def _task_check_attachment_security_gates(_ctx: StartupContext) -> None:
    from app.services.evidence_governance.attachment_security_gates import (
        check_attachment_security_gates_startup,
    )

    check_attachment_security_gates_startup()


async def _task_start_epoch_subscriber(_ctx: StartupContext) -> None:
    from app.services.acnr.cache_epoch import start_epoch_subscriber

    await start_epoch_subscriber()


def _task_acnr_invalidation_outbox_start(_ctx: StartupContext) -> None:
    from app.services.acnr.invalidation_outbox import get_dispatcher

    get_dispatcher().start()


async def _task_recover_ai_chat_runs(_ctx: StartupContext) -> None:
    from app.core.config import settings

    log = logging.getLogger("audit_platform")
    if not settings.AI_CHAT_STARTUP_RECOVERY_ENABLED:
        log.info("[ai-chat] 启动恢复已按配置关闭")
        return
    try:
        from app.core.database import async_session
        from app.services.ai_chat.run_coordinator import get_coordinator

        coordinator = get_coordinator()
        async with async_session() as db:
            report = await coordinator.recover_lease_expired_runs(db)
        if report.requeued:
            await coordinator.redispatch(report.requeued)
        if report.scanned:
            log.warning("[ai-chat] run 启动恢复：%s", report.as_dict())
    except Exception:
        log.error("[ai-chat] run 启动恢复失败（可能有 run 卡在 running）", exc_info=True)


async def _task_run_ai_chat_health_check(_ctx: StartupContext) -> None:
    log = logging.getLogger("audit_platform")
    try:
        from app.services.ai_chat.startup_health import run_ai_chat_startup_health_check

        report = await run_ai_chat_startup_health_check()
        if report.has_violations:
            log.warning("[ai-chat] %s", report.summary())
        else:
            log.info("[ai-chat] %s", report.summary())
    except Exception as exc:
        log.error("[ai-chat] 启动健康检查异常（不阻塞）: %s", exc)


async def _task_acnr_catalog_snapshot_gc(_ctx: StartupContext) -> None:
    """Best-effort GC — exceptions propagate to executor for report status=failed."""
    from app.services.acnr.catalog_snapshot_gc import run_db_aware_gc

    gc_report = await run_db_aware_gc(keep_recent=10)
    logging.getLogger("audit_platform").info(
        "ACNR snapshot GC: total=%s deleted=%s status=%s",
        gc_report.get("total_snapshots"),
        len(gc_report.get("deleted", [])),
        gc_report.get("reference_status"),
    )


def _task_install_sigterm(_ctx: StartupContext) -> None:
    from app.core.graceful_shutdown import install_sigterm_handler

    install_sigterm_handler()


def _task_print_ready(ctx: StartupContext) -> None:
    print(
        f"[GT-Backend] Ready on port {os.getenv('PORT', '9980')} "
        f"(log_level={ctx.log_level})"
    )


# ---------------------------------------------------------------------------
# Workers — each has a stable name in the registry / report
# ---------------------------------------------------------------------------

def _make_worker_starter(
    worker_import: str,
    attr: str = "run",
) -> Callable[[StartupContext], None]:
    def _start(ctx: StartupContext) -> None:
        import importlib

        mod = importlib.import_module(worker_import)
        run_fn = getattr(mod, attr)
        task = asyncio.create_task(run_fn(ctx.stop_event))
        ctx.worker_tasks.append(task)

    return _start


def _start_import_job_runner(ctx: StartupContext) -> None:
    from app.services.import_job_runner import ImportJobRunner

    task = asyncio.create_task(ImportJobRunner.run_forever(stop_event=ctx.stop_event))
    ctx.worker_tasks.append(task)


# Stable worker names (11 always-on + 1 conditional ImportJobRunner).
WORKER_TASK_NAMES: tuple[str, ...] = (
    "sla_worker",
    "import_recover_worker",
    "outbox_replay_worker",
    "audit_log_writer_worker",
    "budget_alert_worker",
    "dataset_purge_worker",
    "staged_orphan_cleaner",
    "export_cleanup_worker",
    "time_machine_cleanup_worker",
    "procedure_dispatcher_worker",
    "invalidation_dispatcher_worker",
    "ImportJobRunner.run_forever",
)


def start_all_workers(stop_event: asyncio.Event) -> list[asyncio.Task]:
    """Batch-start all workers (compat for ``app.main._start_workers`` tests).

    Same set/order as registry worker tasks; ImportJobRunner is conditional.
    """
    from app.core.config import settings
    from app.workers import (
        sla_worker,
        import_recover_worker,
        outbox_replay_worker,
        audit_log_writer_worker,
        budget_alert_worker,
        dataset_purge_worker,
        staged_orphan_cleaner,
        export_cleanup_worker,
        time_machine_cleanup_worker,
        procedure_dispatcher_worker,
        invalidation_dispatcher_worker,
    )

    tasks = [
        asyncio.create_task(sla_worker.run(stop_event)),
        asyncio.create_task(import_recover_worker.run(stop_event)),
        asyncio.create_task(outbox_replay_worker.run(stop_event)),
        asyncio.create_task(audit_log_writer_worker.run(stop_event)),
        asyncio.create_task(budget_alert_worker.run(stop_event)),
        asyncio.create_task(dataset_purge_worker.run(stop_event)),
        asyncio.create_task(staged_orphan_cleaner.run(stop_event)),
        asyncio.create_task(export_cleanup_worker.run(stop_event)),
        asyncio.create_task(time_machine_cleanup_worker.run(stop_event)),
        asyncio.create_task(procedure_dispatcher_worker.run(stop_event)),
        asyncio.create_task(invalidation_dispatcher_worker.run(stop_event)),
    ]
    if settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED:
        from app.services.import_job_runner import ImportJobRunner

        tasks.append(asyncio.create_task(ImportJobRunner.run_forever(stop_event=stop_event)))
    return tasks


def _worker_specs() -> tuple[StartupTaskSpec, ...]:
    bindings: list[tuple[str, str]] = [
        ("sla_worker", "app.workers.sla_worker"),
        ("import_recover_worker", "app.workers.import_recover_worker"),
        ("outbox_replay_worker", "app.workers.outbox_replay_worker"),
        ("audit_log_writer_worker", "app.workers.audit_log_writer_worker"),
        ("budget_alert_worker", "app.workers.budget_alert_worker"),
        ("dataset_purge_worker", "app.workers.dataset_purge_worker"),
        ("staged_orphan_cleaner", "app.workers.staged_orphan_cleaner"),
        ("export_cleanup_worker", "app.workers.export_cleanup_worker"),
        ("time_machine_cleanup_worker", "app.workers.time_machine_cleanup_worker"),
        ("procedure_dispatcher_worker", "app.workers.procedure_dispatcher_worker"),
        ("invalidation_dispatcher_worker", "app.workers.invalidation_dispatcher_worker"),
    ]
    specs: list[StartupTaskSpec] = [
        StartupTaskSpec(
            name=name,
            phase="workers",
            criticality="critical",
            run=_make_worker_starter(mod),
        )
        for name, mod in bindings
    ]
    specs.append(
        StartupTaskSpec(
            name="ImportJobRunner.run_forever",
            phase="workers",
            criticality="critical",
            run=_start_import_job_runner,
            skip_condition=_skip_if_import_runner_disabled,
        )
    )
    return tuple(specs)


# ---------------------------------------------------------------------------
# Ordered registry — MUST match former main.lifespan line order
# ---------------------------------------------------------------------------

STARTUP_TASKS: tuple[StartupTaskSpec, ...] = (
    StartupTaskSpec(
        name="setup_logging",
        phase="bootstrap",
        criticality="critical",
        run=_task_setup_logging,
    ),
    StartupTaskSpec(
        name="run_migrations",
        phase="migration",
        criticality="best_effort",
        run=_task_run_migrations,
        skip_condition=_skip_if_bootstrap_done,
    ),
    StartupTaskSpec(
        name="migration_mark_complete",
        phase="migration",
        criticality="critical",
        run=_task_migration_mark_complete,
    ),
    StartupTaskSpec(
        name="acnr_redis_inject",
        phase="infrastructure",
        criticality="critical",
        run=_task_acnr_redis_inject,
    ),
    StartupTaskSpec(
        name="register_event_handlers",
        phase="handlers",
        criticality="critical",
        run=_task_register_event_handlers,
    ),
    StartupTaskSpec(
        name="register_a13_event_handlers",
        phase="handlers",
        criticality="critical",
        run=_task_register_a13_event_handlers,
    ),
    StartupTaskSpec(
        name="register_phase_handlers",
        phase="handlers",
        criticality="critical",
        run=_task_register_phase_handlers,
    ),
    StartupTaskSpec(
        name="replay_startup_events",
        phase="handlers",
        criticality="best_effort",
        run=_task_replay_startup_events,
    ),
    StartupTaskSpec(
        name="validate_grammar_on_startup",
        phase="validation",
        criticality="critical",
        run=_task_validate_grammar,
    ),
    StartupTaskSpec(
        name="check_gin_index_status",
        phase="validation",
        criticality="best_effort",
        run=_task_check_gin_index,
    ),
    StartupTaskSpec(
        name="check_libreoffice_health",
        phase="validation",
        criticality="best_effort",
        run=_task_check_libreoffice,
    ),
    StartupTaskSpec(
        name="validate_procedure_rollout_config",
        phase="validation",
        criticality="critical",
        run=_task_validate_procedure_rollout,
    ),
    StartupTaskSpec(
        name="validate_template_manifest",
        phase="validation",
        criticality="best_effort",
        run=_task_validate_template_manifest,
    ),
    StartupTaskSpec(
        name="run_schema_drift_check",
        phase="validation",
        criticality="best_effort",
        run=_task_run_schema_drift_check,
    ),
    StartupTaskSpec(
        name="warm_render_caches",
        phase="caches",
        criticality="best_effort",
        run=_task_warm_render_caches,
    ),
    StartupTaskSpec(
        name="check_attachment_security_gates",
        phase="validation",
        criticality="critical",
        run=_task_check_attachment_security_gates,
    ),
    StartupTaskSpec(
        name="start_epoch_subscriber",
        phase="acnr",
        criticality="critical",
        run=_task_start_epoch_subscriber,
    ),
    StartupTaskSpec(
        name="acnr_invalidation_outbox_start",
        phase="acnr",
        criticality="critical",
        run=_task_acnr_invalidation_outbox_start,
    ),
    StartupTaskSpec(
        name="recover_ai_chat_runs",
        phase="ai",
        criticality="best_effort",
        run=_task_recover_ai_chat_runs,
    ),
    StartupTaskSpec(
        name="run_ai_chat_health_check",
        phase="ai",
        criticality="best_effort",
        run=_task_run_ai_chat_health_check,
    ),
    StartupTaskSpec(
        name="acnr_catalog_snapshot_gc",
        phase="acnr",
        criticality="best_effort",
        run=_task_acnr_catalog_snapshot_gc,
    ),
    *_worker_specs(),
    StartupTaskSpec(
        name="install_sigterm_handler",
        phase="finalize",
        criticality="critical",
        run=_task_install_sigterm,
    ),
    StartupTaskSpec(
        name="print_ready",
        phase="finalize",
        criticality="critical",
        run=_task_print_ready,
    ),
)

# Frozen sequence for mutation / sequence-lock tests (Task 10).
FROZEN_STARTUP_SEQUENCE_NAMES: tuple[str, ...] = tuple(t.name for t in STARTUP_TASKS)

FROZEN_CRITICAL_SEQUENCE_NAMES: tuple[str, ...] = tuple(
    t.name for t in STARTUP_TASKS if t.criticality == "critical"
)


def assert_sequence_matches_frozen(
    tasks: Sequence[StartupTaskSpec] | None = None,
) -> None:
    """Raise AssertionError if task name order drifts from the frozen lock."""
    names = tuple(t.name for t in (tasks if tasks is not None else STARTUP_TASKS))
    if names != FROZEN_STARTUP_SEQUENCE_NAMES:
        raise AssertionError(
            f"startup sequence drift:\n  got={names}\n  frozen={FROZEN_STARTUP_SEQUENCE_NAMES}"
        )


def assert_criticality_matches_frozen(
    tasks: Sequence[StartupTaskSpec] | None = None,
) -> None:
    """Raise if any task's criticality differs from the frozen registry."""
    specs = tasks if tasks is not None else STARTUP_TASKS
    frozen_crit = {t.name: t.criticality for t in STARTUP_TASKS}
    for spec in specs:
        expected = frozen_crit.get(spec.name)
        if expected is None:
            raise AssertionError(f"unknown startup task in mutation: {spec.name}")
        if spec.criticality != expected:
            raise AssertionError(
                f"criticality drift for {spec.name}: "
                f"got={spec.criticality} frozen={expected}"
            )
