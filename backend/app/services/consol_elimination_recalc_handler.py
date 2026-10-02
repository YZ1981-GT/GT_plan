"""衔接2 — 抵销分录审批 / 撤销审批 → 合并推送（事件驱动）.

监听 ELIMINATION_APPROVED / ELIMINATION_REVOKED：分录审批通过或撤销审批后，对分录所在合并项目
及其全部上层合并项目依次重算差额表 → 合并试算 → 生成合并报表 → 标记合并附注待更新
（spec consol-elimination-single-source-push 需求 8.1 / 8.2，``consol_push_service.push``）。

设计定位（关联 设计 §三 组件3 / ADR-CONSOL-102 / EH3）：
- 推送与审批解耦：审批本身已同步落库（含审计留痕），推送是下游派生动作。
- 推送失败记失败运行（``consol_push_run``）+ SSE ``consol.push_failed``，**不抛**（不阻断审批，EH3）。
- 幂等：重复触发时 recalc_full / recalculate_trial / 报表生成都是「全量重算覆盖写」，结果不变（属性 Q4）。
- 函数名与注册点沿用旧版（``handle_elimination_approved``），旧测试按真实调用验证前两步仍被调用。

主要 API:
- handle_elimination_approved(event) — EventBus handler（审批）
- handle_elimination_revoked(event) — EventBus handler（撤销审批）
- register_consol_elimination_recalc_handler(event_bus) — 注册到 EventBus
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def _push(project_id: Any, year: Any, trigger: str) -> None:
    if not project_id or not year:
        logger.debug("合并推送事件缺 project_id 或 year，跳过（trigger=%s）", trigger)
        return
    try:
        from app.core.database import async_session as async_session_factory
        from app.services.consol_push_service import push

        async with async_session_factory() as db:
            result = await push(db, project_id, year, trigger=trigger)
        logger.info("分录%s → 合并推送 %s（项目 %s 年度 %s）", trigger, result.status, project_id, year)
    except Exception as err:
        # 顶层兜底：推送故障绝不阻断审批本身（EH3）；push 内部已落失败运行
        logger.error("合并推送事件处理失败（项目 %s 年度 %s）：%s", project_id, year, err)


async def handle_elimination_approved(event: Any) -> None:
    """分录审批通过 → 合并推送（本项目 + 上层合并项目，自下而上）。

    event 字段：project_id（合并项目 ID）、year（发布方漏传时 EventBus 按项目审计年度补齐）。
    """
    from app.services.consol_push_service import TRIGGER_APPROVED

    await _push(getattr(event, "project_id", None), getattr(event, "year", None), TRIGGER_APPROVED)


async def handle_elimination_revoked(event: Any) -> None:
    """撤销审批（已审批 → 草稿）→ 合并推送：合并数回到审批前（P8）。

    event 字段：project_id（合并项目 ID）、year（发布方漏传时 EventBus 按项目审计年度补齐）。
    """
    from app.services.consol_push_service import TRIGGER_REVOKED

    await _push(getattr(event, "project_id", None), getattr(event, "year", None), TRIGGER_REVOKED)


def register_consol_elimination_recalc_handler(event_bus: Any) -> None:
    """注册分录审批 / 撤销审批 → 合并推送 handler（在应用启动时调用，main._register_phase_handlers）。"""
    try:
        from app.models.audit_platform_schemas import EventType

        event_bus.subscribe(EventType.ELIMINATION_APPROVED, handle_elimination_approved)
        event_bus.subscribe(EventType.ELIMINATION_REVOKED, handle_elimination_revoked)
        logger.info("Registered consol push handlers for ELIMINATION_APPROVED / ELIMINATION_REVOKED events")
    except Exception as err:
        logger.warning("Failed to register consol_elimination_recalc_handler: %s", err)
