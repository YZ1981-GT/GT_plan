"""Sprint B.0.6 — 子公司单体附注更新 → 合并附注 stale 标记.

监听 NOTE_SECTION_UPDATED 事件，找到 parent 合并项目，
标对应章节 is_stale=True。

主要 API:
- handle_child_note_updated(event) — EventBus handler
- mark_consol_sections_stale(parent_project_id, section_id, year, db)
- register_stale_handler(event_bus) — 注册到 EventBus

Validates: Requirements D12.4
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 事件处理器
# ---------------------------------------------------------------------------


async def handle_child_note_updated(event: Any) -> None:
    """处理子公司单体附注更新事件.

    当子公司单体附注某章节被更新时：
    1. 检查该项目是否有 parent 合并项目
    2. 如果有，标记 parent 合并项目对应章节为 stale

    event 字段：
      - project_id: UUID  子公司项目 ID
      - year: int
      - extra.section_id: str  更新的章节 ID
    """
    project_id = getattr(event, "project_id", None)
    year = getattr(event, "year", None)
    extra = getattr(event, "extra", None) or {}
    section_id = extra.get("section_id") or extra.get("note_section")

    if not project_id or not year:
        logger.debug("handle_child_note_updated: missing project_id or year")
        return

    try:
        from app.core.database import async_session as async_session_factory

        async with async_session_factory() as db:
            # 查找 parent 合并项目
            parents = await _find_consol_parents(project_id, db)
            if not parents:
                return

            for parent_id in parents:
                await mark_consol_sections_stale(
                    parent_project_id=parent_id,
                    section_id=section_id,
                    year=year,
                    db=db,
                )
            await db.commit()

    except Exception as err:
        logger.warning(
            "handle_child_note_updated failed for project %s: %s",
            project_id, err,
        )


async def mark_consol_sections_stale(
    parent_project_id: UUID,
    section_id: str | None,
    year: int,
    db: Any,
) -> int:
    """标记合并项目对应章节为 stale.

    Args:
        parent_project_id: 合并项目 ID
        section_id: 子公司更新的章节 ID（None 则标全部）
        year: 年度
        db: AsyncSession

    Returns:
        标记为 stale 的章节数
    """
    try:
        from sqlalchemy import text

        if section_id:
            # 标记对应章节
            result = await db.execute(
                text(
                    "UPDATE disclosure_notes SET is_stale = true "
                    "WHERE project_id = :pid AND year = :year "
                    "AND is_deleted = false "
                    "AND (section_id = :sid OR "
                    "     template_lineage::text LIKE :pattern)"
                ),
                {
                    "pid": str(parent_project_id),
                    "year": year,
                    "sid": section_id,
                    "pattern": f"%{section_id}%",
                },
            )
        else:
            # 无具体章节信息，标全部
            result = await db.execute(
                text(
                    "UPDATE disclosure_notes SET is_stale = true "
                    "WHERE project_id = :pid AND year = :year "
                    "AND is_deleted = false"
                ),
                {"pid": str(parent_project_id), "year": year},
            )

        count = result.rowcount or 0
        if count > 0:
            logger.info(
                "Marked %d sections stale for consol project %s (trigger: %s)",
                count, parent_project_id, section_id,
            )
        return count

    except Exception as err:
        logger.warning("mark_consol_sections_stale failed: %s", err)
        return 0


def register_stale_handler(event_bus: Any) -> None:
    """注册 stale handler 到 EventBus.

    在应用启动时调用，监听 NOTE_UPDATED 事件。
    """
    try:
        from app.models.audit_platform_schemas import EventType

        event_bus.subscribe(EventType.NOTE_UPDATED, handle_child_note_updated)
        logger.info("Registered consol_note_stale_handler for NOTE_UPDATED events")
    except Exception as err:
        logger.warning("Failed to register stale handler: %s", err)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


async def _find_consol_parents(
    project_id: UUID,
    db: Any,
) -> list[UUID]:
    """查找消费该子公司的所有 parent 合并项目.

    通过 parent_project_id 反向查找。
    """
    try:
        from sqlalchemy import text

        # 查找直接 parent
        result = await db.execute(
            text(
                "SELECT parent_project_id FROM projects "
                "WHERE id = :pid AND is_deleted = false "
                "AND parent_project_id IS NOT NULL"
            ),
            {"pid": str(project_id)},
        )
        row = result.first()
        if row and row[0]:
            parent_id = UUID(str(row[0])) if isinstance(row[0], str) else row[0]
            # 递归向上查找所有合并层级
            parents = [parent_id]
            grandparents = await _find_consol_parents(parent_id, db)
            parents.extend(grandparents)
            return parents
    except Exception as err:
        logger.debug("_find_consol_parents error: %s", err)

    return []
