"""事件处理器注册 — 应用启动时调用

将 TrialBalanceService 和 ReportEngine 的事件处理方法注册到 EventBus。
由于事件处理器需要数据库会话，这里使用工厂函数创建带会话的处理器。

Validates: Requirements 10.1-10.6, 2.4, 8.1
"""

from __future__ import annotations

import logging

from app.core.database import async_session as async_session_factory
from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.event_bus import event_bus
from app.services.trial_balance_service import TrialBalanceService

logger = logging.getLogger(__name__)


def _make_handler(service_class, method_name: str):
    """创建一个带独立数据库会话的事件处理器，异常时自动回滚"""

    async def handler(payload: EventPayload) -> None:
        async with async_session_factory() as session:
            try:
                svc = service_class(session)
                method = getattr(svc, method_name)
                await method(payload)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

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

    logger.info("All event handlers registered successfully (including formula cache invalidation)")
