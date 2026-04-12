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
from app.routers.companies import router as companies_router
from app.routers.consol_scope import router as consol_scope_router
from app.routers.consol_scope import router as consol_scope_router_v2
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
from app.routers.consolidation import router as consolidation_router
from app.routers.consol_scope import router as consol_scope_router
from app.routers.consol_trial import router as consol_trial_router
from app.routers.internal_trade import router as internal_trade_router
from app.routers.component_auditor import router as component_auditor_router
from app.routers.component_auditors import (
    router as component_auditors_router,
    instruction_router,
    result_router,
)
from app.routers.goodwill import router as goodwill_router
from app.routers.forex import router as forex_router
from app.routers.minority_interest import router as minority_interest_router
from app.routers.consol_report import router as consol_report_router
from app.routers.consol_notes import router as consol_notes_router
from app.routers.notifications import router as notifications_router
from app.routers.sync import router as sync_router
from app.routers.audit_logs import router as audit_logs_router
from app.routers.project_mgmt import router as project_mgmt_router
from app.routers.review import router as review_router
from app.routers.subsequent_events import router as subsequent_events_router
from app.routers.pbc import router as pbc_router
from app.routers.confirmations import router as confirmations_router
from app.routers.going_concern import router as going_concern_router
from app.routers.archive import router as archive_router
from app.routers.sync_conflict import router as sync_conflict_router
from app.routers.audit_plan import router as audit_plan_router
from app.routers.audit_findings import router as audit_findings_router
from app.routers.ai_admin import router as ai_admin_router
from app.routers.ai_risk_assessment import router as ai_risk_assessment_router
from app.routers.ai_workpaper import router as ai_workpaper_router
from app.routers.ai_ocr import router as ai_ocr_router, document_router as ai_document_router
from app.routers.ai_pdf_export import router as ai_pdf_export_router
from app.routers.ai_contract import router as ai_contract_router
from app.routers.ai_evidence_chain import router as ai_evidence_chain_router, project_router as ai_evidence_chain_project_router
from app.routers.ai_chat import router as ai_chat_router, project_router as ai_chat_project_router
from app.routers.ai_confirmation import router as ai_confirmation_router
from app.routers.ai_report import project_router as ai_report_router
from app.routers.ai_knowledge import router as ai_knowledge_router
from app.routers.nl_command import router as nl_command_router
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
    """应用生命周期：启动时注册事件处理器 + 预置AI模型"""
    from app.core.seed_ai_models import seed_ai_models, ensure_active_chat_model
    from app.core.database import async_session_maker

    register_event_handlers()

    # 预置 AI 模型初始数据
    try:
        async with async_session_maker() as db:
            await seed_ai_models(db)
            await ensure_active_chat_model(db)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"AI模型预置失败（非致命）: {e}")

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
app.include_router(consolidation_router)
app.include_router(consol_scope_router)
app.include_router(consol_scope_router_v2)
app.include_router(companies_router)
app.include_router(consol_trial_router)
app.include_router(internal_trade_router)
app.include_router(component_auditor_router)
app.include_router(component_auditors_router)
app.include_router(instruction_router)
app.include_router(result_router)
app.include_router(goodwill_router)
app.include_router(forex_router)
app.include_router(minority_interest_router)
app.include_router(consol_report_router)
app.include_router(consol_notes_router)
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(sync_router)
app.include_router(audit_logs_router)
app.include_router(project_mgmt_router)
app.include_router(review_router)
app.include_router(subsequent_events_router)
app.include_router(pbc_router)
app.include_router(confirmations_router)
app.include_router(going_concern_router)
app.include_router(archive_router)
app.include_router(sync_conflict_router)
app.include_router(audit_plan_router)
app.include_router(audit_findings_router)
app.include_router(ai_admin_router)
app.include_router(ai_risk_assessment_router)
app.include_router(ai_workpaper_router)
app.include_router(ai_ocr_router)
app.include_router(ai_document_router)
app.include_router(ai_pdf_export_router)
app.include_router(ai_contract_router)
app.include_router(ai_evidence_chain_router)
app.include_router(ai_evidence_chain_project_router)
app.include_router(ai_chat_router)
app.include_router(ai_chat_project_router)
app.include_router(ai_confirmation_router)
app.include_router(ai_report_router)
app.include_router(ai_knowledge_router)
app.include_router(nl_command_router)
