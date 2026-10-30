"""审计作业平台 — FastAPI 应用入口"""

import os
import sys
import warnings

# ── 启动期第三方库警告抑制（无害、不可控、污染日志）──────────────────────────
# 1) jieba/_compat.py 在 import 期使用已弃用的 pkg_resources（jieba 自身已有 fallback）
#    setuptools>=81 把此警告改为 UserWarning（非 DeprecationWarning），两类都抑制
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated",
    category=UserWarning,
)
# 2) openpyxl 读含 Conditional Formatting / Data Validation 扩展的 xlsx 时发出 UserWarning
#    这些扩展不影响数据读取，只是 openpyxl 不支持完整保留它们
warnings.filterwarnings(
    "ignore",
    message="Conditional Formatting extension",
    category=UserWarning,
    module="openpyxl",
)
warnings.filterwarnings(
    "ignore",
    message="Data Validation extension",
    category=UserWarning,
    module="openpyxl",
)

# FastAPI 每个 include_router 会嵌套一层 merged_lifespan（当前约 950+ 层）。
# 进入 lifespan 主体时栈已深约 6000+ 帧，其中的迁移/门禁子调用会再叠加，
# 因此上限需留足余量（默认 1000 会溢出，4000 仍不够导致迁移与门禁降级）。
_MIN_RECURSION_FOR_LIFESPAN = 10000
if sys.getrecursionlimit() < _MIN_RECURSION_FOR_LIFESPAN:
    sys.setrecursionlimit(_MIN_RECURSION_FOR_LIFESPAN)

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

# 导入期调优（spec backend-startup-and-request-overhead R1），都必须在导入任何路由模块之前：
# 1) 抬 gen0 阈值：导入要建约 83 万个长寿对象，默认阈值下会做约 8 次全量收集（合计约 1.2 s）；
#    与启动预热同一套调优（app.core.gc_tuning，GT_GC_TUNING=0 关闭）。
# 2) 路由的依赖分析 / 参数模型推迟到第一次用到时再算：此后新建的 APIRouter 默认用 LazyAPIRoute。
from app.core.gc_tuning import configure_gc  # noqa: E402

configure_gc()

from app.core.lazy_api_routes import install_lazy_api_routes  # noqa: E402

install_lazy_api_routes()

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.build_version import get_build_version
from app.core.config import settings
from app.core.openapi_runtime import fastapi_docs_kwargs, install_deferred_docs
# 兼容旧导入路径：`app.main._start_workers` 与 lifespan 跑的是同一组 worker spec
from app.core.startup_registry import start_all_workers as _start_workers  # noqa: F401
from app.core.tracing import setup_tracing
from app.middleware.audit_log import AuditLogMiddleware
from app.middleware.error_handler import (
    evidence_governance_error_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.middleware.response import ResponseWrapperMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.rate_limiter import LLMRateLimitMiddleware
from app.middleware.app_version import AppVersionHeaderMiddleware
from app.middleware.body_limit import RequestBodyLimitMiddleware
from app.middleware.gzip_offload import OffloadingGZipMiddleware
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.inflight import InflightTrackingMiddleware
from app.router_registry import register_all_routers
from app.services.acnr.http_errors import (
    registry_lock_error_handler,
    version_invalid_error_handler,
    version_not_found_error_handler,
)
from app.services.acnr.project_registry_lock import RegistryLockError
from app.services.acnr.resolver import VersionInvalidError, VersionNotFoundError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动按 ``STARTUP_TASKS`` 串行执行，关闭阶段 drain + 停 worker。

    启动步骤（顺序 / 关键性 / 实现）只定义在 ``app.core.startup_registry``，逐项结果见
    ``/api/health`` 的 ``startup``。🔴 不要在这里内联启动步骤：曾经 main 与 registry
    各有一份，两边各自漂移（preexisting-test-failures-closure G11）。
    """
    import asyncio

    from app.core.startup_registry import StartupContext, run_startup_tasks

    ctx = StartupContext(extras={"app": app})
    await run_startup_tasks(context=ctx)
    stop_event = ctx.stop_event
    tasks = ctx.worker_tasks

    yield

    # --- 关闭阶段 ---
    # 热交接已在 reload_handoff 中完成「停 accept → 关 SSE → 0.5 s grace」，这里只跳过重复的
    # PRE_DRAIN_DELAY 与第二次 close_all；普通 SIGTERM / 关闭窗口保持原路径。
    from app.core import reload_handoff
    from app.core.graceful_shutdown import PRE_DRAIN_DELAY, drain_http_requests, GRACEFUL_SHUTDOWN_TIMEOUT
    from app.core.sse_registry import sse_registry

    if not reload_handoff.handoff_pre_drain_complete():
        await asyncio.sleep(PRE_DRAIN_DELAY)
        await sse_registry.close_all()

    # 两种路径都等待已经进入应用的 HTTP 请求完成。
    await drain_http_requests(GRACEFUL_SHUTDOWN_TIMEOUT)

    # 5. 后续是现有逻辑（stop_event.set() + worker cancel + dispose_engine）
    # F44 / Sprint 10.52: 优雅关闭 — 通知 worker stop_event + 取消 + 等待。
    stop_event.set()

    # 停止 ACNR epoch subscriber + poll [Req-14]
    from app.services.acnr.cache_epoch import stop_epoch_subscriber
    await stop_epoch_subscriber()

    # 停止 ACNR invalidation outbox dispatcher [R11]
    from app.services.acnr.invalidation_outbox import get_dispatcher as _get_acnr_dispatcher
    await _get_acnr_dispatcher().stop()

    for t in tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    from app.core.database import dispose_engine
    await dispose_engine()


app = FastAPI(
    title="审计作业平台",
    description="面向会计师事务所的审计全流程作业系统",
    version="1.0.0",
    lifespan=lifespan,
    **fastapi_docs_kwargs(settings.APP_ENV),
)
install_deferred_docs(app, settings.APP_ENV)

setup_tracing(app)


# TEMP: diagnostic endpoint for debugging registry capability issue
@app.get("/api/_debug/a51-capability")
async def debug_a51_capability():
    import os
    from app.services.workpaper_sync.entry_profile import (
        load_entry_manifest, manifest_entries_by_id, capability_of, ENTRY_MANIFEST_PATH,
    )
    m = load_entry_manifest()
    entries = manifest_entries_by_id(m)
    e = entries.get("xlsx/gt-a51-cashflow-audit", {})
    cap_raw = e.get("capability")
    mig = e.get("migration_state")
    has_bypass = False
    try:
        import app.services.workpaper_sync.adapters.registry as reg_mod
        src = open(reg_mod.__file__, "r", encoding="utf-8").read()
        has_bypass = "_CANARY_BYPASS" in src
    except Exception:
        pass
    return {
        "cwd": os.getcwd(),
        "manifest_path": str(ENTRY_MANIFEST_PATH),
        "manifest_exists": ENTRY_MANIFEST_PATH.exists(),
        "capability_raw": cap_raw,
        "migration_state": mig,
        "registry_has_bypass": has_bypass,
        "entry_count": len(entries),
    }


@app.get("/api/_debug/a51-content-revision")
async def debug_a51_content_revision(wp_id: str = "2246b5c0-19c3-4d66-bfb2-72d9afdc2996"):
    """返回指定底稿的 content_revision（canary 临时端点，无需认证）。"""
    import sqlalchemy as sa
    from app.core.database import engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        rev = (await session.execute(
            sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
            {"wp": wp_id},
        )).scalar_one_or_none()
    return {"content_revision": int(rev) if rev is not None else 0}


@app.get("/api/_debug/a51-registration")
async def debug_a51_registration():
    """检查 A5-1 adapter 注册的详细状态。"""
    from app.core.database import engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    result = {}
    try:
        from app.services.workpaper_sync.adapters.registry import build_production_registry
        registry = build_production_registry()
        # 检查 plan
        plan_items = registry.registration_plan or []
        a51_plan = [
            {"entry_id": item.entry_id, "blocked_reason": item.blocked_reason}
            for item in plan_items
            if "a51" in item.entry_id.lower()
        ]
        result["plan"] = a51_plan
        # 检查已注册
        regs = registry.registrations()
        a51_regs = [r.adapter_id for r in regs if "a51" in r.entry_id.lower()]
        result["registered_adapters"] = a51_regs
        # 尝试注册
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            try:
                outcome = await registry.register_from_manifest(session=session)
                result["outcome_registered"] = list(outcome.registered_entry_ids)
                result["outcome_failures"] = {
                    k: {"error_code": v.error_code, "message": v.message[:200]}
                    for k, v in outcome.failures.items()
                    if "a51" in k.lower()
                }
                result["outcome_reasons"] = {
                    k: v[:200] for k, v in outcome.reasons.items()
                    if "a51" in k.lower()
                }
            except Exception as exc:
                result["registration_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return result


@app.get("/api/version")
async def api_version():
    bv = get_build_version()
    return {
        "version": bv["semantic_version"],
        "git_commit": bv["git_commit"],
        "build_time": bv["build_time"],
        "api_prefix": "/api",
    }


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
from app.services.evidence_governance.frozen_contracts import (
    EvidenceGovernanceError as _EvidenceGovernanceError,
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(RegistryLockError, registry_lock_error_handler)
app.add_exception_handler(VersionNotFoundError, version_not_found_error_handler)
app.add_exception_handler(VersionInvalidError, version_invalid_error_handler)
# 证据治理稳定错误 → 脱敏 4xx/5xx（design §7.2）。必须先于泛型 Exception 处理器注册，
# 否则 SCOPE_NOT_FOUND_OR_FORBIDDEN 等会被 generic_exception_handler 误报为 500。
app.add_exception_handler(_EvidenceGovernanceError, evidence_governance_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# --- 中间件（LIFO：最后添加的最先执行=洋葱最外层） ---
# 洋葱模型从外到内：CORS → AppVersion → BodyLimit → GZip → Observability → ResponseWrapper → RequestID → RateLimit → AuditLog
# 添加顺序从内到外（先添加=最内层）：
app.add_middleware(InflightTrackingMiddleware)   # 最内层，in-flight 请求计数（drain 用）
app.add_middleware(AuditLogMiddleware)          # 记录路由真实响应状态码
app.add_middleware(LLMRateLimitMiddleware)      # LLM 限流
app.add_middleware(RequestIDMiddleware)         # 注入 request_id
app.add_middleware(ResponseWrapperMiddleware)   # 统一响应格式
app.add_middleware(ObservabilityMiddleware)     # 请求指标采集 + 慢请求告警
app.add_middleware(OffloadingGZipMiddleware, minimum_size=1000)  # 压缩响应（大响应体在工作线程里压）
app.add_middleware(RequestBodyLimitMiddleware)  # 超大请求拦截
app.add_middleware(AppVersionHeaderMiddleware)   # 注入 X-App-Version 头（所有响应含错误）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 路由注册（按业务域分组，详见 router_registry/ 包） ---
register_all_routers(app)

# 路由按路径段建索引，一次请求只对可能匹配的几条调 matches（spec backend-startup-and-request-overhead R3.2；
# GT_ROUTE_INDEX=0 关闭）。必须在全部路由注册之后。
from app.core.route_index import install_route_index  # noqa: E402

install_route_index(app.router)
