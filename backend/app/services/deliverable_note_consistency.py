"""附注导出前一致性检查（deliverable-writeback-and-online-edit-integrity Phase D / US-4）。

方向裁定（2026-10-17 用户确认）：附注唯一权威源是底稿披露表的单项推送（底稿 → 附注），交付中心是只读下游。
因此交付中心**不回写附注**，改为导出前比对「附注模块当前内容」与「底稿披露表应推送内容」，列出不一致章节让用户
确认或先去同步。

判定不新造：直接复用 ``note_readiness_service.build_readiness`` 的两类信号——
- ``needs_sync``：有对应底稿披露表（note_workpaper_sync_registry）但 ``last_sync_at`` 为空 ⇒ 从未同步到附注；
- ``is_stale``：上游变更后被标记过期、附注未刷新。

fail-open：看板查询异常时返回 ``consistent=True``（不因看板故障阻断已完成的编制）。
看板在保存点内执行并始终回滚到保存点（只读），内部吞掉的语句失败不会让调用方的事务进入 aborted。
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def check_note_consistency(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    selected_sections: list[str] | None = None,
) -> dict[str, Any]:
    """返回附注与底稿的一致性结论。

    Returns::

        {
          "consistent": bool,
          "never_synced": [{"note_section", "section_title", "wp_codes", "wp_ids", "wp_sheet"}...],
          "stale": [{"note_section", "section_title"}...],
        }

    ``selected_sections`` 非空时只看选中章节（与导出范围一致）。
    """
    try:
        from app.services.note_readiness_service import build_readiness

        # 🔴 只读看板放进保存点，且无论成败都回滚到保存点。build_readiness 内部有几处「查询失败即吞掉」
        #    （最近校验结果 / 底稿 id 反查 / 公式灰度）—— PG 上任一语句失败都会让整个事务进入 aborted，
        #    吞掉异常也救不回来：调用方随后的导出写入全部失败，「fail-open」实际是 fail-500。
        #    回滚到保存点在 aborted 状态下照样可执行，才真正不影响调用方的事务。
        savepoint = await db.begin_nested()
        try:
            data = await build_readiness(db, project_id, year)
        finally:
            await savepoint.rollback()
    except Exception as err:  # noqa: BLE001 — 看板故障不得阻断导出
        logger.warning("note consistency check skipped (fail-open): %s", err)
        return {"consistent": True, "never_synced": [], "stale": []}

    sections = data.get("sections") or []
    if selected_sections:
        picked = {str(s) for s in selected_sections}
        sections = [s for s in sections if s.get("note_section") in picked]

    never_synced = [
        {
            "note_section": s.get("note_section"),
            "section_title": s.get("section_title") or "",
            "wp_codes": s.get("wp_codes") or [],
            "wp_ids": s.get("wp_ids") or {},
            "wp_sheet": s.get("wp_sheet"),
        }
        for s in sections
        if s.get("needs_sync")
    ]
    stale = [
        {"note_section": s.get("note_section"), "section_title": s.get("section_title") or ""}
        for s in sections
        if s.get("is_stale")
    ]

    return {
        "consistent": not never_synced and not stale,
        "never_synced": never_synced,
        "stale": stale,
    }


__all__ = ["check_note_consistency"]
