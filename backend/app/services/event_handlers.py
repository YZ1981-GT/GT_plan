"""事件处理器注册 — 应用启动时调用

将 TrialBalanceService 和 ReportEngine 的事件处理方法注册到 EventBus。
由于事件处理器需要数据库会话，这里使用工厂函数创建带会话的处理器。

Validates: Requirements 10.1-10.6, 2.4, 8.1
"""

from __future__ import annotations

import logging

from app.core.database import async_session as async_session_factory
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.dataset_models import ImportEventConsumption
from app.services.event_bus import event_bus
from app.services.trial_balance_service import TrialBalanceService
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def _make_handler(service_class, method_name: str, after_commit_event_type: EventType | None = None):
    """创建一个带独立数据库会话的事件处理器，异常时自动回滚"""
    handler_key = f"{service_class.__name__}.{method_name}"

    async def handler(payload: EventPayload) -> None:
        async with async_session_factory() as session:
            try:
                # Import outbox 事件携带稳定 event_id，使用 DB 唯一约束做跨实例幂等。
                dedup_event_id = None
                if isinstance(payload.extra, dict):
                    dedup_event_id = payload.extra.get("__event_id")
                if dedup_event_id:
                    session.add(
                        ImportEventConsumption(
                            event_id=str(dedup_event_id),
                            handler_name=handler_key,
                            project_id=payload.project_id,
                            year=payload.year,
                        )
                    )
                    try:
                        await session.flush()
                    except IntegrityError:
                        await session.rollback()
                        logger.info("Skip duplicated event delivery: event_id=%s handler=%s", dedup_event_id, handler_key)
                        return
                svc = service_class(session)
                method = getattr(svc, method_name)
                await method(payload)
                await session.commit()
                if after_commit_event_type is not None and payload.year is not None:
                    await event_bus.publish_immediate(EventPayload(
                        event_type=after_commit_event_type,
                        project_id=payload.project_id,
                        year=payload.year,
                        account_codes=payload.account_codes,
                        batch_id=payload.batch_id,
                        entry_group_id=payload.entry_group_id,
                        extra=payload.extra,
                    ))
            except Exception:
                await session.rollback()
                raise

    handler.__qualname__ = handler_key
    return handler


def _make_tb_handler(method_name: str):
    """创建 TrialBalanceService 事件处理器（向后兼容）"""
    return _make_handler(
        TrialBalanceService,
        method_name,
        after_commit_event_type=EventType.TRIAL_BALANCE_UPDATED,
    )


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
    event_bus.subscribe(
        EventType.LEDGER_DATASET_ACTIVATED,
        _make_tb_handler("on_data_imported"),
    )
    event_bus.subscribe(
        EventType.LEDGER_DATASET_ROLLED_BACK,
        _make_tb_handler("on_import_rolled_back"),
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
        _make_handler(
            ReportEngine,
            "on_trial_balance_updated",
            after_commit_event_type=EventType.REPORTS_UPDATED,
        ),
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
    # 底稿保存 → 审定数比对 + 预填充过期标记 (阶段三)
    # ------------------------------------------------------------------
    async def _on_workpaper_saved(payload: EventPayload) -> None:
        """底稿保存后：比对审定数与试算表，标记一致性状态"""
        wp_id = payload.extra.get("wp_id") if payload.extra else None
        if not wp_id:
            return
        async with async_session_factory() as session:
            try:
                from app.services.wp_mapping_service import WpMappingService
                from app.models.audit_platform_models import TrialBalance
                from app.models.workpaper_models import WorkingPaper
                import sqlalchemy as _sa

                # 1. 查找底稿及其 parsed_data
                wp_result = await session.execute(
                    _sa.select(WorkingPaper).where(
                        WorkingPaper.id == wp_id,
                        WorkingPaper.is_deleted == _sa.false(),
                    )
                )
                wp = wp_result.scalar_one_or_none()
                if not wp or not wp.parsed_data:
                    return

                # 2. 从 parsed_data 提取审定数
                wp_audited = wp.parsed_data.get("audited_amount")
                if wp_audited is None:
                    return

                # 3. 查找映射关系
                from app.models.workpaper_models import WpIndex
                idx_result = await session.execute(
                    _sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id)
                )
                wp_code = idx_result.scalar_one_or_none()
                if not wp_code:
                    return

                svc = WpMappingService(session)
                mapping = svc.find_by_wp_code(wp_code)
                if not mapping:
                    return

                # 4. 从试算表取审定数比对
                from decimal import Decimal
                codes = mapping.get("account_codes", [])
                if not codes:
                    return

                tb_result = await session.execute(
                    _sa.select(
                        _sa.func.coalesce(_sa.func.sum(TrialBalance.audited_amount), 0)
                    ).where(
                        TrialBalance.project_id == payload.project_id,
                        TrialBalance.standard_account_code.in_(codes),
                        TrialBalance.is_deleted == _sa.false(),
                    )
                )
                tb_total = Decimal(str(tb_result.scalar() or 0))
                wp_val = Decimal(str(wp_audited))
                diff = abs(tb_total - wp_val)

                # 5. 写入一致性状态到 parsed_data
                wp.parsed_data = {
                    **wp.parsed_data,
                    "wp_consistency": {
                        "status": "consistent" if diff < Decimal("0.01") else "inconsistent",
                        "tb_amount": str(tb_total),
                        "wp_amount": str(wp_val),
                        "diff_amount": str(diff),
                    },
                }
                await session.commit()
                logger.info(
                    "wp_consistency: wp=%s status=%s diff=%s",
                    wp_id,
                    wp.parsed_data["wp_consistency"]["status"],
                    diff,
                )
            except Exception as e:
                await session.rollback()
                logger.warning("on_workpaper_saved consistency check failed: %s", e)

    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_workpaper_saved)

    # ------------------------------------------------------------------
    # 数据变更 → 公式缓存失效 (Task 15.1)
    # ------------------------------------------------------------------
    from app.services.formula_engine import FormulaEngine

    async def _invalidate_formula_cache_on_adjustment(payload: EventPayload) -> None:
        """调整分录变更 → 失效涉及科目的公式缓存"""
        try:
            if not payload.year:
                logger.warning("Skip formula cache invalidation: missing year for event %s", payload.event_type)
                return
            from app.core.redis import redis_client
            engine = FormulaEngine(redis_client=redis_client)
            await engine.invalidate_cache(
                project_id=payload.project_id,
                year=payload.year,
                affected_accounts=payload.account_codes,
            )
        except Exception:
            logger.warning("Formula cache invalidation failed (Redis unavailable)")

    async def _invalidate_formula_cache_all(payload: EventPayload) -> None:
        """数据导入 → 失效全部公式缓存"""
        try:
            if not payload.year:
                logger.warning("Skip formula cache invalidation: missing year for event %s", payload.event_type)
                return
            from app.core.redis import redis_client
            engine = FormulaEngine(redis_client=redis_client)
            await engine.invalidate_cache(
                project_id=payload.project_id,
                year=payload.year,
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
        EventType.LEDGER_DATASET_ACTIVATED,
        _invalidate_formula_cache_all,
    )
    event_bus.subscribe(
        EventType.LEDGER_DATASET_ROLLED_BACK,
        _invalidate_formula_cache_all,
    )
    event_bus.subscribe(
        EventType.MAPPING_CHANGED,
        _invalidate_formula_cache_on_adjustment,
    )

    logger.info("All event handlers registered successfully (including formula cache invalidation)")

    # ------------------------------------------------------------------
    # Phase 9: 底稿预填过期标记
    # ------------------------------------------------------------------
    async def _mark_workpapers_stale_all(payload: EventPayload) -> None:
        """数据导入 → 标记所有底稿预填数据为过期"""
        try:
            async with async_session_factory() as session:
                from app.services.prefill_engine import mark_stale
                count = await mark_stale(session, payload.project_id)
                await session.commit()
                logger.info(f"Marked {count} workpapers as stale for project {payload.project_id}")
        except Exception:
            logger.warning("Failed to mark workpapers stale")

    async def _mark_workpapers_stale_by_account(payload: EventPayload) -> None:
        """调整分录变更 → 标记关联科目底稿预填数据为过期"""
        try:
            async with async_session_factory() as session:
                from app.services.prefill_engine import mark_stale
                count = await mark_stale(session, payload.project_id, payload.account_codes)
                await session.commit()
                logger.info(f"Marked {count} workpapers as stale (account change)")
        except Exception:
            logger.warning("Failed to mark workpapers stale on adjustment change")

    event_bus.subscribe(EventType.DATA_IMPORTED, _mark_workpapers_stale_all)
    event_bus.subscribe(EventType.LEDGER_DATASET_ACTIVATED, _mark_workpapers_stale_all)
    event_bus.subscribe(EventType.LEDGER_DATASET_ROLLED_BACK, _mark_workpapers_stale_all)
    event_bus.subscribe(EventType.ADJUSTMENT_CREATED, _mark_workpapers_stale_by_account)
    event_bus.subscribe(EventType.ADJUSTMENT_UPDATED, _mark_workpapers_stale_by_account)
    event_bus.subscribe(EventType.ADJUSTMENT_DELETED, _mark_workpapers_stale_by_account)
    event_bus.subscribe(EventType.MAPPING_CHANGED, _mark_workpapers_stale_by_account)

    logger.info("Phase 9 workpaper event handlers registered")
