"""同事务标过期（S4 ADR-SDO-03）。

定义写入出口在同一事务内标过期，与入队同步：事务回滚则标记也回滚（不会出现
「定义没写成功但下游已标过期」）。各域口径与 ``propagation.propagate_*`` 相同，
但不开独立会话、不 commit——调用方的路由统一 commit。

报表域复用 ``report_freshness.mark_changed``（hub ADR-FHIC-04）。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── 底稿域 ──────────────────────────────────────────────────────────────────

def _wp_codes_from_slots(slot_keys: Iterable[str]) -> list[str]:
    """slot_key 取 ``|`` 前半段作 wp_code（与 ``propagate_wp`` 同口径）。"""
    return sorted({s.split("|", 1)[0] for s in slot_keys if s})


async def mark_wp_stale(
    db: AsyncSession,
    project_id: uuid.UUID,
    slot_keys: Iterable[str],
) -> int:
    """底稿：受影响底稿的 ``working_paper.prefill_stale = true``。只 flush 不 commit。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    codes = _wp_codes_from_slots(slot_keys)
    if not codes:
        return 0
    idx = sa.select(WpIndex.id).where(
        WpIndex.project_id == project_id,
        WpIndex.wp_code.in_(codes),
    )
    result = await db.execute(
        sa.update(WorkingPaper)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.wp_index_id.in_(idx),
        )
        .values(prefill_stale=True)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


# ── 附注域 ──────────────────────────────────────────────────────────────────

def _sections_from_slots(slot_keys: Iterable[str]) -> list[str]:
    """slot_key 取 ``|`` 前半段作 note_section（与 ``propagate_note`` 同口径）。"""
    return sorted({s.split("|", 1)[0] for s in slot_keys if s})


async def mark_note_stale(
    db: AsyncSession,
    project_id: uuid.UUID,
    slot_keys: Iterable[str],
) -> int:
    """附注：受影响章节的 ``disclosure_notes.is_stale = true``。只 flush 不 commit。"""
    from app.models.report_models import DisclosureNote

    sections = _sections_from_slots(slot_keys)
    if not sections:
        return 0
    result = await db.execute(
        sa.update(DisclosureNote)
        .where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.note_section.in_(sections),
            DisclosureNote.is_deleted == sa.false(),
        )
        .values(is_stale=True)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


# ── 合并附注域 ──────────────────────────────────────────────────────────────

async def mark_consol_note_stale(
    db: AsyncSession,
    project_id: uuid.UUID,
    slot_keys: Iterable[str],
) -> int:
    """合并附注：受影响章节的 ``consol_note_data.is_stale = true``。只 flush 不 commit。"""
    try:
        from app.models.consol_note_models import ConsolNoteData
    except ImportError:
        logger.debug("consol_note_models 不可用，跳过合并附注标过期")
        return 0

    sections = _sections_from_slots(slot_keys)
    if not sections:
        return 0
    result = await db.execute(
        sa.update(ConsolNoteData)
        .where(
            ConsolNoteData.project_id == project_id,
            ConsolNoteData.section_code.in_(sections),
        )
        .values(is_stale=True)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


# ── 统一入口 ────────────────────────────────────────────────────────────────

async def mark_in_txn(
    db: AsyncSession,
    domain: str,
    project_id: uuid.UUID,
    slot_keys: Iterable[str],
) -> dict[str, Any]:
    """按域标过期（同事务，只 flush 不 commit）。

    报表域复用 ``report_freshness.mark_changed``；
    cross_check / push / tb_detail 不标（结果由处理器重算覆盖）。

    Returns:
        ``{"domain": str, "marked": int}``
    """
    slots = list(slot_keys)
    if not slots:
        return {"domain": domain, "marked": 0}

    if domain == "report":
        from app.services.report_freshness import mark_changed, slot_row_codes
        codes = slot_row_codes(slots)
        closures = await mark_changed(db, {project_id: codes})
        return {"domain": domain, "marked": len(closures.get(project_id, set()))}

    if domain == "wp":
        n = await mark_wp_stale(db, project_id, slots)
        return {"domain": domain, "marked": n}

    if domain == "note":
        n = await mark_note_stale(db, project_id, slots)
        return {"domain": domain, "marked": n}

    if domain == "consol_note":
        n = await mark_consol_note_stale(db, project_id, slots)
        return {"domain": domain, "marked": n}

    # cross_check / push / tb_detail：不标过期
    return {"domain": domain, "marked": 0, "reason": "no_stale_mark_for_domain"}
