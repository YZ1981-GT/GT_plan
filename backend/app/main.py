"""审计作业平台 — FastAPI 应用入口"""

import os
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.tracing import setup_tracing
from app.core.logging_config import setup_logging
from app.middleware.audit_log import AuditLogMiddleware
from app.middleware.error_handler import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.middleware.response import ResponseWrapperMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.rate_limiter import LLMRateLimitMiddleware
from app.middleware.body_limit import RequestBodyLimitMiddleware
from app.middleware.observability import ObservabilityMiddleware
from app.services.event_handlers import register_event_handlers
from app.router_registry import register_all_routers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时运行迁移 + 注册事件处理器 + 启动后台 Worker"""
    import asyncio
    import os
    # 默认 WARNING 级别，启动日志精简；通过 LOG_LEVEL 环境变量调高
    log_level = os.getenv("LOG_LEVEL", "WARNING").upper()
    setup_logging(level=log_level, json_format=False)

    await _run_migrations()
    register_event_handlers()
    _register_phase_handlers()
    await _replay_startup_events()
    await _check_gin_index_status()
    await _check_libreoffice_health()
    await _run_schema_drift_check()

    stop_event = asyncio.Event()
    tasks = _start_workers(stop_event)

    # 启动完成提示（即使在 WARNING 级别也会显示）
    print(f"[GT-Backend] Ready on port {os.getenv('PORT', '9980')} (log_level={log_level})")

    yield

    # F44 / Sprint 10.52: 优雅关闭 — 通知 worker stop_event + 取消 + 等待。
    # 等价于 asyncio.wait_for(runner.wait_idle(), timeout=30)：
    # stop_event.set() 让 run_forever 退出循环，task.cancel() 确保超时兜底，
    # await task 等待清理完成。满足 F44 graceful shutdown 需求。
    stop_event.set()
    for t in tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    from app.core.database import dispose_engine
    await dispose_engine()


async def _run_schema_drift_check() -> None:
    """启动 self-check：ORM ↔ DB schema 漂移检测。

    migration-runner-resilience spec / Sprint 2 / Task 2.3。
    - 60s timeout（防止漏接表卡住启动）
    - 失败不阻塞启动（异常吞掉 + WARN）
    - drift>0 → 启动末尾 print() 兜底（绕过 LOG_LEVEL 过滤）
    """
    import logging as _drift_log
    from app.core.database import engine
    from app.core.schema_drift_detector import run_drift_check_with_timeout

    log = _drift_log.getLogger("audit_platform")
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
            # 启动末尾用 print 兜底（仅 critical>0 时告警）
            if critical_count > 0:
                print(
                    f"[GT-Backend] WARNING: {len(items)} schema drifts detected "
                    f"(critical={critical_count})"
                )
    except Exception as e:
        log.warning("[启动] schema 漂移检测失败（不阻塞启动）: %s", e)


async def _run_migrations() -> None:
    """数据库版本化迁移（D6：版本化 SQL 脚本）。

    Resilient 模式（migration-runner-resilience spec）：
    - 单文件失败不阻塞后续迁移（_apply_migration 内 per-migration 异常隔离）
    - 失败迁移写入 schema_migration_failures 表 + 启动日志 ERROR 级别
    - lifespan 不抛出，应用仍继续启动（health endpoint 暴露 degraded）
    """
    import logging as _mig_log
    from app.core.migration_runner import MigrationRunner
    log = _mig_log.getLogger("audit_platform")
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
    except Exception as _mig_err:
        log.warning(
            "[启动] 数据库迁移调度失败（应用仍继续启动）: %s", _mig_err
        )


def _register_phase_handlers() -> None:
    """Phase 14/15 事件处理器与门禁规则注册。"""
    from app.services.gate_rules_phase14 import register_phase14_rules
    from app.services.gate_rules_eqcr import register_eqcr_gate_rules
    from app.services.gate_rules_cross_check import register_cross_check_rules
    import app.services.gate_rules_round6  # noqa: F401 — 模块级自动注册
    import app.services.gate_rules_ai_content  # noqa: F401 — R3 AI 内容确认规则自动注册
    import app.services.gate_rules_cross_module_conflict  # noqa: F401 — V3 7.6 跨模块冲突守门规则自动注册
    from app.services.task_event_handlers import (
        register_event_handlers as register_task_handlers,
    )
    register_phase14_rules()
    register_eqcr_gate_rules()
    register_cross_check_rules()
    register_task_handlers()

    # 合并模块 stale 传播 handler（子公司变更 → 母合并项目标 stale）
    import logging as _log
    try:
        from app.services.event_bus import event_bus
        from app.services.consol_note_stale_handler import register_stale_handler
        from app.services.consol_trial_stale_handler import (
            register_consol_trial_stale_handler,
        )
        from app.services.consol_elimination_recalc_handler import (
            register_consol_elimination_recalc_handler,
        )
        register_stale_handler(event_bus)              # NOTE_UPDATED → 合并附注 stale
        register_consol_trial_stale_handler(event_bus)  # TRIAL_BALANCE_UPDATED → 合并 trial stale（P1）
        register_consol_elimination_recalc_handler(event_bus)  # ELIMINATION_APPROVED → worksheet + trial 重算（衔接2）
    except Exception as e:
        _log.getLogger("audit_platform").warning(
            "[启动] 合并 stale handler 注册失败: %s", e
        )


async def _check_gin_index_status() -> None:
    """Startup check: detect if parsed_data GIN index is building → set global flag."""
    import logging as _log
    try:
        from app.core.database import async_session
        from app.services.gin_index_monitor import check_index_building_status
        async with async_session() as session:
            await check_index_building_status(session)
    except Exception as e:
        _log.getLogger("audit_platform").debug(
            "[启动] GIN index status check skipped (non-PG or unavailable): %s", e
        )


async def _check_libreoffice_health() -> None:
    """Startup check: probe LibreOffice paths + run soffice --version (Req 8.3).

    失败时记录 logger.error 但不阻塞应用启动（三级数据源前两级仍可用）。
    """
    import logging as _log
    try:
        from app.services.libreoffice_pool import startup_health_check
        await startup_health_check()
    except Exception as e:
        _log.getLogger("audit_platform").debug(
            "[启动] LibreOffice health check skipped: %s", e
        )


async def _replay_startup_events() -> None:
    """启动时补偿：Redis Stream 未处理事件 + DB outbox 未发布事件。"""
    import logging as _log
    import asyncio as _aio
    from app.services.event_bus import event_bus

    # Redis Stream 补偿
    try:
        replayed = await _aio.wait_for(event_bus.replay_pending_events(), timeout=5.0)
        if replayed:
            _log.getLogger("audit_platform").info(
                f"[启动] 恢复了 {replayed} 个未处理事件"
            )
    except Exception:
        pass  # Redis 不可用或超时时静默跳过

    # DB outbox 补偿（已提交但未成功发布的导入激活/回滚事件）
    try:
        from app.core.database import async_session
        from app.services.import_event_outbox_service import ImportEventOutboxService
        async with async_session() as db:
            max_attempts = int(settings.LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS or 0)
            replay_kwargs = {"limit": 100}
            if max_attempts > 0:
                replay_kwargs["max_attempts"] = max_attempts
            outbox_report = await ImportEventOutboxService.replay_pending(db, **replay_kwargs)
            await db.commit()
        if outbox_report.get("published_count"):
            _log.getLogger("audit_platform").info(
                "[启动] 重放导入事件 outbox: %s", outbox_report
            )
    except Exception:
        pass


def _start_workers(stop_event):
    """启动所有后台 Worker，返回 task 列表。"""
    import asyncio
    from app.workers import (
        sla_worker, import_recover_worker, outbox_replay_worker,
        audit_log_writer_worker, budget_alert_worker, dataset_purge_worker,
        staged_orphan_cleaner, export_cleanup_worker,
        time_machine_cleanup_worker,
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
    ]
    # 进程内 ImportJob runner 主循环：写 import_worker 心跳 + 拉 queued 任务
    # 仅当 LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED=True 启动（生产模式下应关闭，
    # 改用 standalone `python -m app.workers.import_worker` 进程）
    if settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED:
        from app.services.import_job_runner import ImportJobRunner
        tasks.append(asyncio.create_task(ImportJobRunner.run_forever(stop_event=stop_event)))
    return tasks


app = FastAPI(
    title="审计作业平台",
    description="面向会计师事务所的审计全流程作业系统",
    version="1.0.0",
    lifespan=lifespan,
)

setup_tracing(app)


@app.get("/api/version")
async def api_version():
    return {"version": "1.0.0", "api_prefix": "/api"}


@app.get("/metrics", tags=["observability"])
async def metrics_endpoint():
    """Prometheus /metrics 端点（F16 / Sprint 4.10）。

    prometheus_client 未安装时返回占位文本；安装后返回完整指标。
    暴露 ledger_import_{duration_seconds,jobs_total} + ledger_dataset_count
    + event_outbox_dlq_depth + ledger_import_health_status 共 5 项。
    """
    from app.services.ledger_import.metrics import render_metrics

    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


# --- 异常处理器 ---
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# --- 中间件（LIFO：最后添加的最先执行=洋葱最外层） ---
# 洋葱模型从外到内：BodyLimit → GZip → Observability → ResponseWrapper → RequestID → RateLimit → AuditLog
# 添加顺序从内到外（先添加=最内层）：
app.add_middleware(AuditLogMiddleware)          # 最内层，记录路由真实响应状态码
app.add_middleware(LLMRateLimitMiddleware)      # LLM 限流
app.add_middleware(RequestIDMiddleware)         # 注入 request_id
app.add_middleware(ResponseWrapperMiddleware)   # 统一响应格式
app.add_middleware(ObservabilityMiddleware)     # 请求指标采集 + 慢请求告警
app.add_middleware(GZipMiddleware, minimum_size=1000)  # 压缩响应
app.add_middleware(RequestBodyLimitMiddleware)  # 最外层，最先拦截超大请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 路由注册（按业务域分组，详见 router_registry/ 包） ---
register_all_routers(app)
