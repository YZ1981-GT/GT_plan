"""审计作业平台 — FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.users import router as users_router
from app.api.wopi import router as wopi_router
from app.routers.account_chart import router as account_chart_router
from app.routers.mapping import router as mapping_router
from app.routers.project_wizard import router as project_wizard_router
from app.routers.data_import import router as data_import_router
from app.routers.report_line_mapping import router as report_line_mapping_router
from app.routers.drilldown import router as drilldown_router
from app.routers.trial_balance import router as trial_balance_router
from app.routers.adjustments import router as adjustments_router
from app.routers.materiality import router as materiality_router
from app.routers.events import router as events_router
from app.routers.misstatements import router as misstatements_router
from app.routers.report_config import router as report_config_router
from app.routers.reports import router as reports_router
from app.routers.cfs_worksheet import router as cfs_worksheet_router
from app.routers.disclosure_notes import router as disclosure_notes_router
from app.routers.audit_report import router as audit_report_router
from app.routers.export import router as export_router
from app.routers.formula import router as formula_router
from app.routers.wp_template import router as wp_template_router
from app.routers.working_paper import router as working_paper_router
from app.routers.qc import router as qc_router
from app.routers.wp_review import router as wp_review_router
from app.routers.sampling import router as sampling_router
from app.core.config import settings
from app.middleware.audit_log import AuditLogMiddleware
from app.middleware.error_handler import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.middleware.response import ResponseWrapperMiddleware
from app.services.event_handlers import register_event_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时注册事件处理器"""
    register_event_handlers()
    yield


app = FastAPI(
    title="审计作业平台",
    description="面向会计师事务所的审计全流程作业系统",
    version="0.1.0",
    lifespan=lifespan,
)

# --- 异常处理器注册 ---
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# --- 中间件注册（Starlette LIFO：最后添加的最先执行） ---
# 1) AuditLogMiddleware（最内层 — 最接近路由处理器）
app.add_middleware(AuditLogMiddleware)
# 2) ResponseWrapperMiddleware（包装在审计日志之外）
app.add_middleware(ResponseWrapperMiddleware)
# 3) CORS 中间件（最外层 — 最先处理跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 路由注册 ---
app.include_router(auth_router, prefix="/api/auth")
app.include_router(users_router, prefix="/api/users")
app.include_router(health_router, prefix="/api")
app.include_router(wopi_router, prefix="/wopi")
app.include_router(project_wizard_router)
app.include_router(account_chart_router)
app.include_router(mapping_router)
app.include_router(report_line_mapping_router)
app.include_router(data_import_router)
app.include_router(drilldown_router)
app.include_router(trial_balance_router)
app.include_router(adjustments_router)
app.include_router(materiality_router)
app.include_router(events_router)
app.include_router(misstatements_router)
app.include_router(report_config_router)
app.include_router(reports_router)
app.include_router(cfs_worksheet_router)
app.include_router(disclosure_notes_router)
app.include_router(audit_report_router)
app.include_router(export_router)
app.include_router(formula_router)
app.include_router(wp_template_router)
app.include_router(working_paper_router)
app.include_router(qc_router)
app.include_router(wp_review_router)
app.include_router(sampling_router)
