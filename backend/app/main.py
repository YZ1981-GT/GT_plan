"""审计作业平台 — FastAPI 应用入口"""

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
from app.services.event_handlers import register_event_handlers
from app.router_registry import register_all_routers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时注册事件处理器"""
    setup_logging(level="INFO", json_format=False)
    register_event_handlers()
    yield


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

# --- 中间件（LIFO：最后添加的最先执行） ---
app.add_middleware(AuditLogMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(ResponseWrapperMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 路由注册（按业务域分组，详见 router_registry.py） ---
register_all_routers(app)
