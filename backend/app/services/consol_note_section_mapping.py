"""合并附注 section_id ↔ 单体附注 note_section 映射服务。

映射由 ``gen_consol_standalone_note_mapping.py`` 生成，存储在
``backend/data/consol_note_section_mapping.json``。

运行时按 mtime 缓存；修改映射文件后自动重新加载。

spec: consol-note-pull-from-standalone · Task 1.3
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_MAPPING_PATH = _DATA_DIR / "consol_note_section_mapping.json"


@lru_cache(maxsize=4)
def _load_raw(template_type: str, mtime: float) -> list[dict]:
    """带 mtime 缓存的原始映射加载。"""
    try:
        data = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("consol_note_section_mapping: 映射文件加载失败", exc_info=True)
        return []
    mappings = data.get("mappings", {})
    return mappings.get(template_type, [])


def _mtime() -> float:
    try:
        return _MAPPING_PATH.stat().st_mtime
    except OSError:
        return 0.0


def _entries(template_type: str) -> list[dict]:
    return _load_raw(template_type, _mtime())


# ─── 正向查询：合并 section_id → 单体 note_section ─────────────────────────


def resolve_mapping_entry(
    template_type: str,
    consol_section_id: str,
) -> dict | None:
    """合并附注 section_id 的完整映射条目（单体章节号 / 子表名 / 合并表标题）。

    返回 None = 映射文件未覆盖；``standalone_note_section`` 为空 = 合并特有章节。
    """
    for entry in _entries(template_type):
        if entry.get("consol_section_id") == consol_section_id:
            return entry
    return None


def resolve_standalone_section(
    template_type: str,
    consol_section_id: str,
) -> str | None:
    """合并附注 section_id → 单体附注 note_section。

    返回 None = 该章节无映射（合并特有章节或映射文件未覆盖）。
    """
    for entry in _entries(template_type):
        if entry.get("consol_section_id") == consol_section_id:
            section = entry.get("standalone_note_section")
            return section if section else None
    return None


def resolve_standalone_table_name(
    template_type: str,
    consol_section_id: str,
) -> str | None:
    """合并附注 section_id → 单体附注中对应的子表名（如有）。"""
    for entry in _entries(template_type):
        if entry.get("consol_section_id") == consol_section_id:
            return entry.get("standalone_table_name")
    return None


# ─── 反向查询：单体 note_section → 合并 section_id 列表 ────────────────────


def resolve_consol_sections(
    template_type: str,
    standalone_note_section: str,
) -> list[str]:
    """单体附注 note_section → 所有映射到它的合并附注 section_id 列表。

    用途：子企业附注修改时，查哪些合并章节需要标 stale。
    """
    result = []
    for entry in _entries(template_type):
        if entry.get("standalone_note_section") == standalone_note_section:
            sid = entry.get("consol_section_id")
            if sid:
                result.append(sid)
    return result


# ─── 批量查询 ──────────────────────────────────────────────────────────────


def all_mapped_sections(template_type: str) -> list[dict]:
    """所有已映射的条目（排除 consol_only）。

    返回 [{consol_section_id, standalone_note_section, consol_parent, consol_title, match_type}, ...]
    """
    return [
        entry for entry in _entries(template_type)
        if entry.get("standalone_note_section")
    ]


def mapping_stats(template_type: str) -> dict[str, int]:
    """映射统计：各 match_type 的数量。"""
    stats: dict[str, int] = {}
    for entry in _entries(template_type):
        mt = entry.get("match_type", "unknown")
        stats[mt] = stats.get(mt, 0) + 1
    return stats
