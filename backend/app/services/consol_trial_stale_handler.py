"""P1 — 子公司试算表更新 → 母公司合并 trial stale 标记.

监听 TRIAL_BALANCE_UPDATED 事件：当某子公司 trial_balance 审定数变更时，
反向查找其所有 parent 合并项目，把对应 consol_trial 行标记 is_stale=true。

设计定位：stale 是**观测/提示**机制，不自动重算（用户决定何时重算）。
前端据 is_stale 显示"子公司数据已更新，建议重新汇总"提示 + 重算入口。
合并重算（recalculate_trial）执行后会把 is_stale 清零。

主要 API:
- handle_child_tb_updated(event) — EventBus handler
- mark_consol_trial_stale(parent_project_id, year, db) — 标记某母项目 trial stale
- register_consol_trial_stale_handler(event_bus) — 注册到 EventBus

复用 consol_note_stale_handler._find_consol_parents 的反向查找逻辑（递归向上）。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


async def handle_child_tb_updated(event: Any) -> None:
    """处理子公司试算表更新事件.

    当子公司 trial_balance 审定数变更（TRIAL_BALANCE_UPDATED）时：
    1. 反向查找该项目的所有 parent 合并项目（递归向上，含多级）
    2. 把每个 parent 的 consol_trial 行标记 is_stale=true

    event 字段：
      - project_id: UUID  发生变更的项目 ID（可能是子公司，也可能是母公司本身）
      - year: int

    注：若该项目无 parent（本身是顶层单体或非合并项目），_find_consol_parents
    返回空，handler 静默返回，不产生副作用。
    """
    project_id = getattr(event, "project_id", None)
    year = getattr(event, "year", None)

    if not project_id or not year:
        logger.debug("handle_child_tb_updated: missing project_id or year")
        return

    try:
        from app.core.database import async_session as async_session_factory
        # 复用附注 stale handler 的 parent 反向查找（递归向上）
        from app.services.consol_note_stale_handler import _find_consol_parents

        async with async_session_factory() as db:
            parents = await _find_consol_parents(project_id, db)
            if not parents:
                return

            total = 0
            for parent_id in parents:
                total += await mark_consol_trial_stale(parent_id, year, db)
            await db.commit()

            if total > 0:
                logger.info(
                    "子公司 TB 变更(项目 %s)→ 标记 %d 个合并项目 trial stale",
                    project_id, len(parents),
                )

    except Exception as err:
        logger.warning(
            "handle_child_tb_updated failed for project %s: %s", project_id, err
        )


async def mark_consol_trial_stale(
    parent_project_id: UUID,
    year: int,
    db: Any,
) -> int:
    """把某合并项目当年的 consol_trial 行标记 is_stale=true.

    Args:
        parent_project_id: 合并母项目 ID
        year: 年度
        db: AsyncSession

    Returns:
        标记为 stale 的行数（0 表示该母项目当年无 trial 行）
    """
    try:
        from sqlalchemy import text

        result = await db.execute(
            text(
                "UPDATE consol_trial SET is_stale = true "
                "WHERE project_id = :pid AND year = :year "
                "AND is_deleted = false AND is_stale = false"
            ),
            {"pid": str(parent_project_id), "year": year},
        )
        count = result.rowcount or 0
        if count > 0:
            logger.info(
                "Marked %d consol_trial rows stale for project %s year %s",
                count, parent_project_id, year,
            )
        return count
    except Exception as err:
        logger.warning("mark_consol_trial_stale failed: %s", err)
        return 0


def register_consol_trial_stale_handler(event_bus: Any) -> None:
    """注册 consol trial stale handler 到 EventBus（监听 TRIAL_BALANCE_UPDATED）。

    在应用启动时调用。
    """
    try:
        from app.models.audit_platform_schemas import EventType

        event_bus.subscribe(EventType.TRIAL_BALANCE_UPDATED, handle_child_tb_updated)
        logger.info(
            "Registered consol_trial_stale_handler for TRIAL_BALANCE_UPDATED events"
        )
    except Exception as err:
        logger.warning("Failed to register consol_trial_stale_handler: %s", err)
