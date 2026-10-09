"""披露同步覆盖率只读查询服务

返回按 wp_code × 变体分组的 {expected, synced, stale, never_synced}。
分母派生自 note_workpaper_sync_registry.json（禁手工第二份清单）。
排除项目未启用的底稿（判定走 wp_index, is_deleted=False）。
纯只读，不触发同步。

spec: disclosure-payload-authority-source / Task 2.1 / Q6 Q7
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.models.workpaper_models import WpIndex

logger = logging.getLogger(__name__)

# ─── 注册表读取 ──────────────────────────────────────────────────────────

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "note_workpaper_sync_registry.json"


@lru_cache(maxsize=1)
def _load_registry() -> list[dict[str, Any]]:
    """读取注册表 entries（权威源，lru_cache 避免重复 IO）。"""
    with open(_REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("entries", [])


class SectionExpectation(TypedDict):
    wp_code: str
    variant: str        # 'listed' | 'soe'
    note_section: str   # 如 '五、4'


def _build_expectations() -> list[SectionExpectation]:
    """从注册表构建「应同步章节」全集。

    多章节映射（如 G1 有 trading + derivative）展开为多行。
    """
    results: list[SectionExpectation] = []
    for entry in _load_registry():
        wp_code = entry.get("wp_code", "")
        if not wp_code:
            continue
        # 优先用 listed_sections / soe_sections（多章节映射）
        listed_sections = entry.get("listed_sections") or {}
        soe_sections = entry.get("soe_sections") or {}
        if listed_sections:
            for _key, section in listed_sections.items():
                results.append(SectionExpectation(
                    wp_code=wp_code, variant="listed", note_section=section,
                ))
        elif entry.get("listed"):
            results.append(SectionExpectation(
                wp_code=wp_code, variant="listed", note_section=entry["listed"],
            ))
        if soe_sections:
            for _key, section in soe_sections.items():
                results.append(SectionExpectation(
                    wp_code=wp_code, variant="soe", note_section=section,
                ))
        elif entry.get("soe"):
            results.append(SectionExpectation(
                wp_code=wp_code, variant="soe", note_section=entry["soe"],
            ))
    return results


# ─── 核心查询 ─────────────────────────────────────────────────────────────


class CoverageItem(TypedDict):
    wp_code: str
    variant: str
    note_section: str
    expected: bool      # 项目启用了该底稿
    synced: bool        # last_sync_at IS NOT NULL
    stale: bool         # is_stale = true
    never_synced: bool  # expected 且 last_sync_at IS NULL


class CoverageSummary(TypedDict):
    """覆盖率汇总。

    🔴 汇总数一律按 ``note_section`` **去重**后统计，不按职责行计数 ——
    8 个章节是跨循环共享的（现算，如「五、8」由 G2/G3/K1 共同推送），
    同一个 ``disclosure_notes`` 行若按职责行计数会被重复计 2~3 次，
    使 ``synced``/``stale`` 虚高（真库实测 service 17 vs 直接 SQL 13）。

    ``expected`` = 去重后应同步的章节数（用户关心的口径）
    ``duty_rows`` = 职责行数（含共享章节的重复），仅供诊断
    ``items``     = 逐条职责行，保留「哪个 wp_code 负责哪个章节」
    """

    expected: int
    synced: int
    stale: int
    never_synced: int
    duty_rows: int
    items: list[CoverageItem]


async def get_project_disclosure_sync_coverage(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> CoverageSummary:
    """返回项目级同步覆盖率。

    逻辑：
    1. 读注册表得到全部 (wp_code, variant, note_section) 三元组
    2. 查 wp_index 得到项目启用了哪些 wp_code → 排除未启用的
    3. 查 disclosure_notes 得到已同步/stale 状态
    4. 汇总
    """
    all_expectations = _build_expectations()
    all_wp_codes = list({e["wp_code"] for e in all_expectations})

    # 查项目启用的 wp_code 集合
    stmt_enabled = (
        sa.select(WpIndex.wp_code)
        .where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code.in_(all_wp_codes),
            WpIndex.is_deleted == sa.false(),
        )
    )
    result_enabled = await db.execute(stmt_enabled)
    enabled_codes: set[str] = {row[0] for row in result_enabled}

    # 查 disclosure_notes 的同步状态（按 note_section 取）
    all_sections = [e["note_section"] for e in all_expectations]
    stmt_notes = (
        sa.select(
            DisclosureNote.note_section,
            DisclosureNote.last_sync_at,
            DisclosureNote.is_stale,
        )
        .where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section.in_(all_sections),
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    result_notes = await db.execute(stmt_notes)
    note_status: dict[str, dict[str, Any]] = {}
    for row in result_notes:
        note_status[row.note_section] = {
            "last_sync_at": row.last_sync_at,
            "is_stale": row.is_stale,
        }

    # 构建结果
    items: list[CoverageItem] = []
    for exp in all_expectations:
        is_expected = exp["wp_code"] in enabled_codes
        if not is_expected:
            continue  # 排除未启用底稿，不计入分母
        ns = note_status.get(exp["note_section"])
        is_synced = ns is not None and ns["last_sync_at"] is not None
        is_stale = ns is not None and ns["is_stale"] is True
        items.append(CoverageItem(
            wp_code=exp["wp_code"],
            variant=exp["variant"],
            note_section=exp["note_section"],
            expected=True,
            synced=is_synced,
            stale=is_stale,
            never_synced=not is_synced,
        ))

    # 🔴 汇总按 note_section 去重：共享章节（现算 8 个，如「五、8」← G2/G3/K1）
    #    在 items 里有多条职责行，但对应的 disclosure_notes **只有一行**，
    #    按职责行计数会把同一行重复计 2~3 次（真库实测虚高 4~5）。
    seen_sections: set[str] = set()
    synced_sections: set[str] = set()
    stale_sections: set[str] = set()
    for item in items:
        section = item["note_section"]
        seen_sections.add(section)
        if item["synced"]:
            synced_sections.add(section)
        if item["stale"]:
            stale_sections.add(section)

    return CoverageSummary(
        expected=len(seen_sections),
        synced=len(synced_sections),
        stale=len(stale_sections),
        never_synced=len(seen_sections - synced_sections),
        duty_rows=len(items),
        items=items,
    )
