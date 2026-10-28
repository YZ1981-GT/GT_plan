"""Sprint B.0.6 — 子公司单体附注更新 → 合并附注 stale 标记.

两个订阅：
- NOTE_UPDATED → ``handle_child_note_updated``：旧 V2 口径（合并附注存 disclosure_notes，
  按 parent_project_id 找上级），标 disclosure_notes.is_stale；
- NOTE_SECTION_SAVED → ``_on_note_section_saved_mark_consol_stale``：明细映射口径（合并附注
  存 consol_note_data，按明细映射绑定找用到该企业该章节的合并章节），标 consol_note_data.is_stale。

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
            # 6A.1：标记母项目 stale 后发 SSE 事件，合并页实时感知（ADR-CONSOL-304）
            # 复用既有 SSE 基础设施（broadcast_raw），不新增轮询（呼应 Phase 2 R5 打爆 pool 教训）
            _emit_consol_note_stale(parent_project_id, year, section_id, count)
        return count

    except Exception as err:
        logger.warning("mark_consol_sections_stale failed: %s", err)
        return 0


def _emit_consol_note_stale(
    parent_project_id: UUID,
    year: int,
    section_id: str | None,
    count: int,
) -> None:
    """广播 consol.note_stale SSE 事件（合并页 F5 实时感知，ADR-CONSOL-304）。

    走 event_bus.broadcast_raw（轻量、同步）推 SSE；无 event_bus / 无 event loop 时
    静默回退到 logger，不阻断业务（下次进合并页读最新 stale 态兜底）。
    """
    try:
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw(
            "consol.note_stale",
            {
                "project_id": str(parent_project_id),
                "year": year,
                "section_id": section_id,
                "stale_count": count,
            },
        )
    except Exception as exc:  # pragma: no cover - 兜底，不阻断业务
        logger.debug("broadcast consol.note_stale failed (non-blocking): %s", exc)


def register_stale_handler(event_bus: Any) -> None:
    """注册 stale handler 到 EventBus.

    在应用启动时调用，监听 NOTE_UPDATED 事件。
    """
    try:
        from app.models.audit_platform_schemas import EventType

        event_bus.subscribe(EventType.NOTE_UPDATED, handle_child_note_updated)
        # 子企业单体附注章节保存 → 用到它的合并附注章节标 stale（经明细映射绑定定位）
        event_bus.subscribe(EventType.NOTE_SECTION_SAVED, _on_note_section_saved_mark_consol_stale)
        logger.info("Registered consol_note_stale_handler for NOTE_UPDATED + NOTE_SECTION_SAVED events")
    except Exception as err:
        logger.warning("Failed to register stale handler: %s", err)


async def _on_note_section_saved_mark_consol_stale(event: Any) -> None:
    """NOTE_SECTION_SAVED → 用到该子企业该章节的合并附注标 stale。

    合并附注从子企业单体附注拉数靠明细映射绑定（``consol_note_mapping_binding``），受影响
    范围就按绑定找，不靠 ``parent_project_id``（企业树已改按三码推导）：

    1. 把该企业绑定为来源的合并项目 + 合并章节；
    2. 合并章节经章节映射换算成单体章节号，与本次保存的章节一致才算受影响；事件没带
       章节号（如整本生成）时该企业全部已绑定章节都受影响；
    3. 交 ``consol_note_value_change_service.on_note_section_saved`` 标 is_stale；
    4. 每个受影响的合并项目推一条 ``consol.note_stale`` SSE。
    """
    project_id = getattr(event, "project_id", None)
    year = getattr(event, "year", None)
    extra = getattr(event, "extra", None) or {}
    if not project_id or not year:
        return
    try:
        entity_project_id = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    except (TypeError, ValueError):
        return
    saved = extra.get("section_code") or extra.get("note_section") or extra.get("section_id")

    try:
        from app.core.database import async_session as async_session_factory
        from app.services.consol_note_value_change_service import on_note_section_saved

        stale_by_project: dict[UUID, int] = {}
        async with async_session_factory() as db:
            note_section, section_title = await _resolve_saved_note_section(db, entity_project_id, year, saved)
            affected = await _affected_consol_sections(db, entity_project_id, note_section, section_title)
            for section_id, consol_pids in affected.items():
                result = await on_note_section_saved(
                    db, entity_project_id=entity_project_id, section_id=section_id,
                    year=year, consol_project_ids=consol_pids,
                )
                for item in (result or {}).get("affected_projects", []):
                    pid = UUID(item["consol_project_id"])
                    stale_by_project[pid] = stale_by_project.get(pid, 0) + 1
            await db.commit()

        for pid, count in stale_by_project.items():
            _emit_consol_note_stale(pid, year, note_section, count)
    except Exception as err:
        logger.warning(
            "_on_note_section_saved_mark_consol_stale failed for project %s: %s",
            project_id, err,
        )


async def _resolve_saved_note_section(
    db: Any, entity_project_id: UUID, year: Any, saved: Any,
) -> tuple[str | None, str | None]:
    """事件里的章节标识 → (单体章节号, 章节标题)。

    个别发布方只给附注记录 id；按 id 查回章节号。章节标题用于子企业附注模板与合并口径不同
    （国企集团含上市子公司）时按标题认章节。查不到章节号返回 (None, None) = 视为整企业变化。
    """
    if not saved:
        return None, None
    import sqlalchemy as sa
    from app.models.report_models import DisclosureNote

    text_value = str(saved).strip()
    try:
        condition = DisclosureNote.id == UUID(text_value)
        is_note_id = True
    except ValueError:
        condition = sa.and_(DisclosureNote.note_section == text_value, DisclosureNote.year == year)
        is_note_id = False
    row = (await db.execute(
        sa.select(DisclosureNote.note_section, DisclosureNote.section_title)
        .where(condition, DisclosureNote.project_id == entity_project_id)
        .limit(1)
    )).first()
    if row is None:
        # 查不到记录（如章节已删除）：给的是章节号就照用；给的是记录 id 就无从判断，按整企业变化处理
        return (None, None) if is_note_id else (text_value, None)
    return row.note_section, row.section_title


async def _affected_consol_sections(
    db: Any,
    entity_project_id: UUID,
    note_section: str | None,
    section_title: str | None = None,
) -> dict[str, list[UUID]]:
    """该企业作为来源的已确认绑定里，受本次保存影响的 ``{合并章节号: [合并项目 id]}``。

    合并章节经章节映射对应的单体章节号或章节标题与本次保存的一致即受影响（读取层按号取不到
    时按标题取，这里同口径）。``note_section`` 为空 = 该企业全部已绑定章节都受影响。
    """
    import sqlalchemy as sa
    from app.models.consol_note_mapping_models import ConsolNoteMappingBinding
    from app.services.consol_note_detail_source_service import resolve_section_template_type
    from app.services.consol_note_section_mapping import resolve_mapping_entry

    title_key = "".join(str(section_title or "").split())
    pairs = (await db.execute(
        sa.select(ConsolNoteMappingBinding.project_id, ConsolNoteMappingBinding.section_id)
        .where(
            ConsolNoteMappingBinding.entity_project_id == entity_project_id,
            ConsolNoteMappingBinding.status.in_(["confirmed", "stale"]),
        )
        .distinct()
    )).all()

    template_types: dict[UUID, str] = {}
    affected: dict[str, list[UUID]] = {}
    for consol_pid, section_id in pairs:
        if note_section:
            if consol_pid not in template_types:
                template_types[consol_pid] = await resolve_section_template_type(db, consol_pid)
            entry = resolve_mapping_entry(template_types[consol_pid], section_id) or {}
            same_number = entry.get("standalone_note_section") == note_section
            same_title = bool(title_key) and "".join(
                str(entry.get("standalone_section_title") or "").split()
            ) == title_key
            if not (same_number or same_title):
                continue
        affected.setdefault(section_id, []).append(consol_pid)
    return affected


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
