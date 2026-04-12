"""事件处理器注册 — 应用启动时调用

将 TrialBalanceService 和 ReportEngine 的事件处理方法注册到 EventBus。
由于事件处理器需要数据库会话，这里使用工厂函数创建带会话的处理器。

Phase 2 合并抵消新增处理器：
- ELIMINATION_CREATED/UPDATED/DELETED → on_elimination_changed（增量重算）
- CONSOL_SCOPE_CHANGED → on_scope_changed（全量重算）
- FOREX_TRANSLATED → on_forex_translated（带外币的全量重算）
- COMPONENT_RESULT_ACCEPTED → on_component_accepted（全量重算）

Validates: Requirements 10.1-10.6, 2.4, 8.1, 3.4
"""

from __future__ import annotations

import logging

from app.core.database import async_session as async_session_factory
from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.event_bus import event_bus
from app.services.trial_balance_service import TrialBalanceService

logger = logging.getLogger(__name__)


def _make_handler(service_class, method_name: str):
    """创建一个带独立数据库会话的事件处理器"""

    async def handler(payload: EventPayload) -> None:
        async with async_session_factory() as session:
            svc = service_class(session)
            method = getattr(svc, method_name)
            await method(payload)
            await session.commit()

    handler.__qualname__ = f"{service_class.__name__}.{method_name}"
    return handler


def _make_tb_handler(method_name: str):
    """创建 TrialBalanceService 事件处理器（向后兼容）"""
    return _make_handler(TrialBalanceService, method_name)


def register_event_handlers() -> None:
    """注册所有事件处理器到全局 EventBus"""
    # 调整分录 CRUD → 增量重算
    event_bus.subscribe(
        EventType.ADJUSTMENT_CREATED,
        _make_tb_handler("on_adjustment_changed"),
    )
    event_bus.subscribe(
        EventType.ADJUSTMENT_UPDATED,
        _make_tb_handler("on_adjustment_changed"),
    )
    event_bus.subscribe(
        EventType.ADJUSTMENT_DELETED,
        _make_tb_handler("on_adjustment_changed"),
    )

    # 科目映射变更 → 重算未审数
    event_bus.subscribe(
        EventType.MAPPING_CHANGED,
        _make_tb_handler("on_mapping_changed"),
    )

    # 数据导入完成 → 全量重算
    event_bus.subscribe(
        EventType.DATA_IMPORTED,
        _make_tb_handler("on_data_imported"),
    )

    # 导入回滚 → 全量重算
    event_bus.subscribe(
        EventType.IMPORT_ROLLED_BACK,
        _make_tb_handler("on_import_rolled_back"),
    )

    # 试算表更新 → 报表增量更新
    from app.services.report_engine import ReportEngine
    event_bus.subscribe(
        EventType.TRIAL_BALANCE_UPDATED,
        _make_handler(ReportEngine, "on_trial_balance_updated"),
    )

    # 报表更新 → 附注增量更新
    from app.services.disclosure_engine import DisclosureEngine
    event_bus.subscribe(
        EventType.REPORTS_UPDATED,
        _make_handler(DisclosureEngine, "on_reports_updated"),
    )

    # 报表更新 → 审计报告财务数据刷新
    from app.services.audit_report_service import AuditReportService
    event_bus.subscribe(
        EventType.REPORTS_UPDATED,
        _make_handler(AuditReportService, "on_reports_updated"),
    )

    # ------------------------------------------------------------------
    # 数据变更 → 公式缓存失效 (Task 15.1)
    # ------------------------------------------------------------------
    from app.services.formula_engine import FormulaEngine

    async def _invalidate_formula_cache_on_adjustment(payload: EventPayload) -> None:
        """调整分录变更 → 失效涉及科目的公式缓存"""
        try:
            from app.core.redis import redis_client
            engine = FormulaEngine(redis_client=redis_client)
            await engine.invalidate_cache(
                project_id=payload.project_id,
                year=payload.year or 2025,
                affected_accounts=payload.account_codes,
            )
        except Exception:
            logger.warning("Formula cache invalidation failed (Redis unavailable)")

    async def _invalidate_formula_cache_all(payload: EventPayload) -> None:
        """数据导入 → 失效全部公式缓存"""
        try:
            from app.core.redis import redis_client
            engine = FormulaEngine(redis_client=redis_client)
            await engine.invalidate_cache(
                project_id=payload.project_id,
                year=payload.year or 2025,
            )
        except Exception:
            logger.warning("Formula cache invalidation failed (Redis unavailable)")

    event_bus.subscribe(
        EventType.ADJUSTMENT_CREATED,
        _invalidate_formula_cache_on_adjustment,
    )
    event_bus.subscribe(
        EventType.ADJUSTMENT_UPDATED,
        _invalidate_formula_cache_on_adjustment,
    )
    event_bus.subscribe(
        EventType.ADJUSTMENT_DELETED,
        _invalidate_formula_cache_on_adjustment,
    )
    event_bus.subscribe(
        EventType.DATA_IMPORTED,
        _invalidate_formula_cache_all,
    )
    event_bus.subscribe(
        EventType.MAPPING_CHANGED,
        _invalidate_formula_cache_on_adjustment,
    )

    # ------------------------------------------------------------------
    # Phase 2: 合并抵消事件处理器 (Task 7.4)
    # ------------------------------------------------------------------
    from app.services.consol_trial_service import (
        full_recalc_async,
        incremental_recalc_async,
    )

    async def _consol_full_recalc_handler(payload: EventPayload) -> None:
        """合并试算表全量重算（通用）"""
        if payload.year is None:
            logger.warning("Consolidation recalc skipped: year is None")
            return
        async with async_session_factory() as session:
            try:
                await full_recalc_async(session, payload.project_id, payload.year)
                await session.commit()
                logger.info(
                    "Consol full recalc completed for project=%s year=%d",
                    payload.project_id,
                    payload.year,
                )
            except Exception:
                logger.exception("Consol full recalc failed")

    async def _consol_incremental_recalc_handler(payload: EventPayload) -> None:
        """合并试算表增量重算（指定科目）"""
        if payload.year is None:
            logger.warning("Consolidation incremental recalc skipped: year is None")
            return
        async with async_session_factory() as session:
            try:
                await incremental_recalc_async(
                    session,
                    payload.project_id,
                    payload.year,
                    payload.account_codes,
                )
                await session.commit()
                logger.info(
                    "Consol incremental recalc completed for project=%s year=%d accounts=%s",
                    payload.project_id,
                    payload.year,
                    payload.account_codes,
                )
            except Exception:
                logger.exception("Consol incremental recalc failed")

    # 抵消分录变更 → 增量重算（仅重算抵消列）
    event_bus.subscribe(
        EventType.ELIMINATION_CREATED,
        _consol_incremental_recalc_handler,
    )
    event_bus.subscribe(
        EventType.ELIMINATION_UPDATED,
        _consol_incremental_recalc_handler,
    )
    event_bus.subscribe(
        EventType.ELIMINATION_DELETED,
        _consol_incremental_recalc_handler,
    )

    # 合并范围变更 → 全量重算（因为 individual_sum 可能变化）
    event_bus.subscribe(
        EventType.CONSOL_SCOPE_CHANGED,
        _consol_full_recalc_handler,
    )

    # 外币折算完成 → 全量重算（individual_sum 使用折算后金额）
    event_bus.subscribe(
        EventType.FOREX_TRANSLATED,
        _consol_full_recalc_handler,
    )

    # 组成部分审计结果接受 → 全量重算
    event_bus.subscribe(
        EventType.COMPONENT_RESULT_ACCEPTED,
        _consol_full_recalc_handler,
    )

    # ------------------------------------------------------------------
    # Phase 3: 协作与质控 — 事件→通知映射 (Task 8.3)
    # ------------------------------------------------------------------
    from app.services.notification_service import notification_service

    event_bus.subscribe(
        EventType.REVIEW_SUBMITTED,
        notification_service.on_review_submitted,
    )
    event_bus.subscribe(
        EventType.REVIEW_COMPLETED,
        notification_service.on_review_completed,
    )
    event_bus.subscribe(
        EventType.REVIEW_RESPONDED,
        notification_service.on_review_responded,
    )
    event_bus.subscribe(
        EventType.SYNC_CONFLICT,
        notification_service.on_sync_conflict,
    )
    event_bus.subscribe(
        EventType.CONFIRMATION_OVERDUE,
        notification_service.on_confirmation_overdue,
    )
    event_bus.subscribe(
        EventType.MISSTATEMENT_THRESHOLD,
        notification_service.on_misstatement_alert,
    )
    event_bus.subscribe(
        EventType.GOING_CONCERN_ALERT,
        notification_service.on_going_concern_alert,
    )

    logger.info("All event handlers registered successfully (including consolidation and collaboration handlers)")
