"""审计作业平台 — FastAPI 应用入口"""

import os
import sys

# FastAPI 每个 include_router 会嵌套一层 merged_lifespan（当前约 950+ 层）。
# 进入 lifespan 主体时栈已深约 6000+ 帧，其中的迁移/门禁子调用会再叠加，
# 因此上限需留足余量（默认 1000 会溢出，4000 仍不够导致迁移与门禁降级）。
_MIN_RECURSION_FOR_LIFESPAN = 10000
if sys.getrecursionlimit() < _MIN_RECURSION_FOR_LIFESPAN:
    sys.setrecursionlimit(_MIN_RECURSION_FOR_LIFESPAN)

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.core.build_version import get_build_version
from app.core.config import settings
from app.core.tracing import setup_tracing
from app.core.logging_config import setup_logging
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
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.inflight import InflightTrackingMiddleware
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

    if os.environ.get("GT_BOOTSTRAP_DONE") != "1":
        await _run_migrations()

    # 标记迁移完成 → readyz 探针开始返回就绪
    from app.core.runtime_state import migration_state
    migration_state.mark_complete()

    # ACNR Redis 客户端注入 — 必须在事件回放/缓存预热之前，
    # 否则 increment_epoch 在启动期看到未注入的客户端而误报降级 [Req-14]
    from app.core.redis import get_redis
    from app.services.acnr.cache_epoch import set_redis_client, start_epoch_subscriber
    _acnr_redis = await get_redis()
    if _acnr_redis is not None:
        set_redis_client(_acnr_redis)
    # ping 失败时不注入 None：保留懒解析，Redis 恢复后可自动接管

    register_event_handlers()
    # A13 错报评价自动聚合 EventBus handler
    from app.services.a13_event_handler import register_a13_event_handlers
    register_a13_event_handlers()
    _register_phase_handlers()
    await _replay_startup_events()
    # Grammar 源完整性校验 — 失败则 sys.exit(1) (Req-2)
    from app.services.acnr.grammar import validate_grammar_on_startup
    validate_grammar_on_startup()

    await _check_gin_index_status()
    await _check_libreoffice_health()

    # procedure-mainline-convergence Task 7.3: rollout fail-fast
    _validate_procedure_rollout_config()
    await _validate_template_manifest()
    await _run_schema_drift_check()
    await _warm_render_caches()
    _check_attachment_security_gates()

    # ACNR Redis pub-sub 订阅 + epoch 轮询兜底 [Req-14]
    await start_epoch_subscriber()

    # ACNR invalidation outbox dispatcher（至少一次投递 durable 失效）[R11]
    from app.services.acnr.invalidation_outbox import get_dispatcher as _get_acnr_dispatcher
    _get_acnr_dispatcher().start()

    # AI Chat run 启动恢复（dsh-agent-panel-integration Task 5 / Design 第 7 步）：
    # 上次进程崩溃/被 kill 时留下的 running run 在租约过期后无人接管 —— 扫描并按
    # “无外部副作用 + retry limit”重排，否则标 interrupted → error(run_interrupted)，
    # 让用户看到中文中断原因而不是永远转圈（Req 4.9）。
    await _recover_ai_chat_runs()

    # AI Chat 启动自检：local-only 验证与服务健康报告
    # （dsh-agent-panel-integration Task 30 / Req 12.1/12.2/12.4）
    # 🔴 不阻塞启动：violation 记录审计事件 + WARNING 日志；/capabilities 从缓存读取。
    await _run_ai_chat_health_check()

    # ACNR catalog 快照 GC（P2-1：启动清理无引用旧快照，防无界增长；best-effort 不阻断）
    import logging as _gc_log
    _gc_logger = _gc_log.getLogger("audit_platform")
    try:
        from app.services.acnr.catalog_snapshot_gc import run_db_aware_gc as _acnr_run_gc

        _gc_report = await _acnr_run_gc(keep_recent=10)
        _gc_logger.info(
            "ACNR snapshot GC: total=%s deleted=%s status=%s",
            _gc_report.get("total_snapshots"),
            len(_gc_report.get("deleted", [])),
            _gc_report.get("reference_status"),
        )
    except Exception as _gc_exc:
        _gc_logger.warning("ACNR snapshot GC (startup) failed (non-blocking): %s", _gc_exc)

    stop_event = asyncio.Event()
    tasks = _start_workers(stop_event)

    # 注册 SIGTERM handler（drain 用）
    from app.core.graceful_shutdown import install_sigterm_handler
    install_sigterm_handler()

    # 启动完成提示（即使在 WARNING 级别也会显示）
    print(f"[GT-Backend] Ready on port {os.getenv('PORT', '9980')} (log_level={log_level})")

    yield

    # --- 关闭阶段 ---
    # 1. SIGTERM 已置 draining=True（readyz 已 503）
    # 2. 给 nginx 健康检查留窗口（sleep PRE_DRAIN_DELAY）
    from app.core.graceful_shutdown import PRE_DRAIN_DELAY, drain_http_requests, GRACEFUL_SHUTDOWN_TIMEOUT
    await asyncio.sleep(PRE_DRAIN_DELAY)

    # 3. 优雅关闭所有 SSE 连接（组件 7a 实现）
    from app.core.sse_registry import sse_registry
    await sse_registry.close_all()

    # 4. Drain HTTP in-flight 请求
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


async def _run_ai_chat_health_check() -> None:
    """AI Chat 启动自检（dsh-agent-panel-integration Task 30 / Req 12.1/12.2/12.4）。

    验证 model/embedding/OCR endpoint 为本地，DSH SDK 状态。
    不阻塞启动：violation 记录 WARNING + 审计事件；结果缓存到模块变量供 /capabilities 读取。
    """
    import logging as _hc_log

    log = _hc_log.getLogger("audit_platform")
    try:
        from app.services.ai_chat.startup_health import run_ai_chat_startup_health_check

        report = await run_ai_chat_startup_health_check()
        if report.has_violations:
            log.warning("[ai-chat] %s", report.summary())
        else:
            log.info("[ai-chat] %s", report.summary())
    except Exception as exc:
        log.error("[ai-chat] 启动健康检查异常（不阻塞）: %s", exc)


async def _recover_ai_chat_runs() -> None:
    """AI Chat run 启动恢复（dsh-agent-panel-integration Task 5 / Req 4.9）。

    扫描租约已过期的 ``running`` run：无外部副作用且未达 retry limit 的重排回队列并
    重新执行（重排前会**重新授权** HostContext），其余标 ``interrupted → error``。

    失败记 **ERROR** 而非 WARNING：恢复不生效意味着有一批 run 永久卡在 running，
    用户侧表现是“一直转圈”。吞成 WARNING 就是典型的 fail-open。
    """
    import logging as _rec_log

    log = _rec_log.getLogger("audit_platform")
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


def _check_attachment_security_gates() -> None:
    """启动守卫：确认证据治理上传的三道内容门（媒体类型允许清单 / 恶意内容 / 可读性）
    在 production 已真实接线（R1.2/R1.3/R2/R15）。

    - ``ATTACHMENT_SECURITY_GATES_REQUIRED=true`` 且缺门 → 抛错阻断启动（fail-closed）。
    - production 缺门（未强制）→ loud WARNING + 治理指标 alert 暴露。
    - 非 production（dev/test/staging，合法注入 fake / 关门运行）→ 不阻断。

    守卫只看 ``APP_ENV`` / 配置开关，不做 pytest 检测 hack。
    """
    from app.services.evidence_governance.attachment_security_gates import (
        check_attachment_security_gates_startup,
    )

    check_attachment_security_gates_startup()


async def _warm_render_caches() -> None:
    """启动预热：把 render-config 热路径的重量级惰性导入 + 模板缓存在启动时加载完成。

    根因：`_get_render_config_impl` 内部 `from app.routers.wp_render_strategies import
    RENDERER_DISPATCH` 会一次性导入 100+ 个渲染策略子模块（及其传递依赖 openpyxl/
    resolvers/services），此前发生在**首个请求**内。首屏打开底稿时前端并发打一批请求，
    首个 render-config 边导入边被并发请求争抢事件循环 → 冷启动首请求被拖到数秒级
    （SLOW_REQUEST 7s）。在 lifespan 启动阶段（"Ready" 之前）预热后，首请求不再付导入代价。
    失败不阻塞启动。
    """
    import logging as _warm_log
    log = _warm_log.getLogger("audit_platform")
    try:
        # 1) 渲染策略分发表（最重的惰性导入，~0.4s + 传递依赖）
        from app.routers import wp_render_strategies  # noqa: F401
        _ = wp_render_strategies.RENDERER_DISPATCH
        # 2) 程序表模板 JSON（首次 _load_templates 读盘）
        from app.services.procedure_table_auto_service import _load_templates
        _load_templates()
        log.info("[启动] render 热路径预热完成（RENDERER_DISPATCH=%d）",
                 len(wp_render_strategies.RENDERER_DISPATCH))
    except Exception as e:  # noqa: BLE001 — 预热失败不阻塞启动，首请求会自行惰性导入
        log.warning("[启动] render 热路径预热失败（忽略，改由首请求惰性导入）: %s", e)


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
    import app.services.gate_rules_b60  # noqa: F401 — B60 矩阵/重要性门禁
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


async def _validate_template_manifest() -> None:
    """启动校验：template_manifest.json 引用文件存在、无 .doc 残留."""
    import logging as _log

    log = _log.getLogger("audit_platform")
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


def _validate_procedure_rollout_config() -> None:
    """procedure-mainline-convergence Task 7.3: rollout 值域 + 三开关组合 fail-fast。

    非法值或非法组合在 Ready 前失败（sys.exit(1)），不把配置错误带进生产流量。
    """
    import logging as _log
    from app.core.config import settings

    log = _log.getLogger("audit_platform.procedure_rollout")
    mode = settings.PROCEDURE_ROW_TASK_WRITE_MODE
    enabled = settings.PROCEDURE_ROW_TASKS_ENABLED
    dispatcher = settings.PROCEDURE_TASK_DISPATCHER_ENABLED

    VALID_MODES = {"legacy", "dual", "task_source", "paused"}
    if mode not in VALID_MODES:
        log.critical(
            "PROCEDURE_ROW_TASK_WRITE_MODE=%r 非法（合法值: %s），拒绝启动",
            mode, sorted(VALID_MODES),
        )
        sys.exit(1)

    # 非法组合：task_source 模式下必须开启 ENABLED（否则 overlay 不叠加，状态机写入无可见效果）
    if mode == "task_source" and not enabled:
        log.critical(
            "PROCEDURE_ROW_TASK_WRITE_MODE=task_source 但 PROCEDURE_ROW_TASKS_ENABLED=False "
            "（task overlay 不叠加 → 状态机写入无可见效果），拒绝启动",
        )
        sys.exit(1)

    # paused 模式下 dispatcher 必须关闭（drain 态不投递通知）
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
    """启动所有后台 Worker，返回 task 列表。

    # TODO: Worker 多副本去重（zero-downtime-deployment Task 9.2）
    # 对仍需 in-process 的 worker（sla/outbox/cleanup），每轮 run loop 先调：
    #   if not await try_acquire_leadership("worker_name"):
    #       await asyncio.sleep(interval); continue
    # 或用 @with_leader_lock("worker_name") 装饰器
    # from app.workers._leader_lock import try_acquire_leadership, with_leader_lock
    """
    import asyncio
    from app.workers import (
        sla_worker, import_recover_worker, outbox_replay_worker,
        audit_log_writer_worker, budget_alert_worker, dataset_purge_worker,
        staged_orphan_cleaner, export_cleanup_worker,
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
        # procedure-delegation-notification / Task 10：有序 outbox dispatcher。
        # 受 PROCEDURE_TASK_DISPATCHER_ENABLED 控制（expand 阶段默认 false → worker 直接退出）。
        asyncio.create_task(procedure_dispatcher_worker.run(stop_event)),
        # visibility-isolation-go-live-hardening Task 3 / R2：epoch 失效 Redis dispatcher。
        # subscriber（psubscribe 快路径淘汰）+ publisher（提交后 outbox fan-out），
        # 受 VISIBILITY_INVALIDATION_DISPATCHER_ENABLED 控制（默认 True）。Redis 不可用不阻塞
        # 启动 → 指数退避重连；重连期间由 PersistentEpochCache 的 ≤1s DB epoch 安全网兜底。
        asyncio.create_task(invalidation_dispatcher_worker.run(stop_event)),
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
app.add_middleware(GZipMiddleware, minimum_size=1000)  # 压缩响应
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
