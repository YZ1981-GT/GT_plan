"""衔接2 — 抵销分录审批 → worksheet + trial 事件驱动重算.

监听 ELIMINATION_APPROVED 事件：当某笔抵销分录被审批（→approved）时，
触发该合并项目当年的 worksheet 全量重算 + trial 重算，使两条计算路径
都纳入这笔已审批抵销（口径统一为 APPROVED）。

设计定位（关联 设计 §三 组件3 / ADR-CONSOL-102 / EH3）：
- 重算与审批解耦：审批本身已同步落库（含审计留痕），重算是下游派生动作。
- 重算失败记 error 日志但**不抛**（不阻断审批，幂等可重试，关联 EH3）。
- 幂等：同一笔抵销重复触发 ELIMINATION_APPROVED，recalc_full / recalculate_trial
  都是"全量重算覆盖写"，结果不变（关联属性 Q4）。

主要 API:
- handle_elimination_approved(event) — EventBus handler
- register_consol_elimination_recalc_handler(event_bus) — 注册到 EventBus
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handle_elimination_approved(event: Any) -> None:
    """处理抵销分录审批事件 → 触发 worksheet + trial 重算.

    event 字段：
      - project_id: UUID  合并母项目 ID
      - year: int

    重算顺序：先 worksheet（recalc_full），再 trial（recalculate_trial，
    含 Phase 0 B1 individual_sum 汇总 + APPROVED 抵销叠加）。
    任一步失败记 error，不抛（审批已落库，EH3）。
    """
    project_id = getattr(event, "project_id", None)
    year = getattr(event, "year", None)

    if not project_id or not year:
        logger.debug("handle_elimination_approved: missing project_id or year")
        return

    try:
        from app.core.database import async_session as async_session_factory
        from app.services.consol_worksheet_engine import recalc_full
        from app.services.consol_trial_service import recalculate_trial

        async with async_session_factory() as db:
            # ① worksheet 全量重算（后序遍历，消费 APPROVED 抵销）
            try:
                await recalc_full(db, project_id, year)
            except Exception as ws_err:
                logger.error(
                    "ELIMINATION_APPROVED → recalc_full 失败 (项目 %s 年度 %s): %s",
                    project_id, year, ws_err,
                )

            # ② trial 重算（individual_sum 汇总 + APPROVED 抵销叠加）
            try:
                await recalculate_trial(db, project_id, year)
                await db.commit()
            except Exception as trial_err:
                await db.rollback()
                logger.error(
                    "ELIMINATION_APPROVED → recalculate_trial 失败 (项目 %s 年度 %s): %s",
                    project_id, year, trial_err,
                )
                return

            logger.info(
                "抵销审批 → 重算完成 (项目 %s 年度 %s): worksheet + trial",
                project_id, year,
            )

    except Exception as err:
        # 顶层兜底：重算故障绝不阻断审批本身（EH3）
        logger.error(
            "handle_elimination_approved failed for project %s: %s",
            project_id, err,
        )


def register_consol_elimination_recalc_handler(event_bus: Any) -> None:
    """注册抵销审批重算 handler 到 EventBus（监听 ELIMINATION_APPROVED）。

    在应用启动时调用（main._register_phase_handlers）。
    """
    try:
        from app.models.audit_platform_schemas import EventType

        event_bus.subscribe(EventType.ELIMINATION_APPROVED, handle_elimination_approved)
        logger.info(
            "Registered consol_elimination_recalc_handler for ELIMINATION_APPROVED events"
        )
    except Exception as err:
        logger.warning("Failed to register consol_elimination_recalc_handler: %s", err)
