"""衔接 — 调整分录审批 → TB 调整列 + 审定数事件驱动重算.

spec: adj-formula-repair-and-approval-gate-wiring · 设计 §三 组件 3
照搬 consol_elimination_recalc_handler.py 结构。

监听 ADJUSTMENT_APPROVED 事件：当调整分录被审批（→approved）时，
触发该项目当年受影响科目的 TB 调整列重算 + 审定数重算。

设计定位（ADR-ADJ-003 / EH3）：
- 重算与审批解耦：审批本身已同步落库（含审计留痕），重算是下游派生动作。
- 重算失败记 error 日志但**不抛**（不阻断审批，幂等可重试）。
- 幂等：同一笔分录重复触发，recalc_adjustments + recalc_audited
  都是按科目覆盖写，结果不变（属性 P8）。

主要 API:
- handle_adjustment_approved(event) — EventBus handler
- register_adjustment_approved_recalc_handler(event_bus) — 注册到 EventBus
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handle_adjustment_approved(event: Any) -> None:
    """处理调整分录审批事件 → 触发 TB 调整列 + 审定数重算.

    event 字段（EventPayload）：
      - project_id: UUID
      - year: int
      - account_codes: list[str]  受影响科目

    重算顺序：先 recalc_adjustments（调整列），再 recalc_audited（审定数）。
    按 account_codes 增量（非全量），防事件风暴。
    任一步失败记 error，不抛（审批已落库，EH3）。
    """
    project_id = getattr(event, "project_id", None)
    year = getattr(event, "year", None)
    account_codes = getattr(event, "account_codes", None)

    if not project_id or not year:
        logger.debug("handle_adjustment_approved: missing project_id or year")
        return

    try:
        from app.core.database import async_session as async_session_factory
        from app.services.trial_balance_service import TrialBalanceService

        async with async_session_factory() as db:
            svc = TrialBalanceService(db)

            # ① 调整列重算（按科目增量）
            try:
                await svc.recalc_adjustments(
                    project_id, year, account_codes=account_codes
                )
            except Exception as adj_err:
                logger.error(
                    "ADJUSTMENT_APPROVED → recalc_adjustments 失败 (项目 %s 年度 %s): %s",
                    project_id, year, adj_err,
                )

            # ② 审定数重算
            try:
                await svc.recalc_audited(
                    project_id, year, account_codes=account_codes
                )
                await db.commit()
            except Exception as aud_err:
                await db.rollback()
                logger.error(
                    "ADJUSTMENT_APPROVED → recalc_audited 失败 (项目 %s 年度 %s): %s",
                    project_id, year, aud_err,
                )
                return

            # ③ 发布 TRIAL_BALANCE_UPDATED，驱动下游链路
            try:
                from app.models.audit_platform_schemas import EventPayload, EventType
                from app.services.event_bus import event_bus

                await event_bus.publish(EventPayload(
                    event_type=EventType.TRIAL_BALANCE_UPDATED,
                    project_id=project_id,
                    year=year,
                    account_codes=account_codes,
                    extra={"trigger": "adjustment_approved"},
                ))
            except Exception as pub_err:
                logger.warning(
                    "ADJUSTMENT_APPROVED → TRIAL_BALANCE_UPDATED 发布失败: %s", pub_err
                )

            logger.info(
                "调整分录审批 → 重算完成 (项目 %s 年度 %s): adjustments + audited, accounts=%s",
                project_id, year, account_codes,
            )

    except Exception as err:
        # 顶层兜底：重算故障绝不阻断审批本身（EH3）
        logger.error(
            "handle_adjustment_approved failed for project %s: %s",
            project_id, err,
        )


def register_adjustment_approved_recalc_handler(event_bus: Any) -> None:
    """注册调整分录审批重算 handler 到 EventBus（监听 ADJUSTMENT_APPROVED）。

    在应用启动时调用（main._register_phase_handlers）。
    """
    try:
        from app.models.audit_platform_schemas import EventType

        event_bus.subscribe(EventType.ADJUSTMENT_APPROVED, handle_adjustment_approved)
        logger.info(
            "Registered adjustment_approved_recalc_handler for ADJUSTMENT_APPROVED events"
        )
    except Exception as err:
        logger.warning("Failed to register adjustment_approved_recalc_handler: %s", err)
