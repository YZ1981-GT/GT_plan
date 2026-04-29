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

    # Phase 15: SLA 超时定时检查（每 15 分钟）
    import asyncio
    _sla_task = None

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

    yield

    # 优雅关闭
    if _sla_task:
        _sla_task.cancel()
        try:
            await _sla_task
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
