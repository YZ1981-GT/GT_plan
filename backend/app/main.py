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
    """应用生命周期：启动时运行迁移 + 注册事件处理器 + 启动后台 Worker"""
    import asyncio
    setup_logging(level="INFO", json_format=False)

    await _run_migrations()
    register_event_handlers()
    _register_phase_handlers()
    await _replay_startup_events()

    stop_event = asyncio.Event()
    tasks = _start_workers(stop_event)

    yield

    # 优雅关闭：通知 worker + 取消 + 等待 + 释放 DB 连接池
    stop_event.set()
    for t in tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    from app.core.database import dispose_engine
    await dispose_engine()


async def _run_migrations() -> None:
    """数据库版本化迁移（D6：版本化 SQL 脚本）。失败时记录 warning 但不阻断启动。"""
    import logging as _mig_log
    from app.core.migration_runner import MigrationRunner
    try:
        runner = MigrationRunner(database_url=settings.DATABASE_URL)
        applied = await runner.run_pending()
        if applied:
            _mig_log.getLogger("audit_platform").info(
                "[启动] 数据库迁移完成，执行了版本: %s", applied
            )
        await runner.close()
    except Exception as _mig_err:
        _mig_log.getLogger("audit_platform").warning(
            "[启动] 数据库迁移失败（应用仍继续启动）: %s", _mig_err
        )


def _register_phase_handlers() -> None:
    """Phase 14/15 事件处理器与门禁规则注册。"""
    from app.services.gate_rules_phase14 import register_phase14_rules
    from app.services.gate_rules_eqcr import register_eqcr_gate_rules
    from app.services.task_event_handlers import (
        register_event_handlers as register_task_handlers,
    )
    register_phase14_rules()
    register_eqcr_gate_rules()
    register_task_handlers()


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
    from app.workers import sla_worker, import_recover_worker, outbox_replay_worker, audit_log_writer_worker, budget_alert_worker
    return [
        asyncio.create_task(sla_worker.run(stop_event)),
        asyncio.create_task(import_recover_worker.run(stop_event)),
        asyncio.create_task(outbox_replay_worker.run(stop_event)),
        asyncio.create_task(audit_log_writer_worker.run(stop_event)),
        asyncio.create_task(budget_alert_worker.run(stop_event)),
    ]


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
