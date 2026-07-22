"""A17-1 / A17-6 上游变更 stale 检测（基于 checklist_responses.updated_at）。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_CHAPTER_DEFS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "a17_chapter_definitions.json"
)

# A17-6 议程 → 主要上游 wp_code（与 guidance 对齐）
_AGENDA_UPSTREAM: dict[int, list[str]] = {
    2: ["B50", "A17-5-1"],
    3: ["B50"],
    5: ["A13"],
    7: ["A17-7"],
    9: ["A17-2-1"],
}


def _load_chapter_sources() -> dict[str, list[str]]:
    try:
        data = json.loads(_CHAPTER_DEFS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("load chapter defs failed: %s", exc)
        return {}
    out: dict[str, list[str]] = {}
    for ch in data:
        cid = ch.get("id") or ""
        sources = (ch.get("data_source") or {}).get("sources") or []
        # 仅保留像底稿编码的项
        codes = [
            s
            for s in sources
            if isinstance(s, str) and s[:1].isalpha() and any(c.isdigit() for c in s)
        ]
        if cid and codes:
            out[cid] = codes
    return out


async def _get_wp_id(db: AsyncSession, project_id: UUID, wp_code: str) -> str | None:
    result = await db.execute(
        sa.text(
            """
            SELECT wp_id FROM wp_index
            WHERE project_id = :pid AND wp_code = :code
            LIMIT 1
            """
        ),
        {"pid": str(project_id), "code": wp_code},
    )
    row = result.fetchone()
    return str(row[0]) if row and row[0] else None


async def _max_updated_at(db: AsyncSession, wp_ids: list[str]) -> datetime | None:
    if not wp_ids:
        return None
    # 使用逐条 IN，兼容 PG / 测试
    placeholders = ", ".join(f":w{i}" for i in range(len(wp_ids)))
    params = {f"w{i}": wid for i, wid in enumerate(wp_ids)}
    result = await db.execute(
        sa.text(
            f"""
            SELECT MAX(updated_at) FROM checklist_responses
            WHERE wp_id IN ({placeholders})
            """
        ),
        params,
    )
    return result.scalar_one_or_none()


async def _chapter_content_updated_at(
    db: AsyncSession, a171_wp_id: str, chapter_num: int
) -> datetime | None:
    """本章内容最后写入时间（content/yn/table 或旧格式）。"""
    result = await db.execute(
        sa.text(
            """
            SELECT MAX(updated_at) FROM checklist_responses
            WHERE wp_id = :wid
              AND (
                item_id LIKE :pfx1
                OR item_id LIKE :pfx2
                OR item_id = :legacy
              )
              AND (
                (remark IS NOT NULL AND TRIM(remark) <> '')
                OR (conclusion IS NOT NULL AND conclusion <> '')
              )
            """
        ),
        {
            "wid": a171_wp_id,
            "pfx1": f"a171-ch{chapter_num}-%",
            "pfx2": f"a171-ch{chapter_num:02d}-%",
            "legacy": f"A17-1-ch{chapter_num:02d}",
        },
    )
    return result.scalar_one_or_none()


async def check_chapter_stale(db: AsyncSession, project_id: UUID, wp_id: UUID) -> dict:
    """检测 A17-1 各章相对上游底稿是否过期。"""
    sources_map = _load_chapter_sources()
    stale_chapters: list[dict] = []

    for chapter_id, codes in sources_map.items():
        try:
            num = int(chapter_id.split("ch")[-1])
        except ValueError:
            continue

        chapter_ts = await _chapter_content_updated_at(db, str(wp_id), num)
        if chapter_ts is None:
            continue  # 未填写 → 不算过期

        upstream_ids: list[str] = []
        for code in codes:
            wid = await _get_wp_id(db, project_id, code)
            if wid:
                upstream_ids.append(wid)
        upstream_ts = await _max_updated_at(db, upstream_ids)
        if upstream_ts is None:
            continue
        if upstream_ts > chapter_ts:
            stale_chapters.append(
                {
                    "chapter_id": chapter_id,
                    "chapter_num": num,
                    "message": f"上游 {','.join(codes)} 有更新，建议重新拉取",
                    "sources": codes,
                    "upstream_updated_at": upstream_ts.isoformat(),
                    "chapter_updated_at": chapter_ts.isoformat(),
                }
            )

    return {
        "stale": len(stale_chapters) > 0,
        "stale_chapters": stale_chapters,
        "message": (
            f"{len(stale_chapters)} 个章节可能过期"
            if stale_chapters
            else "各章与上游时间戳一致"
        ),
    }


async def _agenda_updated_at(db: AsyncSession, a176_wp_id: str, idx: int) -> datetime | None:
    result = await db.execute(
        sa.text(
            """
            SELECT updated_at FROM checklist_responses
            WHERE wp_id = :wid AND item_id = :iid
              AND remark IS NOT NULL AND TRIM(remark) <> ''
            LIMIT 1
            """
        ),
        {"wid": a176_wp_id, "iid": f"a176-agenda-{idx}"},
    )
    row = result.fetchone()
    return row[0] if row else None


async def check_agenda_stale(db: AsyncSession, project_id: UUID, wp_id: UUID) -> dict:
    """检测 A17-6 已填议程相对上游是否过期。"""
    stale_items: list[dict] = []
    for idx, codes in _AGENDA_UPSTREAM.items():
        agenda_ts = await _agenda_updated_at(db, str(wp_id), idx)
        if agenda_ts is None:
            continue
        upstream_ids: list[str] = []
        for code in codes:
            wid = await _get_wp_id(db, project_id, code)
            if wid:
                upstream_ids.append(wid)
        upstream_ts = await _max_updated_at(db, upstream_ids)
        if upstream_ts and upstream_ts > agenda_ts:
            stale_items.append(
                {
                    "agenda_index": idx,
                    "message": f"上游 {','.join(codes)} 有更新，建议重新预填核对",
                    "sources": codes,
                    "upstream_updated_at": upstream_ts.isoformat(),
                    "agenda_updated_at": agenda_ts.isoformat(),
                }
            )

    return {
        "stale": len(stale_items) > 0,
        "stale_items": stale_items,
        "message": (
            f"{len(stale_items)} 项议程可能过期" if stale_items else "议程与上游时间戳一致"
        ),
    }
