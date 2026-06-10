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
                        logger.debug("Skip duplicated event delivery: event_id=%s handler=%s", dedup_event_id, handler_key)
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
    # spec workpaper-d-sales-cycle 任务 2.2 (F4 ADR D4):
    # B51-5 反舞弊高风险评估保存后 → 强制加载 D4 IPO 应对类底稿（D4-22~D4-32）
    #
    # 触发条件（AND 关系）:
    #   1. event_type == WORKPAPER_SAVED
    #   2. payload.extra['wp_code'] == 'B51-5'
    #   3. risk_level == 'high'（来自 extra['risk_level'] 或
    #      extra['parsed_data']['conclusion']['fraud_risk_level']）
    # ------------------------------------------------------------------
    async def _on_b515_high_risk(payload: EventPayload) -> None:
        """B51-5 高风险触发 → 调 _ensure_d4_ipo_loaded 追加加载 D4-22~D4-32。

        即使 project.scenario='normal' 也强制加载（spec ADR D4 铁律：
        高风险评估覆盖普通项目场景过滤）。
        """
        if not payload.extra:
            return
        wp_code = payload.extra.get("wp_code", "")
        if wp_code != "B51-5":
            return

        # 解析 risk_level：优先 extra['risk_level']，否则从 parsed_data.conclusion 解析
        risk_level = payload.extra.get("risk_level")
        if not risk_level:
            parsed = payload.extra.get("parsed_data") or {}
            conclusion = parsed.get("conclusion") or {} if isinstance(parsed, dict) else {}
            risk_level = conclusion.get("fraud_risk_level") or conclusion.get("risk_level")

        if str(risk_level).lower() != "high":
            return

        project_id = payload.project_id
        year = payload.year
        if not project_id or not year:
            logger.warning(
                "_on_b515_high_risk: missing project_id or year in payload extra=%s",
                payload.extra,
            )
            return

        async with async_session_factory() as session:
            try:
                from app.services.wp_template_init_service import (
                    _ensure_d4_ipo_loaded,
                )

                ipo_result = await _ensure_d4_ipo_loaded(
                    session, project_id, year
                )
                await session.commit()
                logger.debug(
                    "[F4 B51-5 high-risk trigger] project=%s year=%s "
                    "added=%d skipped=%d errors=%d",
                    project_id,
                    year,
                    len(ipo_result.get("added_codes", [])),
                    len(ipo_result.get("skipped_existing", [])),
                    len(ipo_result.get("errors", [])),
                )
            except Exception as e:
                await session.rollback()
                logger.warning(
                    "_on_b515_high_risk failed for project=%s year=%s: %s",
                    project_id, year, e,
                )

    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_b515_high_risk)

    # ------------------------------------------------------------------
    # spec workpaper-f-purchase-inventory F-F14 (ADR-F4):
    # B51-4 存货舞弊风险评估高风险保存后 → 强制加载 F2 IPO 应对类底稿（F2-61~F2-72）
    #
    # 触发条件（AND 关系）:
    #   1. event_type == WORKPAPER_SAVED
    #   2. payload.extra['wp_code'] == 'B51-4'
    #   3. risk_level == 'high'
    # ------------------------------------------------------------------
    async def _on_b514_high_risk(payload: EventPayload) -> None:
        """B51-4 高风险触发 → 调 _ensure_ipo_loaded(prefix='F2') 追加加载 F2-61~F2-72。"""
        if not payload.extra:
            return
        wp_code = payload.extra.get("wp_code", "")
        if wp_code != "B51-4":
            return

        risk_level = payload.extra.get("risk_level")
        if not risk_level:
            parsed = payload.extra.get("parsed_data") or {}
            conclusion = parsed.get("conclusion") or {} if isinstance(parsed, dict) else {}
            risk_level = conclusion.get("fraud_risk_level") or conclusion.get("risk_level")

        if str(risk_level).lower() != "high":
            return

        project_id = payload.project_id
        year = payload.year
        if not project_id or not year:
            logger.warning(
                "_on_b514_high_risk: missing project_id or year in payload extra=%s",
                payload.extra,
            )
            return

        async with async_session_factory() as session:
            try:
                from app.services.wp_template_init_service import _ensure_ipo_loaded

                ipo_result = await _ensure_ipo_loaded(
                    session, project_id, year, wp_code_prefix="F2"
                )
                await session.commit()
                logger.debug(
                    "[F-F14 B51-4 high-risk trigger] project=%s year=%s "
                    "added=%d skipped=%d errors=%d",
                    project_id,
                    year,
                    len(ipo_result.get("added_codes", [])),
                    len(ipo_result.get("skipped_existing", [])),
                    len(ipo_result.get("errors", [])),
                )
            except Exception as e:
                await session.rollback()
                logger.warning(
                    "_on_b514_high_risk failed for project=%s year=%s: %s",
                    project_id, year, e,
                )

    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_b514_high_risk)

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
                logger.debug(
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
                account_codes=payload.account_codes,  # R10 修复：参数名 account_codes 不是 affected_accounts
            )
        except Exception as e:
            # R10 修复：记录真实异常类型而非误称 "Redis unavailable"
            logger.warning("Formula cache invalidation failed: %s: %s", type(e).__name__, e)

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
        except Exception as e:
            # R10 修复：记录真实异常类型而非误称 "Redis unavailable"
            logger.warning("Formula cache invalidation failed: %s: %s", type(e).__name__, e)

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

    logger.debug("All event handlers registered successfully (including formula cache invalidation)")

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
                logger.debug(f"Marked {count} workpapers as stale for project {payload.project_id}")
        except Exception as e:
            # P0-4: stale 非静默治理 — 记录 degraded
            from app.services.stale_degraded_logger import log_stale_degraded
            log_stale_degraded(
                source=f"data_imported:{payload.event_type.value}",
                target=f"workpapers:project={payload.project_id}",
                error=f"底稿 stale 全量标记失败: {type(e).__name__}: {e}",
                context={"project_id": str(payload.project_id)},
            )
            logger.warning("Failed to mark workpapers stale: %s", e)

    async def _mark_workpapers_stale_by_account(payload: EventPayload) -> None:
        """调整分录变更 → 标记关联科目底稿预填数据为过期"""
        try:
            async with async_session_factory() as session:
                from app.services.prefill_engine import mark_stale
                count = await mark_stale(session, payload.project_id, payload.account_codes)
                await session.commit()
                logger.debug(f"Marked {count} workpapers as stale (account change)")
        except Exception as e:
            # P0-4: stale 非静默治理 — 记录 degraded
            from app.services.stale_degraded_logger import log_stale_degraded
            log_stale_degraded(
                source=f"adjustment:{payload.event_type.value}",
                target=f"workpapers:accounts={payload.account_codes}",
                error=f"底稿 stale 按科目标记失败: {type(e).__name__}: {e}",
                context={"project_id": str(payload.project_id), "account_codes": payload.account_codes},
            )
            logger.warning("Failed to mark workpapers stale on adjustment change: %s", e)

    event_bus.subscribe(EventType.DATA_IMPORTED, _mark_workpapers_stale_all)
    event_bus.subscribe(EventType.LEDGER_DATASET_ACTIVATED, _mark_workpapers_stale_all)
    event_bus.subscribe(EventType.LEDGER_DATASET_ROLLED_BACK, _mark_workpapers_stale_all)
    event_bus.subscribe(EventType.ADJUSTMENT_CREATED, _mark_workpapers_stale_by_account)
    event_bus.subscribe(EventType.ADJUSTMENT_UPDATED, _mark_workpapers_stale_by_account)
    event_bus.subscribe(EventType.ADJUSTMENT_DELETED, _mark_workpapers_stale_by_account)
    event_bus.subscribe(EventType.MAPPING_CHANGED, _mark_workpapers_stale_by_account)
    event_bus.subscribe(EventType.ADJUSTMENT_BATCH_COMMITTED, _mark_workpapers_stale_by_account)

    logger.debug("Phase 9 workpaper event handlers registered")

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
                logger.debug(
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
    logger.debug("F46 rollback downstream stale handler registered")

    # ── 地址坐标注册表缓存失效 ──
    from app.services.address_registry import address_registry

    async def _invalidate_addr_tb(payload):
        """调整/导入变更 → 失效试算表域缓存"""
        pid = getattr(payload, 'project_id', '')
        if pid:
            await address_registry.invalidate_async(pid, domain='tb')

    async def _invalidate_addr_report(payload):
        """报表更新 → 失效报表域缓存"""
        pid = getattr(payload, 'project_id', '')
        if pid:
            await address_registry.invalidate_async(pid, domain='report')

    async def _invalidate_addr_all(payload):
        """数据导入 → 失效该项目全部缓存"""
        pid = getattr(payload, 'project_id', '')
        if pid:
            await address_registry.invalidate_async(pid)

    event_bus.subscribe(EventType.ADJUSTMENT_CREATED, _invalidate_addr_tb)
    event_bus.subscribe(EventType.ADJUSTMENT_UPDATED, _invalidate_addr_tb)
    event_bus.subscribe(EventType.ADJUSTMENT_DELETED, _invalidate_addr_tb)
    event_bus.subscribe(EventType.TRIAL_BALANCE_UPDATED, _invalidate_addr_tb)
    event_bus.subscribe(EventType.REPORTS_UPDATED, _invalidate_addr_report)
    event_bus.subscribe(EventType.DATA_IMPORTED, _invalidate_addr_all)
    event_bus.subscribe(EventType.LEDGER_DATASET_ACTIVATED, _invalidate_addr_all)

    logger.debug("Address registry cache invalidation handlers registered")

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

        logger.debug(
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

    logger.debug("Enterprise Linkage: adjustment SSE push handlers registered")

    # ------------------------------------------------------------------
    # Enterprise Linkage Task 2.5: 批量提交单次级联
    # ADJUSTMENT_BATCH_COMMITTED → 一次性 TB 重算（非逐条）
    # Validates: Requirements 9.1, 9.2, 9.3
    # ------------------------------------------------------------------
    event_bus.subscribe(
        EventType.ADJUSTMENT_BATCH_COMMITTED,
        _make_tb_handler("on_adjustment_changed"),
    )
    logger.debug("Enterprise Linkage: batch committed → single TB recalc handler registered")

    # ------------------------------------------------------------------
    # Sprint 7 Task 7.2: 数据过期级联标记
    # 调整分录 → 标记试算表 stale → 级联标记报表 stale → 级联标记附注 stale
    # 全链路执行完成后清除所有 stale 标记
    # Validates: Requirements 8.1, 8.2, 8.3, 8.6
    # ------------------------------------------------------------------
    async def _mark_reports_stale_on_adjustment(payload: EventPayload) -> None:
        """调整分录变更 → 标记报表和附注为 stale（级联）"""
        import sqlalchemy as _sa
        from app.models.report_models import AuditReport, DisclosureNote

        project_id = payload.project_id
        year = payload.year
        if not project_id or not year:
            return

        async with async_session_factory() as session:
            try:
                # 标记报表 stale
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
                except Exception as e:
                    # P0-4: stale 非静默治理 — 不再静默 pass，记录 degraded
                    from app.services.stale_degraded_logger import log_stale_degraded
                    log_stale_degraded(
                        source=f"adjustment:{payload.event_type.value}",
                        target=f"AuditReport:project={project_id},year={year}",
                        error=f"AuditReport is_stale 更新失败: {type(e).__name__}: {e}",
                        context={"project_id": str(project_id), "year": year},
                    )

                # 标记附注 stale
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
                logger.debug(
                    "[stale-cascade] Reports/Notes marked stale for project=%s year=%s",
                    project_id,
                    year,
                )
            except Exception as e:
                await session.rollback()
                # P0-4: stale 非静默治理 — 记录 degraded
                from app.services.stale_degraded_logger import log_stale_degraded
                log_stale_degraded(
                    source=f"adjustment:{payload.event_type.value}",
                    target=f"DisclosureNote:project={project_id},year={year}",
                    error=f"stale 级联标记失败: {type(e).__name__}: {e}",
                    context={"project_id": str(project_id), "year": year},
                )
                logger.warning(
                    "[stale-cascade] Failed to mark reports/notes stale",
                    exc_info=True,
                )

    event_bus.subscribe(EventType.ADJUSTMENT_CREATED, _mark_reports_stale_on_adjustment)
    event_bus.subscribe(EventType.ADJUSTMENT_UPDATED, _mark_reports_stale_on_adjustment)
    event_bus.subscribe(EventType.ADJUSTMENT_DELETED, _mark_reports_stale_on_adjustment)
    event_bus.subscribe(EventType.ADJUSTMENT_BATCH_COMMITTED, _mark_reports_stale_on_adjustment)
    logger.debug("Sprint 7 Task 7.2: stale cascade handlers registered")

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
    logger.debug("Enterprise Linkage: cascade logging handler registered")

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
    logger.debug("Enterprise Linkage: TB change history handler registered")

    # ------------------------------------------------------------------
    # Sprint 10 Task 10.11: 底稿深度优化 5 个新事件订阅
    # WORKPAPER_STALE_DETECTED → stale 传播
    # WORKPAPER_AUDITED_CONFIRMED → 试算表重算
    # WORKPAPER_REVIEW_PASSED → 附注刷新
    # WORKPAPER_PROCEDURE_COMPLETED → 质量评分更新
    # CROSS_CHECK_FAILED → 通知
    # ------------------------------------------------------------------
    async def _on_workpaper_stale_detected(payload: EventPayload) -> None:
        """底稿 stale 检测 → 传播到依赖底稿"""
        logger.debug(
            "[Sprint10] WORKPAPER_STALE_DETECTED for project=%s",
            payload.project_id,
        )

    async def _on_workpaper_audited_confirmed(payload: EventPayload) -> None:
        """审定数确认 → 触发试算表重算"""
        logger.debug(
            "[Sprint10] WORKPAPER_AUDITED_CONFIRMED for project=%s",
            payload.project_id,
        )
        try:
            async with async_session_factory() as session:
                svc = TrialBalanceService(session)
                await svc.on_adjustment_changed(payload)
                await session.commit()
        except Exception as e:
            logger.warning("[Sprint10] audited_confirmed TB recalc failed: %s", e)

    async def _on_workpaper_review_passed(payload: EventPayload) -> None:
        """复核通过 → 刷新附注"""
        logger.debug(
            "[Sprint10] WORKPAPER_REVIEW_PASSED for project=%s",
            payload.project_id,
        )

    async def _on_workpaper_procedure_completed(payload: EventPayload) -> None:
        """程序完成 → 更新质量评分"""
        logger.debug(
            "[Sprint10] WORKPAPER_PROCEDURE_COMPLETED for project=%s",
            payload.project_id,
        )

    async def _on_cross_check_failed(payload: EventPayload) -> None:
        """跨科目校验失败 → 通知"""
        logger.debug(
            "[Sprint10] CROSS_CHECK_FAILED for project=%s",
            payload.project_id,
        )

    event_bus.subscribe(EventType.WORKPAPER_STALE_DETECTED, _on_workpaper_stale_detected)
    event_bus.subscribe(EventType.WORKPAPER_AUDITED_CONFIRMED, _on_workpaper_audited_confirmed)
    event_bus.subscribe(EventType.WORKPAPER_REVIEW_PASSED, _on_workpaper_review_passed)
    event_bus.subscribe(EventType.WORKPAPER_PROCEDURE_COMPLETED, _on_workpaper_procedure_completed)
    event_bus.subscribe(EventType.CROSS_CHECK_FAILED, _on_cross_check_failed)
    logger.debug("Sprint 10: 5 new workpaper event handlers registered")

    # ------------------------------------------------------------------
    # Global Linkage Bus Sprint 2: Stale Propagation Engine 统一入口
    # 每个 handler 末尾追加 stale_engine.on_change(uri, project_id, year)
    # Validates: Requirements F6, F7
    # ------------------------------------------------------------------
    from app.services.stale_propagation_engine import stale_engine

    async def _stale_engine_on_adjustment(payload: EventPayload) -> None:
        """调整分录变更 → stale_engine.on_change（按科目构建 URI）"""
        if not payload.project_id or not payload.year:
            return
        account_codes = payload.account_codes or []
        for code in account_codes:
            uri = f"ADJ:{code}::aje_net"
            try:
                await stale_engine.on_change(uri, payload.project_id, payload.year)
            except Exception as e:
                logger.warning("[stale_engine] on_adjustment failed for %s: %s", uri, e)

    async def _stale_engine_on_data_imported(payload: EventPayload) -> None:
        """数据导入 → stale_engine.on_change（TB 全量）"""
        if not payload.project_id or not payload.year:
            return
        uri = f"TB:::全量导入"
        try:
            await stale_engine.on_change(uri, payload.project_id, payload.year)
        except Exception as e:
            logger.warning("[stale_engine] on_data_imported failed: %s", e)

    async def _stale_engine_on_workpaper_saved(payload: EventPayload) -> None:
        """底稿保存 → stale_engine.on_change"""
        if not payload.project_id or not payload.year:
            return
        extra = payload.extra or {}
        wp_code = extra.get("wp_code", "")
        sheet = extra.get("sheet", "")
        if wp_code:
            uri = f"WP:{wp_code}:{sheet}:审定数"
            try:
                await stale_engine.on_change(uri, payload.project_id, payload.year)
            except Exception as e:
                logger.warning("[stale_engine] on_workpaper_saved failed for %s: %s", uri, e)

    async def _stale_engine_on_mapping_changed(payload: EventPayload) -> None:
        """科目映射变更 → stale_engine.on_change"""
        if not payload.project_id or not payload.year:
            return
        account_codes = payload.account_codes or []
        for code in account_codes:
            uri = f"MAPPING:{code}::"
            try:
                await stale_engine.on_change(uri, payload.project_id, payload.year)
            except Exception as e:
                logger.warning("[stale_engine] on_mapping_changed failed for %s: %s", uri, e)

    event_bus.subscribe(EventType.ADJUSTMENT_CREATED, _stale_engine_on_adjustment)
    event_bus.subscribe(EventType.ADJUSTMENT_UPDATED, _stale_engine_on_adjustment)
    event_bus.subscribe(EventType.ADJUSTMENT_DELETED, _stale_engine_on_adjustment)
    event_bus.subscribe(EventType.ADJUSTMENT_BATCH_COMMITTED, _stale_engine_on_adjustment)
    event_bus.subscribe(EventType.DATA_IMPORTED, _stale_engine_on_data_imported)
    event_bus.subscribe(EventType.LEDGER_DATASET_ACTIVATED, _stale_engine_on_data_imported)
    event_bus.subscribe(EventType.WORKPAPER_SAVED, _stale_engine_on_workpaper_saved)
    event_bus.subscribe(EventType.MAPPING_CHANGED, _stale_engine_on_mapping_changed)
    logger.debug("Global Linkage Bus: stale_engine event handlers registered")

    # ------------------------------------------------------------------
    # Global Linkage Bus Sprint 3: 5 个新事件 handler（反向联动）
    # FORMULA_CONFIG_CHANGED / PREFILL_MAPPING_CHANGED / NOTE_SECTION_SAVED
    # ACCOUNT_MAPPING_CHANGED / REPORT_ROW_CHANGED
    # Validates: Requirements F9, F10, F11, F12, F13, F14, F15
    # ------------------------------------------------------------------

    async def _stale_engine_on_formula_config_changed(payload: EventPayload) -> None:
        """公式配置变更 → stale_engine.on_change（按 row_code 构建 REPORT URI）"""
        if not payload.project_id:
            return
        extra = payload.extra or {}
        row_code = extra.get("row_code", "")
        if row_code:
            uri = f"REPORT:{row_code}::"
            try:
                year = payload.year or 2025
                await stale_engine.on_change(uri, payload.project_id, year)
            except Exception as e:
                logger.warning("[stale_engine] on_formula_config_changed failed for %s: %s", uri, e)

    async def _stale_engine_on_prefill_mapping_changed(payload: EventPayload) -> None:
        """预填充映射变更 → stale_engine.on_change（标记相关底稿 stale）"""
        if not payload.project_id:
            return
        extra = payload.extra or {}
        changed_wp_codes = extra.get("changed_wp_codes", [])
        year = payload.year or 2025
        for wp_code in changed_wp_codes:
            uri = f"WP:{wp_code}::预填充"
            try:
                await stale_engine.on_change(uri, payload.project_id, year)
            except Exception as e:
                logger.warning("[stale_engine] on_prefill_mapping_changed failed for %s: %s", uri, e)

    async def _stale_engine_on_note_section_saved(payload: EventPayload) -> None:
        """附注章节保存 → stale_engine.on_change（标记引用该附注的底稿 stale）"""
        if not payload.project_id or not payload.year:
            return
        extra = payload.extra or {}
        section_code = extra.get("section_code", "")
        if section_code:
            uri = f"NOTE:{section_code}::"
            try:
                await stale_engine.on_change(uri, payload.project_id, payload.year)
            except Exception as e:
                logger.warning("[stale_engine] on_note_section_saved failed for %s: %s", uri, e)

    async def _stale_engine_on_account_mapping_changed(payload: EventPayload) -> None:
        """科目映射变更 → stale_engine.on_change（全链路 stale）"""
        if not payload.project_id:
            return
        extra = payload.extra or {}
        affected_codes = extra.get("affected_account_codes", [])
        year = payload.year or 2025
        for code in affected_codes:
            uri = f"MAPPING:{code}::"
            try:
                await stale_engine.on_change(uri, payload.project_id, year)
            except Exception as e:
                logger.warning("[stale_engine] on_account_mapping_changed failed for %s: %s", uri, e)

    async def _stale_engine_on_report_row_changed(payload: EventPayload) -> None:
        """报表行变更 → stale_engine.on_change（标记引用该行的底稿 stale）"""
        if not payload.project_id or not payload.year:
            return
        extra = payload.extra or {}
        changed_row_codes = extra.get("changed_row_codes", [])
        for row_code in changed_row_codes[:50]:  # Limit to prevent excessive BFS
            uri = f"REPORT:{row_code}::"
            try:
                await stale_engine.on_change(uri, payload.project_id, payload.year)
            except Exception as e:
                logger.warning("[stale_engine] on_report_row_changed failed for %s: %s", uri, e)

    event_bus.subscribe(EventType.FORMULA_CONFIG_CHANGED, _stale_engine_on_formula_config_changed)
    event_bus.subscribe(EventType.PREFILL_MAPPING_CHANGED, _stale_engine_on_prefill_mapping_changed)
    event_bus.subscribe(EventType.NOTE_SECTION_SAVED, _stale_engine_on_note_section_saved)
    event_bus.subscribe(EventType.ACCOUNT_MAPPING_CHANGED, _stale_engine_on_account_mapping_changed)
    event_bus.subscribe(EventType.REPORT_ROW_CHANGED, _stale_engine_on_report_row_changed)
    logger.debug("Global Linkage Bus Sprint 3: 5 new reverse-linkage event handlers registered")

    # ------------------------------------------------------------------
    # H-F8: H9→H8 租赁两表反向回填 (ADR-H5)
    # WORKPAPER_SAVED + wp_code='H9' → stale 传播到 H8 使用权资产初始计量
    # WORKPAPER_SAVED + wp_code='H8-7' → stale 传播到 H8 后续计量
    # cross_wp_references: CW-217 (H9→H8) / CW-242 (H8-7→H8)
    # Validates: Requirements H-F8.2, H-F8.3, H-F8.4, H-F8.5
    # ------------------------------------------------------------------

    # H9/H8-7 wp_code 过滤集合
    _H_LEASE_REVERSE_WP_CODES = {"H9", "H8-7"}

    async def _on_h_lease_reverse_backfill(payload: EventPayload) -> None:
        """H9/H8-7 保存 → stale_engine 沿 cross_wp_references 传播到 H8。

        触发条件（AND 关系）:
          1. event_type == WORKPAPER_SAVED
          2. payload.extra['wp_code'] in {'H9', 'H8-7'}
          3. project_id 和 year 有效

        行为:
          - H9 保存 → stale 传播到 H8 使用权资产初始计量 (CW-217)
          - H8-7 保存 → stale 传播到 H8 后续计量 (CW-242)
          - 发布 cross-ref:updated 事件通知前端刷新 H8
        """
        if not payload.extra:
            return
        wp_code = payload.extra.get("wp_code", "")
        if wp_code not in _H_LEASE_REVERSE_WP_CODES:
            return

        project_id = payload.project_id
        year = payload.year
        if not project_id or not year:
            return

        # 构建 stale URI 并传播
        sheet = payload.extra.get("sheet", "")
        uri = f"WP:{wp_code}:{sheet}:租赁回填"
        try:
            result = await stale_engine.on_change(uri, project_id, year)
            logger.debug(
                "[H-F8 lease reverse backfill] wp_code=%s project=%s "
                "affected=%d degraded=%s",
                wp_code,
                project_id,
                result.get("total", 0),
                result.get("degraded", False),
            )
        except Exception as e:
            logger.warning(
                "[H-F8 lease reverse backfill] stale propagation failed "
                "for wp_code=%s project=%s: %s",
                wp_code, project_id, e,
            )

        # 发布 cross-ref:updated 事件 → 前端 WorkpaperEditor 自动刷新 H8
        try:
            ref_id = "CW-217" if wp_code == "H9" else "CW-242"
            await event_bus.publish_immediate(
                EventPayload(
                    event_type=EventType.CROSS_REF_UPDATED,
                    project_id=project_id,
                    year=year,
                    extra={
                        "source_wp_code": wp_code,
                        "target_wp_code": "H8",
                        "ref_id": ref_id,
                        "trigger": f"workpaper:saved:{wp_code}",
                    },
                )
            )
        except Exception as e:
            logger.warning(
                "[H-F8 lease reverse backfill] cross-ref:updated publish failed: %s", e
            )

    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_h_lease_reverse_backfill)
    logger.debug("H-F8: H9/H8-7 lease reverse backfill event handler registered")

    # ------------------------------------------------------------------
    # I-F8: I6↔I2 研发费用↔开发支出反向回填 (ADR-I4)
    # WORKPAPER_SAVED + wp_code='I2' → stale 传播到 I6 资本化支出（CW-265）
    # WORKPAPER_SAVED + wp_code='I6' → stale 传播到 I2 对应费用化金额（CW-266）
    # cross_wp_references: CW-265 (I2→I6) / CW-266 (I6→I2)
    # Validates: Requirements I-F8.2, I-F8.3, I-F8.4, I-F8.5
    # ------------------------------------------------------------------

    # I2/I6 wp_code 过滤集合 + ref_id 映射（保存方 → 反向回填条目 ref_id）
    _I_RD_REVERSE_WP_CODES = {"I2", "I6"}
    _I_RD_REVERSE_REF_ID = {"I2": "CW-265", "I6": "CW-266"}
    _I_RD_REVERSE_TARGET = {"I2": "I6", "I6": "I2"}

    async def _on_i_rd_reverse_backfill(payload: EventPayload) -> None:
        """I2/I6 保存 → stale_engine 沿 cross_wp_references 双向传播。

        触发条件（AND 关系）:
          1. event_type == WORKPAPER_SAVED
          2. payload.extra['wp_code'] in {'I2', 'I6'}
          3. project_id 和 year 有效

        行为:
          - I2 保存（开发支出资本化金额变更）→ stale 传播到 I6 资本化支出 (CW-265)
          - I6 保存（研发费用费用化金额变更）→ stale 传播到 I2 对应费用化金额 (CW-266)
          - 发布 cross-ref:updated 事件通知前端刷新对方底稿
        """
        if not payload.extra:
            return
        wp_code = payload.extra.get("wp_code", "")
        if wp_code not in _I_RD_REVERSE_WP_CODES:
            return

        project_id = payload.project_id
        year = payload.year
        if not project_id or not year:
            return

        # 构建 stale URI 并传播
        sheet = payload.extra.get("sheet", "")
        uri = f"WP:{wp_code}:{sheet}:研发回填"
        try:
            result = await stale_engine.on_change(uri, project_id, year)
            logger.debug(
                "[I-F8 RD reverse backfill] wp_code=%s project=%s "
                "affected=%d degraded=%s",
                wp_code,
                project_id,
                result.get("total", 0),
                result.get("degraded", False),
            )
        except Exception as e:
            logger.warning(
                "[I-F8 RD reverse backfill] stale propagation failed "
                "for wp_code=%s project=%s: %s",
                wp_code, project_id, e,
            )

        # 发布 cross-ref:updated 事件 → 前端 WorkpaperEditor 自动刷新对方底稿
        try:
            ref_id = _I_RD_REVERSE_REF_ID[wp_code]
            target_wp = _I_RD_REVERSE_TARGET[wp_code]
            await event_bus.publish_immediate(
                EventPayload(
                    event_type=EventType.CROSS_REF_UPDATED,
                    project_id=project_id,
                    year=year,
                    extra={
                        "source_wp_code": wp_code,
                        "target_wp_code": target_wp,
                        "ref_id": ref_id,
                        "trigger": f"workpaper:saved:{wp_code}",
                    },
                )
            )
        except Exception as e:
            logger.warning(
                "[I-F8 RD reverse backfill] cross-ref:updated publish failed: %s", e
            )

    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_i_rd_reverse_backfill)
    logger.debug("I-F8: I2/I6 RD reverse backfill event handler registered")

    # ------------------------------------------------------------------
    # Sprint 2 Task 2.5: DisclosureNote 联动 — 3 新事件订阅 (R2.1)
    #
    # Spec: .kiro/specs/disclosure-note-full-revamp/ Sprint 2 Task 2.5
    # Design: D6 联动机制 EventBus 订阅表
    #
    # 现状（grep 实测）：
    #   - LEDGER_DATASET_ROLLED_BACK 已有 _mark_downstream_stale_on_rollback
    #     handler（F46/Sprint 7.22），本 spec **不动**
    #   - WORKPAPER_REVIEWED / ADJUSTMENT_APPROVED 在 EventType 中**不存在**
    #     → 改订阅最接近的现有事件：
    #       · WORKPAPER_REVIEW_PASSED  （Sprint 10 已有定义；语义最接近）
    #       · ADJUSTMENT_BATCH_COMMITTED（Enterprise Linkage Sprint 已有）
    #
    # 行为：3 个事件共用通用 stale handler — 把 project_id+year 维度
    # 全部 DisclosureNote.is_stale=True（与现有 rollback 规则一致）。
    # ------------------------------------------------------------------

    async def _mark_disclosure_notes_stale_for_project_year(
        payload: EventPayload, *, source_event: str,
    ) -> None:
        """通用 helper：把 (project_id, year) 范围内全部附注标 is_stale=True.

        与 _mark_downstream_stale_on_rollback 一致 — 写 update + commit；
        失败不阻断事件链（参考 F46 模式）。
        """
        import sqlalchemy as _sa
        from app.models.report_models import DisclosureNote

        project_id = payload.project_id
        year = payload.year
        if project_id is None or year is None:
            return
        async with async_session_factory() as session:
            try:
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
                logger.debug(
                    "[Sprint2-Task2.5/%s] DisclosureNote marked stale "
                    "for project=%s year=%s",
                    source_event, project_id, year,
                )
            except Exception:  # pragma: no cover — 失败不阻断
                await session.rollback()
                logger.warning(
                    "[Sprint2-Task2.5/%s] mark stale failed for "
                    "project=%s year=%s",
                    source_event, project_id, year,
                    exc_info=True,
                )

    async def on_event_ledger_activated(payload: EventPayload) -> None:
        """LEDGER_DATASET_ACTIVATED → 全部 DisclosureNote.is_stale=True (R2.1).

        语义：账套激活后试算表全量刷新，附注下游视为陈旧。
        """
        await _mark_disclosure_notes_stale_for_project_year(
            payload, source_event="LEDGER_DATASET_ACTIVATED",
        )

    async def on_event_workpaper_reviewed(payload: EventPayload) -> None:
        """WORKPAPER_REVIEW_PASSED → 全部 DisclosureNote.is_stale=True (R2.1).

        语义：底稿复核通过 — 审定数已变化，附注需重算（D6 表第 2 行）。
        实际订阅事件名：WORKPAPER_REVIEW_PASSED（spec 设计名 WORKPAPER_REVIEWED
        在 EventType 中不存在，订阅最接近的语义事件）。
        """
        await _mark_disclosure_notes_stale_for_project_year(
            payload, source_event="WORKPAPER_REVIEW_PASSED",
        )

    async def on_event_adjustment_approved(payload: EventPayload) -> None:
        """ADJUSTMENT_BATCH_COMMITTED → 全部 DisclosureNote.is_stale=True (R2.1).

        语义：调整分录批量提交 — 试算表+报表已变化，附注下游视为陈旧。
        实际订阅事件名：ADJUSTMENT_BATCH_COMMITTED（spec 设计名 ADJUSTMENT_APPROVED
        在 EventType 中不存在，订阅最接近的语义事件）。
        """
        await _mark_disclosure_notes_stale_for_project_year(
            payload, source_event="ADJUSTMENT_BATCH_COMMITTED",
        )

    event_bus.subscribe(EventType.LEDGER_DATASET_ACTIVATED, on_event_ledger_activated)
    event_bus.subscribe(EventType.WORKPAPER_REVIEW_PASSED, on_event_workpaper_reviewed)
    event_bus.subscribe(EventType.ADJUSTMENT_BATCH_COMMITTED, on_event_adjustment_approved)
    logger.debug(
        "Sprint 2 Task 2.5: 3 DisclosureNote stale event handlers registered "
        "(LEDGER_DATASET_ACTIVATED / WORKPAPER_REVIEW_PASSED / ADJUSTMENT_BATCH_COMMITTED)"
    )

    # ------------------------------------------------------------------
    # multi-standard-unification 需求 3：STANDARD_CHANGED → 附注层联动
    # 复用 note_conversion_service.execute_conversion 执行附注切换
    # ------------------------------------------------------------------
    async def _on_standard_changed_notes(payload: EventPayload) -> None:
        """准则切换 → 附注层自动跟随（需求 3.1/3.2/3.3）。

        复用 note_conversion_service 已验证的切换逻辑（section_id 保留 +
        共有章节不丢编辑 + soe_only 归档 / listed_only 创建）。execute_conversion
        内部已把 project.template_type 对齐到新 entity_type，使 current_standard
        与 applicable_standard_v2 保持一致（需求 3.3）。
        """
        if not payload.project_id:
            return
        new_standard = (payload.extra or {}).get("new_standard") or {}
        target_type = new_standard.get("entity_type")
        # 本 spec 只支持 SOE↔Listed 附注切换；其他 entity_type（如 private）跳过
        if target_type not in ("soe", "listed"):
            return
        year = payload.year
        if year is None:
            # 附注切换需要年度；缺失时跳过（记录 warning）
            logger.warning("STANDARD_CHANGED 缺少 year，跳过附注切换: project=%s", payload.project_id)
            return
        async with async_session_factory() as session:
            try:
                from app.services.note_conversion_service import NoteConversionService
                svc = NoteConversionService(session)
                await svc.execute_conversion(payload.project_id, year, target_type)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.warning("STANDARD_CHANGED 附注切换失败: project=%s: %s", payload.project_id, e)

    event_bus.subscribe(EventType.STANDARD_CHANGED, _on_standard_changed_notes)
    logger.debug("multi-standard-unification 需求 3: STANDARD_CHANGED → 附注切换 handler registered")

    # ------------------------------------------------------------------
    # multi-standard-unification 需求 4：STANDARD_CHANGED → 报表层联动
    # ------------------------------------------------------------------
    async def _on_standard_changed_reports(payload: EventPayload) -> None:
        """准则切换 → 报表层标记 stale（需求 4.1/4.2）。

        需求 4.1（更新 applicable_standard）：报表的 applicable_standard 是在报表
        生成时从 project.template_type + report_scope 派生的（无独立列）；set_standard
        已双写这两个字段，故派生口径在下次生成时自动更新——此处无需改报表列。
        需求 4.2：把现有报表标记为 stale（需重新生成）。
        """
        import sqlalchemy as sa
        from app.models.report_models import FinancialReport

        if not payload.project_id:
            return
        async with async_session_factory() as session:
            try:
                stmt = sa.update(FinancialReport).where(
                    FinancialReport.project_id == payload.project_id,
                    FinancialReport.is_deleted == sa.false(),
                )
                if payload.year is not None:
                    stmt = stmt.where(FinancialReport.year == payload.year)
                stmt = stmt.values(is_stale=True)
                await session.execute(stmt)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.warning("STANDARD_CHANGED 报表 stale 标记失败: project=%s: %s", payload.project_id, e)

    event_bus.subscribe(EventType.STANDARD_CHANGED, _on_standard_changed_reports)
    logger.debug("multi-standard-unification 需求 4: STANDARD_CHANGED → 报表 stale handler registered")

    # ------------------------------------------------------------------
    # report-config-baseline 需求 2.2: 主模板更新 → 克隆项目 is_stale
    # REPORT_CONFIG_MASTER_UPDATED → 查 applicable_standard LIKE 'project:%'
    # 且 report_type + row_code 匹配 → 标 is_stale=True
    # 属性 E3: 只标引用该行的克隆项目，不误标无关
    # Validates: Requirements 2.2
    # ------------------------------------------------------------------
    async def _mark_cloned_configs_stale(payload: EventPayload) -> None:
        """主模板更新 → 标记引用该行的克隆项目 report_config.is_stale=True。

        只标记 applicable_standard 以 'project:' 开头且 report_type + row_code
        与更新行匹配的克隆配置行（E3 属性：不误标无关项目）。
        """
        import sqlalchemy as sa
        from app.models.report_models import ReportConfig

        extra = payload.extra or {}
        report_type = extra.get("report_type")
        row_code = extra.get("row_code")
        if not report_type or not row_code:
            return

        async with async_session_factory() as session:
            try:
                stmt = (
                    sa.update(ReportConfig)
                    .where(
                        ReportConfig.applicable_standard.like("project:%"),
                        ReportConfig.row_code == row_code,
                        ReportConfig.is_deleted == sa.false(),
                    )
                    .values(is_stale=True)
                )
                # report_type 在 DB 中是 enum 列；payload 传来的是字符串值
                # 使用 cast 确保类型匹配
                stmt = stmt.where(
                    sa.cast(ReportConfig.report_type, sa.String) == report_type
                )
                result = await session.execute(stmt)
                await session.commit()
                logger.debug(
                    "[report-config-baseline] Marked %d cloned configs stale "
                    "for report_type=%s row_code=%s",
                    result.rowcount,
                    report_type,
                    row_code,
                )
            except Exception:
                await session.rollback()
                logger.warning(
                    "[report-config-baseline] Failed to mark cloned configs stale "
                    "for report_type=%s row_code=%s",
                    report_type,
                    row_code,
                    exc_info=True,
                )

    event_bus.subscribe(EventType.REPORT_CONFIG_MASTER_UPDATED, _mark_cloned_configs_stale)
    logger.debug("report-config-baseline 需求 2.2: REPORT_CONFIG_MASTER_UPDATED → cloned configs stale handler registered")

    # ------------------------------------------------------------------
    # deliverable-lineage-and-writeback Task 8.1/8.2:
    # 上游变更 → 标受影响出品物章节 stale + 自触发防护
    # 订阅: ADJUSTMENT_CREATED/UPDATED/DELETED, REPORTS_UPDATED, NOTE_SECTION_SAVED
    # Validates: Requirements 4.3, 4.9
    # ------------------------------------------------------------------
    async def _on_upstream_changed_mark_deliverable_stale(payload: EventPayload) -> None:
        """上游 disclosure_notes/financial_report/adjustments 变更 → 标受影响出品物章节 stale。

        自触发防护（需求 4.9）：
          若 payload.extra.get('writeback_source_deliverable_id') == 本出品物 word_export_task_id，
          则跳过该出品物（但仍标其他依赖同一附注的出品物）。

        流程：
          1. 提取变更 section_code（从 payload.extra）
          2. 反查依赖该 section_code 的出品物章节（deliverable_section_state）
          3. 对每个受影响 (word_export_task_id, section_code) 调 StalePropagationEngine
             on_change(f'DELIVERABLE:{word_export_task_id}:{section_code}', ...)
          4. 跳过 writeback_source_deliverable_id（= 来源出品物 word_export_task_id）
        """
        import sqlalchemy as _sa

        project_id = payload.project_id
        year = payload.year
        if not project_id or not year:
            return

        extra = payload.extra or {}

        # 自触发防护：获取回填来源出品物标识
        writeback_source_id = extra.get("writeback_source_deliverable_id")

        # 提取变更相关的 section_codes
        changed_section_codes: list[str] = []
        # NOTE_SECTION_SAVED 事件携带 section_code / note_section
        if extra.get("section_code"):
            changed_section_codes.append(extra["section_code"])
        elif extra.get("note_section"):
            changed_section_codes.append(extra["note_section"])

        # 如果没有具体 section_code（如 REPORTS_UPDATED / 调整分录变更），
        # 查找项目下所有有状态记录的出品物章节
        async with async_session_factory() as session:
            try:
                if changed_section_codes:
                    # 精确匹配：反查依赖该 section_code 的出品物章节
                    stmt = _sa.text(
                        "SELECT word_export_task_id, section_code "
                        "FROM deliverable_section_state "
                        "WHERE project_id = :pid AND year = :year "
                        "AND section_code = ANY(:codes) "
                        "AND is_stale = false"
                    )
                    result = await session.execute(
                        stmt,
                        {"pid": str(project_id), "year": year, "codes": changed_section_codes},
                    )
                else:
                    # 广泛匹配：标记项目下所有出品物章节为 stale
                    stmt = _sa.text(
                        "SELECT word_export_task_id, section_code "
                        "FROM deliverable_section_state "
                        "WHERE project_id = :pid AND year = :year "
                        "AND is_stale = false"
                    )
                    result = await session.execute(
                        stmt,
                        {"pid": str(project_id), "year": year},
                    )

                affected_rows = result.fetchall()

                if not affected_rows:
                    return

                # 过滤自触发：跳过 writeback_source_deliverable_id
                from app.services.stale_propagation_engine import stale_engine

                marked_count = 0
                for row in affected_rows:
                    wid = str(row[0])
                    sc = row[1]

                    # 自触发防护：来源出品物不标自身 stale（需求 4.9）
                    if writeback_source_id and str(writeback_source_id) == wid:
                        continue

                    # 调 StalePropagationEngine 标 stale（直接走 _mark_stale_by_uri 而非 on_change，
                    # 因为 on_change 会 BFS 依赖图——DELIVERABLE 节点通常不在图中，直接标即可）
                    uri = f"DELIVERABLE:{wid}:{sc}"
                    await stale_engine._mark_stale_by_uri([uri], project_id, year)
                    marked_count += 1

                # SSE 推送给前端
                if marked_count > 0:
                    affected_uris = [
                        f"DELIVERABLE:{row[0]}:{row[1]}"
                        for row in affected_rows
                        if not (writeback_source_id and str(writeback_source_id) == str(row[0]))
                    ]
                    await stale_engine._notify_frontend(project_id, affected_uris)

                logger.info(
                    "[deliverable-stale] Marked %d deliverable sections stale "
                    "(project=%s, event=%s, skipped_source=%s)",
                    marked_count,
                    project_id,
                    payload.event_type.value,
                    writeback_source_id or "none",
                )
            except Exception as e:
                await session.rollback()
                logger.warning(
                    "[deliverable-stale] Failed to mark deliverable sections stale: %s",
                    e,
                )

    # 订阅调整分录变更事件
    event_bus.subscribe(EventType.ADJUSTMENT_CREATED, _on_upstream_changed_mark_deliverable_stale)
    event_bus.subscribe(EventType.ADJUSTMENT_UPDATED, _on_upstream_changed_mark_deliverable_stale)
    event_bus.subscribe(EventType.ADJUSTMENT_DELETED, _on_upstream_changed_mark_deliverable_stale)
    # 订阅报表更新事件
    event_bus.subscribe(EventType.REPORTS_UPDATED, _on_upstream_changed_mark_deliverable_stale)
    # 订阅附注章节保存事件
    event_bus.subscribe(EventType.NOTE_SECTION_SAVED, _on_upstream_changed_mark_deliverable_stale)

    logger.debug("deliverable-lineage-and-writeback: upstream change → deliverable stale handlers registered")

    # 启动汇总（只打这一行 INFO）
    total_handlers = sum(len(h) for h in event_bus._handlers.values())
    logger.info("[EventBus] %d handlers registered across %d event types", total_handlers, len(event_bus._handlers))
