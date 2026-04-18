"""审计作业平台 — FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

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
from app.routers.gt_coding import router as gt_coding_router
from app.routers.t_accounts import router as t_accounts_router
from app.routers.ledger_penetration import router as ledger_penetration_router
from app.routers.metabase import router as metabase_router
from app.routers.attachments import router as attachments_router
from app.routers.custom_templates import router as custom_templates_router
from app.routers.consolidation import router as consolidation_router
from app.routers.consol_scope import router as consol_scope_router
from app.routers.consol_trial import router as consol_trial_router
from app.routers.internal_trade import router as internal_trade_router
from app.routers.component_auditor import router as component_auditor_router
from app.routers.goodwill import router as goodwill_router
from app.routers.forex import router as forex_router
from app.routers.minority_interest import router as minority_interest_router
from app.routers.consol_notes import router as consol_notes_router
from app.routers.consol_report import router as consol_report_router
from app.routers.accounting_standards import router as accounting_standards_router
from app.routers.i18n import router as i18n_router
from app.routers.audit_types import router as audit_types_router
from app.routers.signatures import router as signatures_router
from app.routers.ai_plugins import router as ai_plugins_router
from app.routers.regulatory import router as regulatory_router
from app.routers.note_templates import router as note_templates_router
from app.routers.workpaper_summary import router as workpaper_summary_router
from app.routers.ai_unified import router as ai_unified_router
from app.routers.ai_models import router as ai_models_router
from app.routers.recycle_bin import router as recycle_bin_router
from app.routers.staff import router as staff_router
from app.routers.assignments import router as assignments_router_v2
from app.routers.workhours import router as workhours_router
from app.routers.dashboard import router as dashboard_router
from app.routers.consistency import router as consistency_router
from app.routers.procedures import router as procedures_router
from app.routers.wp_progress import router as wp_progress_router
from app.routers.wp_ai import router as wp_ai_router
from app.routers.tb_sync import router as tb_sync_router
from app.routers.note_wp_mapping import router as note_wp_mapping_router
from app.routers.note_trim import router as note_trim_router
from app.routers.subsequent_events import router as subsequent_events_router
from app.routers.note_ai import router as note_ai_router
from app.routers.wp_storage import router as wp_storage_router
from app.routers.wp_download import router as wp_download_router
from app.routers.continuous_audit import router as continuous_audit_router
from app.routers.private_storage import router as private_storage_router
from app.routers.process_record import router as process_record_router
from app.routers.wp_chat import router as wp_chat_router
from app.routers.sampling_enhanced import router as sampling_enhanced_router
from app.routers.review_conversations import router as review_conversations_router
from app.routers.annotations import router as annotations_router_v2
from app.routers.forum import router as forum_router
from app.routers.report_trace import router as report_trace_router
from app.routers.feature_flags import router as feature_flags_router
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时注册事件处理器"""
    setup_logging(level="INFO", json_format=False)  # 开发模式用文本格式，生产改 True
    register_event_handlers()
    yield


app = FastAPI(
    title="审计作业平台",
    description="面向会计师事务所的审计全流程作业系统",
    version="1.0.0",
    lifespan=lifespan,
)

# API 版本信息端点
@app.get("/api/version")
async def api_version():
    return {"version": "1.0.0", "api_prefix": "/api", "note": "当前为 v1，未来升级将使用 /api/v2/"}

# --- 异常处理器注册 ---
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# --- 中间件注册（Starlette LIFO：最后添加的最先执行） ---
# 1) AuditLogMiddleware（最内层 — 最接近路由处理器）
app.add_middleware(AuditLogMiddleware)
# 2) RequestIDMiddleware（链路追踪）
app.add_middleware(RequestIDMiddleware)
# 3) ResponseWrapperMiddleware（包装在审计日志之外）
app.add_middleware(ResponseWrapperMiddleware)
# 3) GZip 压缩（大 JSON 响应自动压缩）
app.add_middleware(GZipMiddleware, minimum_size=1000)
# 4) CORS 中间件（最外层 — 最先处理跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
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
app.include_router(gt_coding_router)
app.include_router(t_accounts_router)
app.include_router(ledger_penetration_router)
app.include_router(metabase_router)
app.include_router(attachments_router)
app.include_router(custom_templates_router)
app.include_router(consolidation_router)
app.include_router(consol_scope_router)
app.include_router(consol_trial_router)
app.include_router(internal_trade_router)
app.include_router(component_auditor_router)
app.include_router(goodwill_router)
app.include_router(forex_router)
app.include_router(minority_interest_router)
app.include_router(consol_notes_router)
app.include_router(consol_report_router)
app.include_router(accounting_standards_router)
app.include_router(i18n_router)
app.include_router(audit_types_router)
app.include_router(signatures_router)
app.include_router(ai_plugins_router)
app.include_router(regulatory_router)
app.include_router(note_templates_router)
app.include_router(workpaper_summary_router)
app.include_router(ai_unified_router)
app.include_router(ai_models_router)
app.include_router(recycle_bin_router)
app.include_router(staff_router)
app.include_router(assignments_router_v2)
app.include_router(workhours_router)
app.include_router(dashboard_router)
app.include_router(consistency_router)
app.include_router(procedures_router)
app.include_router(wp_progress_router)
app.include_router(wp_ai_router)
app.include_router(tb_sync_router)
app.include_router(note_wp_mapping_router)
app.include_router(note_trim_router)
app.include_router(subsequent_events_router)
app.include_router(note_ai_router)
app.include_router(wp_storage_router)
app.include_router(wp_download_router)
app.include_router(continuous_audit_router)
app.include_router(private_storage_router)
app.include_router(process_record_router)
app.include_router(wp_chat_router)
app.include_router(sampling_enhanced_router)
app.include_router(review_conversations_router)
app.include_router(annotations_router_v2)
app.include_router(forum_router)
app.include_router(report_trace_router)
app.include_router(feature_flags_router)
