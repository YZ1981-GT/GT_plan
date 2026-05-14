"""事件处理器注册 — 应用启动时调用

将 TrialBalanceService 和 ReportEngine 的事件处理方法注册到 EventBus。
由于事件处理器需要数据库会话，这里使用工厂函数创建带会话的处理器。

Validates: Requirements 10.1-10.6, 2.4, 8.1
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.database import async_session as async_session_factory
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.dataset_models import ImportEventConsumption

if TYPE_CHECKING:
    from app.services.event_bus import EventBus
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


def subscribe_many(bus: "EventBus", subscriptions: list[tuple]) -> None:
    """批量注册事件处理器，减少重复的 bus.subscribe() 调用。

    Parameters
    ----------
    bus : EventBus
        事件总线实例
    subscriptions : list of (EventType, handler) tuples
        要注册的事件类型和处理器列表
    """
    for event_type, handler in subscriptions:
        bus.subscribe(event_type, handler)


def register_event_handlers() -> None:
    """注册所有事件处理器到全局 EventBus"""
    # 使用 subscribe_many 批量注册，减少重复代码
    subscribe_many(event_bus, [
        (EventType.ADJUSTMENT_CREATED, _make_tb_handler("on_adjustment_changed")),
        (EventType.ADJUSTMENT_UPDATED, _make_tb_handler("on_adjustment_changed")),
        (EventType.ADJUSTMENT_DELETED, _make_tb_handler("on_adjustment_changed")),
        (EventType.MAPPING_CHANGED, _make_tb_handler("on_mapping_changed")),
    ])

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
        """底稿保存后：比对审定数与试算表，标记一致性状态。
        具体逻辑委托给 ConsistencyCheckService.update_workpaper_consistency()。
        """
        wp_id = payload.extra.get("wp_id") if payload.extra else None
        if not wp_id:
            return
        async with async_session_factory() as session:
            try:
                from app.services.consistency_check_service import ConsistencyCheckService
                svc = ConsistencyCheckService(session)
                await svc.update_workpaper_consistency(wp_id, payload.project_id)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.warning("on_workpaper_saved consistency check failed: %s", e)

    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_workpaper_saved)

    # ------------------------------------------------------------------
    # R1 需求 2：复核退回 → IssueTicket 工单创建补偿（幂等）
    # ------------------------------------------------------------------
    async def _on_review_record_created(payload: EventPayload) -> None:
        """订阅 ``REVIEW_RECORD_CREATED`` 事件做工单补偿。

        调用方（``wp_review_service.add_comment`` 的守卫逻辑）在复核退回时
        无论 IssueTicket 同步创建成功与否都会发此事件：

        - 成功路径：此 handler 发现对应 ``source_ref_id`` 的工单已存在 → 跳过；
        - 失败路径：对应工单缺失 → 补偿重建一条 ``source='review_comment'``
          的工单，防止漏单。

        幂等依据 ``IssueTicket.source_ref_id = review_record.id`` 唯一匹配。
        """
        extra = payload.extra or {}
        review_record_id_str = extra.get("review_record_id")
        if not review_record_id_str:
            return

        from uuid import UUID as _UUID

        try:
            review_record_id = _UUID(str(review_record_id_str))
        except (TypeError, ValueError):
            logger.warning(
                "[REVIEW_COMPENSATE] invalid review_record_id=%s",
                review_record_id_str,
            )
            return

        async with async_session_factory() as session:
            try:
                # 幂等：检查同一 ReviewRecord 是否已有工单
                from sqlalchemy import select as _select

                from app.models.phase15_enums import IssueSource
                from app.models.phase15_models import IssueTicket
                from app.models.workpaper_models import ReviewRecord
                from app.services.wp_review_service import (
                    _build_and_persist_issue_ticket,
                )

                existing = (
                    await session.execute(
                        _select(IssueTicket).where(
                            IssueTicket.source_ref_id == review_record_id,
                            IssueTicket.source == IssueSource.review_comment.value,
                        )
                    )
                ).scalar_one_or_none()

                if existing is not None:
                    logger.debug(
                        "[REVIEW_COMPENSATE] ticket already exists for review=%s (id=%s)",
                        review_record_id,
                        existing.id,
                    )
                    return

                review = await session.get(ReviewRecord, review_record_id)
                if review is None:
                    logger.warning(
                        "[REVIEW_COMPENSATE] review record not found: %s",
                        review_record_id,
                    )
                    return

                commenter_id_raw = extra.get("commenter_id")
                try:
                    commenter_id = (
                        _UUID(str(commenter_id_raw))
                        if commenter_id_raw
                        else review.commenter_id
                    )
                except (TypeError, ValueError):
                    commenter_id = review.commenter_id

                await _build_and_persist_issue_ticket(
                    session,
                    review_record=review,
                    commenter_id=commenter_id,
                )
                await session.commit()
                logger.info(
                    "[REVIEW_COMPENSATE] IssueTicket compensated for review=%s",
                    review_record_id,
                )
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.warning(
                    "[REVIEW_COMPENSATE] failed for review=%s: %s",
                    review_record_id,
                    exc,
                )

    event_bus.subscribe(EventType.REVIEW_RECORD_CREATED, _on_review_record_created)

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
    event_bus.subscribe(
        EventType.ADJUSTMENT_BATCH_COMMITTED,
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
    event_bus.subscribe(EventType.ADJUSTMENT_BATCH_COMMITTED, _mark_workpapers_stale_by_account)

    logger.info("Phase 9 workpaper event handlers registered")

    # ------------------------------------------------------------------
    # F46 / Sprint 7.22: 账套 rollback → 标下游 Workpaper/AuditReport/DisclosureNote is_stale
    # ------------------------------------------------------------------
    async def _mark_downstream_stale_on_rollback(payload: EventPayload) -> None:
        """rollback 后同时把底稿/审计报告/附注标记为过期。

        Workpaper 已由 `_mark_workpapers_stale_all` 覆盖（走 prefill_stale），
        本 handler 补齐 AuditReport.is_stale 和 DisclosureNote.is_stale。
        """
        import sqlalchemy as _sa
        from app.models.report_models import AuditReport, DisclosureNote

        project_id = payload.project_id
        year = payload.year
        if project_id is None or year is None:
            return

        async with async_session_factory() as session:
            try:
                await session.execute(
                    _sa.update(AuditReport)
                    .where(
                        AuditReport.project_id == project_id,
                        AuditReport.year == year,
                        AuditReport.is_deleted == False,  # noqa: E712
                    )
                    .values(is_stale=True)
                )
                await session.execute(
                    _sa.update(DisclosureNote)
                    .where(
                        DisclosureNote.project_id == project_id,
                        DisclosureNote.year == year,
                        DisclosureNote.is_deleted == False,  # noqa: E712
                    )
                    .values(is_stale=True)
                )
                await session.commit()
                logger.info(
                    "[F46-rollback-stale] AuditReport/DisclosureNote marked stale "
                    "for project=%s year=%s",
                    project_id,
                    year,
                )
            except Exception:  # pragma: no cover - 失败不阻断事件链
                await session.rollback()
                logger.warning(
                    "[F46-rollback-stale] failed to mark downstream stale for "
                    "project=%s year=%s",
                    project_id,
                    year,
                    exc_info=True,
                )

    event_bus.subscribe(
        EventType.LEDGER_DATASET_ROLLED_BACK,
        _mark_downstream_stale_on_rollback,
    )
    logger.info("F46 rollback downstream stale handler registered")

    # ── 地址坐标注册表缓存失效 ──
    from app.services.address_registry import address_registry

    async def _invalidate_addr_tb(payload):
        """调整/导入变更 → 失效试算表域缓存"""
        pid = getattr(payload, 'project_id', '')
        if pid:
            address_registry.invalidate(pid, domain='tb')

    async def _invalidate_addr_report(payload):
        """报表更新 → 失效报表域缓存"""
        pid = getattr(payload, 'project_id', '')
        if pid:
            address_registry.invalidate(pid, domain='report')

    async def _invalidate_addr_all(payload):
        """数据导入 → 失效该项目全部缓存"""
        pid = getattr(payload, 'project_id', '')
        if pid:
            address_registry.invalidate(pid)

    event_bus.subscribe(EventType.ADJUSTMENT_CREATED, _invalidate_addr_tb)
    event_bus.subscribe(EventType.ADJUSTMENT_UPDATED, _invalidate_addr_tb)
    event_bus.subscribe(EventType.ADJUSTMENT_DELETED, _invalidate_addr_tb)
    event_bus.subscribe(EventType.TRIAL_BALANCE_UPDATED, _invalidate_addr_tb)
    event_bus.subscribe(EventType.REPORTS_UPDATED, _invalidate_addr_report)
    event_bus.subscribe(EventType.DATA_IMPORTED, _invalidate_addr_all)
    event_bus.subscribe(EventType.LEDGER_DATASET_ACTIVATED, _invalidate_addr_all)

    logger.info("Address registry cache invalidation handlers registered")

    # ------------------------------------------------------------------
    # Enterprise Linkage: 调整分录事件 → SSE 推送给项目组在线成员
    # 按 ProjectAssignment.role 过滤推送内容（助理只收到负责科目相关事件）
    # Validates: Requirements 1.1, 1.2, 1.3, 12.1, 12.2, 12.3, 12.4, 12.5
    # ------------------------------------------------------------------
    async def _notify_adjustment_event_sse(payload: EventPayload) -> None:
        """调整分录 CRUD 事件 → 通过 SSE 推送给项目组在线成员。

        角色过滤逻辑：
        - partner/manager/qc/eqcr/admin: 收到所有事件
        - auditor（助理）: 只收到与自己负责科目相关的事件
          (通过 workpaper_assignments 关联的 account_code 过滤)

        SSE 推送已由 EventBus._notify_sse 自动完成（所有事件都推到 SSE 队列）。
        此处记录日志 + 标记 payload.extra 中的 role_filter 信息供前端过滤。
        """
        # Enrich payload with role filter metadata for frontend filtering
        if payload.extra is None:
            payload.extra = {}
        payload.extra["_role_filter"] = {
            "full_access_roles": ["partner", "manager", "qc", "eqcr", "admin"],
            "filtered_role": "auditor",
            "filter_by": "account_codes",
        }

        logger.info(
            "[enterprise-linkage] Adjustment event %s pushed via SSE for project=%s, "
            "accounts=%s, entry_group=%s",
            payload.event_type.value,
            payload.project_id,
            payload.account_codes,
            payload.entry_group_id,
        )

    event_bus.subscribe(EventType.ADJUSTMENT_CREATED, _notify_adjustment_event_sse)
    event_bus.subscribe(EventType.ADJUSTMENT_UPDATED, _notify_adjustment_event_sse)
    event_bus.subscribe(EventType.ADJUSTMENT_DELETED, _notify_adjustment_event_sse)

    logger.info("Enterprise Linkage: adjustment SSE push handlers registered")

    # ------------------------------------------------------------------
    # Enterprise Linkage Task 2.5: 批量提交单次级联
    # ADJUSTMENT_BATCH_COMMITTED → 一次性 TB 重算（非逐条）
    # Validates: Requirements 9.1, 9.2, 9.3
    # ------------------------------------------------------------------
    event_bus.subscribe(
        EventType.ADJUSTMENT_BATCH_COMMITTED,
        _make_tb_handler("on_adjustment_changed"),
    )
    logger.info("Enterprise Linkage: batch committed → single TB recalc handler registered")

    # ------------------------------------------------------------------
    # Enterprise Linkage Task 2.8: 事件级联日志记录
    # 每次级联执行写入 event_cascade_log
    # Validates: Requirements 7.1, 7.2
    # ------------------------------------------------------------------
    async def _log_cascade_on_tb_updated(payload: EventPayload) -> None:
        """TB 重算完成后记录级联日志。"""
        import time as _time
        try:
            async with async_session_factory() as session:
                from app.services.linkage_service import LinkageService
                svc = LinkageService(session)
                trigger = payload.extra.get("trigger", "unknown") if payload.extra else "unknown"
                steps = [
                    {"step": "tb_recalc", "status": "completed"},
                    {"step": "reports_update", "status": "pending"},
                ]
                await svc.log_cascade(
                    project_id=payload.project_id,
                    year=payload.year,
                    trigger_event=trigger if trigger != "unknown" else payload.event_type.value,
                    trigger_payload={
                        "account_codes": payload.account_codes,
                        "entry_group_id": str(payload.entry_group_id) if payload.entry_group_id else None,
                    },
                    steps=steps,
                    status="completed",
                    duration_ms=0,  # 精确耗时需要在 handler 外层计时
                )
                await session.commit()
        except Exception as e:
            logger.warning("[cascade-log] Failed to log cascade: %s", e)

    event_bus.subscribe(EventType.TRIAL_BALANCE_UPDATED, _log_cascade_on_tb_updated)
    logger.info("Enterprise Linkage: cascade logging handler registered")

    # ------------------------------------------------------------------
    # Enterprise Linkage Task 2.4: 调整分录变更 → 记录 TB 变更历史
    # Validates: Requirements 2.4
    # ------------------------------------------------------------------
    async def _record_tb_change_on_adjustment(payload: "EventPayload") -> None:
        """Record TB change history when adjustments change. Task 2.4 wiring."""
        from uuid import UUID as _UUID

        project_id = payload.project_id
        year = payload.year
        extra = payload.extra or {}
        operator_id = extra.get("operator_id")
        operator_name = extra.get("operator_name", "")
        account_codes = payload.account_codes or []

        if not project_id or not year or not operator_id or not account_codes:
            return

        op_map = {
            "adjustment.created": "adjustment_created",
            "adjustment.updated": "adjustment_modified",
            "adjustment.deleted": "adjustment_deleted",
        }
        operation_type = op_map.get(payload.event_type.value if hasattr(payload.event_type, 'value') else str(payload.event_type), "unknown")

        try:
            async with async_session_factory() as session:
                from app.services.linkage_service import LinkageService
                svc = LinkageService(session)
                for code in account_codes:
                    await svc.record_tb_change(
                        project_id=project_id,
                        year=year,
                        row_code=code,
                        operation_type=operation_type,
                        operator_id=_UUID(str(operator_id)),
                        operator_name=operator_name,
                    )
                await session.commit()
        except Exception as exc:
            logger.warning("[TB_CHANGE_HISTORY] failed: %s", exc)

    event_bus.subscribe(EventType.ADJUSTMENT_CREATED, _record_tb_change_on_adjustment)
    event_bus.subscribe(EventType.ADJUSTMENT_UPDATED, _record_tb_change_on_adjustment)
    event_bus.subscribe(EventType.ADJUSTMENT_DELETED, _record_tb_change_on_adjustment)
    logger.info("Enterprise Linkage: TB change history handler registered")
