"""推送写入附注后自动执行附注公式（spec note-table-structure-formula-pull-closure R20 / ADR-15）。

公式推送只写主表审定金额；同一张表的合计、账面价值、比例/损失率与用户公式原先要等用户点「刷新」
才跟着变。这里在推送**提交后**对本次写入的附注章节执行一次附注公式（与刷新链路同一函数
``_apply_note_formulas``：逐章节保存点、只写自动格、底稿投影表只补空格），再提交。

接在最新 ``formula_push.persistence.execute_and_commit`` 的统一提交边界内，以回调形式
在领域通知（``notify_committed``）**之前**执行。

调用方：试算表/底稿保存事件（``triggers._push``）、公式配置变更传播、推送页「立即推送」、
采纳公式值。刷新链路（``note_workpaper_pull_service``）显式 opt-out（自己最后执行公式）。
失败只记日志、不影响已提交的推送。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["recalc_pushed_notes"]


async def recalc_pushed_notes(db: Any, result: Any) -> dict[str, dict[str, Any]]:
    """对推送结果里写入的附注章节执行附注公式并提交。

    dry_run、没有运行记录、没写附注 → 不做事返回 ``{}``。
    """
    if result is None or getattr(result, "dry_run", False) or getattr(result, "run_id", None) is None:
        return {}
    sections = sorted({str(s) for s in (getattr(result, "note_sections", None) or []) if s})
    if not sections:
        return {}
    from app.services.note_workpaper_pull_service import _apply_note_formulas

    try:
        runs = await _apply_note_formulas(db, result.project_id, result.year, sections)
        await db.commit()
    except Exception:  # noqa: BLE001 — 推送已提交；附注公式失败不回滚推送
        await db.rollback()
        logger.warning(
            "formula_push: 推送后附注公式执行失败 project=%s sections=%s",
            getattr(result, "project_id", None), sections, exc_info=True,
        )
        return {}
    updated = sum(int((r or {}).get("updated") or 0) for r in runs.values())
    if updated:
        logger.info(
            "formula_push: 推送后附注公式更新 %s 格 project=%s sections=%s",
            updated, result.project_id, sections,
        )
    return runs
