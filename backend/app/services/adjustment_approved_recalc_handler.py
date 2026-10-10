"""调整分录审批与撤回复核后的试算表重算 handler。

监听 ``ADJUSTMENT_APPROVED`` 和 ``ADJUSTMENT_REVIEW_REVOKED``：两者都重算
受影响科目的调整列与审定数，但向 ``TRIAL_BALANCE_UPDATED`` 写入不同的
``extra.trigger``，让历史和下游审计追踪能区分审批与撤回。

设计定位（EH3）：审批状态已经提交后，下游派生失败只记录日志，不反向阻断
审批；重算可由同一事件再次触发，结果按科目覆盖写，满足幂等性。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def _handle_adjustment_review_event(
    event: Any,
    *,
    trigger: str,
    event_label: str,
) -> None:
    """执行审批/撤回共用的调整列和审定数重算。"""
    project_id = getattr(event, "project_id", None)
    year = getattr(event, "year", None)
    account_codes = getattr(event, "account_codes", None)

    if not project_id or not year:
        logger.debug("%s: missing project_id or year", event_label)
        return

    try:
        from app.core.database import async_session as async_session_factory
        from app.services.trial_balance_service import TrialBalanceService

        async with async_session_factory() as db:
            svc = TrialBalanceService(db)

            try:
                await svc.recalc_adjustments(
                    project_id, year, account_codes=account_codes
                )
            except Exception as adj_err:
                logger.error(
                    "%s -> recalc_adjustments 失败 (项目 %s 年度 %s): %s",
                    event_label,
                    project_id,
                    year,
                    adj_err,
                )

            try:
                await svc.recalc_audited(
                    project_id, year, account_codes=account_codes
                )
                await db.commit()
            except Exception as aud_err:
                await db.rollback()
                logger.error(
                    "%s -> recalc_audited 失败 (项目 %s 年度 %s): %s",
                    event_label,
                    project_id,
                    year,
                    aud_err,
                )
                return

            try:
                from app.models.audit_platform_schemas import EventPayload, EventType
                from app.schemas.consol_context import ConsolContext
                from app.services.event_bus import event_bus

                await event_bus.publish(EventPayload(
                    event_type=EventType.TRIAL_BALANCE_UPDATED,
                    project_id=project_id,
                    year=year,
                    account_codes=account_codes,
                    extra={"trigger": trigger},
                    context=ConsolContext.legacy(
                        project_id=project_id,
                        year=year,
                        source_version=trigger,
                    ),
                ))
            except Exception as pub_err:
                logger.warning(
                    "%s -> TRIAL_BALANCE_UPDATED 发布失败: %s",
                    event_label,
                    pub_err,
                )

            logger.info(
                "%s -> 重算完成 (项目 %s 年度 %s): adjustments + audited, accounts=%s",
                event_label,
                project_id,
                year,
                account_codes,
            )

    except Exception as err:
        logger.error(
            "%s handler failed for project %s: %s",
            event_label,
            project_id,
            err,
        )


async def handle_adjustment_approved(event: Any) -> None:
    """处理调整分录审批通过事件。"""
    await _handle_adjustment_review_event(
        event,
        trigger="adjustment_approved",
        event_label="ADJUSTMENT_APPROVED",
    )


async def handle_adjustment_review_revoked(event: Any) -> None:
    """处理调整分录撤回复核事件。"""
    await _handle_adjustment_review_event(
        event,
        trigger="adjustment_review_revoked",
        event_label="ADJUSTMENT_REVIEW_REVOKED",
    )


def register_adjustment_approved_recalc_handler(event_bus: Any) -> None:
    """注册审批和撤回复核的重算 handler 到 EventBus。"""
    try:
        from app.models.audit_platform_schemas import EventType

        event_bus.subscribe(EventType.ADJUSTMENT_APPROVED, handle_adjustment_approved)
        event_bus.subscribe(
            EventType.ADJUSTMENT_REVIEW_REVOKED,
            handle_adjustment_review_revoked,
        )
        logger.info(
            "Registered adjustment review recalc handlers for approval and revoke events"
        )
    except Exception as err:
        logger.warning("Failed to register adjustment review recalc handlers: %s", err)
