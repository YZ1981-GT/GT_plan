"""审计作业平台 — FastAPI 应用入口"""

import os
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.core.config import settings
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
    """应用生命周期：启动时注册事件处理器 + Phase 15 SLA 定时检查"""
    setup_logging(level="INFO", json_format=False)
    register_event_handlers()

    # Phase 14: 注册门禁规则
    from app.services.gate_rules_phase14 import register_phase14_rules
    register_phase14_rules()

    # Phase 15: 注册任务事件处理器（统一在 lifespan 中注册）
    from app.services.task_event_handlers import register_event_handlers as register_task_handlers
    register_task_handlers()

    # 恢复 Redis Stream 中未处理的事件（服务重启后自动补偿）
    from app.services.event_bus import event_bus
    try:
        import asyncio as _aio
        replayed = await _aio.wait_for(event_bus.replay_pending_events(), timeout=5.0)
        if replayed:
            import logging
            logging.getLogger("audit_platform").info(f"[启动] 恢复了 {replayed} 个未处理事件")
    except Exception:
        pass  # Redis 不可用或超时时静默跳过

    # 补偿 DB outbox 中“已提交但未成功发布”的导入激活/回滚事件
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
            import logging
            logging.getLogger("audit_platform").info("[启动] 重放导入事件 outbox: %s", outbox_report)
    except Exception:
        pass

    # Phase 15: SLA 超时定时检查（每 15 分钟）
    import asyncio
    _sla_task = None
    _import_recover_task = None
    _outbox_replay_task = None

    async def _sla_check_loop():
        """使用独立会话避免与请求连接池竞争"""
        while True:
            try:
                await asyncio.sleep(900)  # 15 分钟
                from app.core.database import async_session
                from app.services.issue_ticket_service import issue_ticket_service
                async with async_session() as db:
                    escalated = await issue_ticket_service.check_sla_timeout(db)
                    if escalated:
                        await db.commit()
                        import logging
                        logging.getLogger("sla_check").info(f"[SLA] auto-escalated {len(escalated)} issues")
            except asyncio.CancelledError:
                break
            except Exception as e:
                import logging
                logging.getLogger("sla_check").warning(f"[SLA] check loop error: {e}")

    _sla_task = asyncio.create_task(_sla_check_loop())

    async def _import_recover_loop():
        while True:
            try:
                from app.services.import_job_runner import ImportJobRunner
                await ImportJobRunner.recover_jobs()
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                import logging
                logging.getLogger("import_recover").warning(f"[ImportRecover] loop error: {e}")

    if settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED:
        _import_recover_task = asyncio.create_task(_import_recover_loop())

    async def _outbox_replay_loop():
        import random
        import time as _time

        base_interval = max(5, int(settings.LEDGER_IMPORT_OUTBOX_REPLAY_INTERVAL_SECONDS))
        max_backoff = max(base_interval, int(settings.LEDGER_IMPORT_OUTBOX_REPLAY_MAX_BACKOFF_SECONDS))
        jitter_ratio = min(max(float(settings.LEDGER_IMPORT_OUTBOX_REPLAY_JITTER_RATIO), 0.0), 0.5)
        limit = max(1, int(settings.LEDGER_IMPORT_OUTBOX_REPLAY_LIMIT))
        max_attempts = int(settings.LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS or 0)
        cleanup_enabled = bool(settings.LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_ENABLED)
        cleanup_retention_days = max(1, int(settings.LEDGER_IMPORT_EVENT_CONSUMPTION_RETENTION_DAYS))
        cleanup_interval_seconds = max(60, int(settings.LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_INTERVAL_SECONDS))
        cleanup_batch_size = max(1, int(settings.LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_BATCH_SIZE))
        last_cleanup_monotonic = 0.0
        consecutive_failures = 0
        while True:
            try:
                from app.core.database import async_session
                from app.services.import_event_consumption_service import ImportEventConsumptionService
                from app.services.import_event_outbox_service import ImportEventOutboxService

                async with async_session() as db:
                    replay_kwargs = {"limit": limit}
                    if max_attempts > 0:
                        replay_kwargs["max_attempts"] = max_attempts
                    report = await ImportEventOutboxService.replay_pending(db, **replay_kwargs)
                    cleanup_report = {"deleted_count": 0}
                    if cleanup_enabled and (_time.monotonic() - last_cleanup_monotonic) >= cleanup_interval_seconds:
                        cleanup_report = await ImportEventConsumptionService.cleanup_older_than_days(
                            db,
                            retention_days=cleanup_retention_days,
                            batch_size=cleanup_batch_size,
                        )
                        last_cleanup_monotonic = _time.monotonic()
                    await db.commit()

                if report.get("failed_count"):
                    import logging
                    logging.getLogger("import_outbox").warning("[OutboxReplay] failed_count=%s report=%s", report.get("failed_count"), report)
                if report.get("exhausted_total_count", 0):
                    import logging
                    logging.getLogger("import_outbox").warning(
                        "[OutboxReplay] exhausted_total_count=%s, manual intervention required",
                        report.get("exhausted_total_count"),
                    )
                if cleanup_report.get("deleted_count", 0) > 0:
                    import logging
                    logging.getLogger("import_outbox").info(
                        "[OutboxReplay] cleaned up %s import event consumption rows",
                        cleanup_report.get("deleted_count"),
                    )

                if report.get("failed_count", 0) > 0:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

                effective_interval = min(max_backoff, base_interval * (2 ** min(consecutive_failures, 5)))
                jitter = effective_interval * jitter_ratio * random.random()
                await asyncio.sleep(effective_interval + jitter)
            except asyncio.CancelledError:
                break
            except Exception as e:
                import logging
                logging.getLogger("import_outbox").warning(f"[OutboxReplay] loop error: {e}")
                consecutive_failures += 1
                effective_interval = min(max_backoff, base_interval * (2 ** min(consecutive_failures, 5)))
                await asyncio.sleep(effective_interval)

    if settings.LEDGER_IMPORT_OUTBOX_REPLAY_ENABLED:
        _outbox_replay_task = asyncio.create_task(_outbox_replay_loop())

    yield

    # 优雅关闭
    if _sla_task:
        _sla_task.cancel()
        try:
            await _sla_task
        except asyncio.CancelledError:
            pass
    if _import_recover_task:
        _import_recover_task.cancel()
        try:
            await _import_recover_task
        except asyncio.CancelledError:
            pass
    if _outbox_replay_task:
        _outbox_replay_task.cancel()
        try:
            await _outbox_replay_task
        except asyncio.CancelledError:
            pass

    # 关闭数据库连接池
    from app.core.database import dispose_engine
    await dispose_engine()


app = FastAPI(
    title="审计作业平台",
    description="面向会计师事务所的审计全流程作业系统",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/version")
async def api_version():
    return {"version": "1.0.0", "api_prefix": "/api"}


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

# --- 路由注册（按业务域分组，详见 router_registry.py） ---
register_all_routers(app)
