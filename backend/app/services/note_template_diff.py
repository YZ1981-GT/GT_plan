"""Note template diff service — SOE/Listed 模板差异管理.

Sprint A.5 Tasks: A.5.9 / A.5.10 / A.5.11

纯函数 / 无 DB / ≤ 350 行

Functions:
    load_diff_data() — 优先从 JSON 加载，降级到实时计算
    compute_diff_from_templates(soe_sections, listed_sections) — 按 section_title 匹配
    compute_section_diff(soe_section, listed_section) — 单章节 diff
    adapt_table_data(table_data, target_format, field_mapping) — 列重映射
    classify_section_mapping(section_id, diff_data) — 分类工具
"""
from __future__ import annotations

import json
import logging
import pathlib
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "load_diff_data",
    "compute_diff_from_templates",
    "compute_section_diff",
    "adapt_table_data",
    "classify_section_mapping",
]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DATA_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "data"
_DIFF_JSON_PATH = _DATA_DIR / "note_soe_listed_diff.json"
_SOE_TEMPLATE_PATH = _DATA_DIR / "note_template_soe.json"
_LISTED_TEMPLATE_PATH = _DATA_DIR / "note_template_listed.json"

# Cache
_DIFF_CACHE: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# load_diff_data
# ---------------------------------------------------------------------------


def load_diff_data() -> dict[str, Any]:
    """Load diff data from JSON file; fallback to real-time computation.

    Returns:
        Dict with keys: version, is_mock, common_sections,
        soe_only_sections, listed_only_sections, format_diff_sections
    """
    global _DIFF_CACHE
    if _DIFF_CACHE is not None:
        return _DIFF_CACHE

    # Try loading from pre-generated JSON
    if _DIFF_JSON_PATH.exists():
        try:
            data = json.loads(_DIFF_JSON_PATH.read_text(encoding="utf-8"))
            _DIFF_CACHE = data
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load diff JSON: %s, falling back to compute", e)

    # Fallback: compute from templates
    data = _compute_from_template_files()
    _DIFF_CACHE = data
    return data


def reset_diff_cache() -> None:
    """Reset the cached diff data (for testing)."""
    global _DIFF_CACHE
    _DIFF_CACHE = None


# ---------------------------------------------------------------------------
# compute_diff_from_templates
# ---------------------------------------------------------------------------


def compute_diff_from_templates(
    soe_sections: list[dict[str, Any]],
    listed_sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute diff between SOE and Listed section lists by section_title matching.

    Args:
        soe_sections: List of SOE template section dicts
        listed_sections: List of Listed template section dicts

    Returns:
        Dict with common_sections, soe_only_sections, listed_only_sections,
        format_diff_sections
    """
    soe_by_title = _build_title_index(soe_sections)
    listed_by_title = _build_title_index(listed_sections)

    soe_titles = set(soe_by_title.keys())
    listed_titles = set(listed_by_title.keys())

    common_titles = sorted(soe_titles & listed_titles)
    soe_only_titles = sorted(soe_titles - listed_titles)
    listed_only_titles = sorted(listed_titles - soe_titles)

    common_sections: list[dict[str, Any]] = []
    format_diff_sections: list[dict[str, Any]] = []

    for title in common_titles:
        soe_s = soe_by_title[title]
        listed_s = listed_by_title[title]
        common_sections.append({
            "section_title": title,
            "soe_section_id": soe_s.get("section_id", ""),
            "listed_section_id": listed_s.get("section_id", ""),
        })

        diff = compute_section_diff(soe_s, listed_s)
        if diff.get("has_format_diff"):
            format_diff_sections.append({
                "section_title": title,
                "soe_section_id": soe_s.get("section_id", ""),
                "listed_section_id": listed_s.get("section_id", ""),
                "soe_format": diff["soe_format"],
                "listed_format": diff["listed_format"],
                "field_mapping": diff.get("field_mapping"),
            })

    soe_only_sections = [
        {"section_id": soe_by_title[t].get("section_id", ""), "title": t}
        for t in soe_only_titles
    ]
    listed_only_sections = [
        {"section_id": listed_by_title[t].get("section_id", ""), "title": t}
        for t in listed_only_titles
    ]

    return {
        "version": "1.0.0",
        "is_mock": False,
        "common_sections": common_sections,
        "soe_only_sections": soe_only_sections,
        "listed_only_sections": listed_only_sections,
        "format_diff_sections": format_diff_sections,
    }


# ---------------------------------------------------------------------------
# compute_section_diff
# ---------------------------------------------------------------------------


def compute_section_diff(
    soe_section: dict[str, Any],
    listed_section: dict[str, Any],
) -> dict[str, Any]:
    """Compute diff between a single SOE section and its Listed counterpart.

    Returns:
        Dict with has_format_diff, soe_format, listed_format, field_mapping
    """
    soe_ct = soe_section.get("content_type", "text")
    listed_ct = listed_section.get("content_type", "text")
    soe_tables = len(soe_section.get("tables", []))
    listed_tables = len(listed_section.get("tables", []))

    has_diff = (
        soe_ct != listed_ct
        or (soe_tables > 0 and listed_tables > 0 and soe_tables != listed_tables)
    )

    return {
        "has_format_diff": has_diff,
        "soe_format": {"content_type": soe_ct, "table_count": soe_tables},
        "listed_format": {"content_type": listed_ct, "table_count": listed_tables},
        "field_mapping": None,  # Populated by P-7 auditor annotation
    }


# ---------------------------------------------------------------------------
# adapt_table_data (A.5.11)
# ---------------------------------------------------------------------------


def adapt_table_data(
    table_data: dict[str, Any],
    target_format: dict[str, Any],
    field_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt table_data to target format using column/field remapping.

    This handles cases like SOE movement table → Listed category_sum columns.

    Args:
        table_data: Source table_data dict (rows, headers, _columns_meta, etc.)
        target_format: Target format descriptor (content_type, table_count, etc.)
        field_mapping: Optional column mapping dict:
            {"column_remap": {"source_col_id": "target_col_id", ...},
             "row_filter": {...},
             "value_transform": {...}}

    Returns:
        Adapted table_data dict (deep copy, safe to mutate)
    """
    if not isinstance(table_data, dict):
        return {}

    result = deepcopy(table_data)

    if not field_mapping or not isinstance(field_mapping, dict):
        # No mapping available — return as-is (structure preserved)
        return result

    column_remap = field_mapping.get("column_remap")
    if isinstance(column_remap, dict) and column_remap:
        result = _apply_column_remap(result, column_remap)

    row_filter = field_mapping.get("row_filter")
    if isinstance(row_filter, dict) and row_filter:
        result = _apply_row_filter(result, row_filter)

    return result


def _apply_column_remap(
    table_data: dict[str, Any],
    column_remap: dict[str, str],
) -> dict[str, Any]:
    """Remap column IDs in _columns_meta and row values.

    column_remap: {"old_col_id": "new_col_id", ...}
    """
    columns_meta = table_data.get("_columns_meta")
    if not isinstance(columns_meta, list):
        return table_data

    # Build old position index
    old_positions: dict[str, int] = {}
    for i, col in enumerate(columns_meta):
        if isinstance(col, dict):
            cid = col.get("id", "")
            if cid:
                old_positions[cid] = i

    # Remap column IDs in meta
    for col in columns_meta:
        if isinstance(col, dict):
            cid = col.get("id", "")
            if cid in column_remap:
                col["id"] = column_remap[cid]

    # Rows don't need value reordering since positions stay the same
    # (only the column ID label changes)
    table_data["_columns_meta"] = columns_meta
    return table_data


def _apply_row_filter(
    table_data: dict[str, Any],
    row_filter: dict[str, Any],
) -> dict[str, Any]:
    """Filter rows based on criteria (e.g., exclude certain row_types)."""
    exclude_types = row_filter.get("exclude_row_types")
    if not isinstance(exclude_types, list):
        return table_data

    rows = table_data.get("rows")
    if not isinstance(rows, list):
        return table_data

    exclude_set = set(exclude_types)
    filtered = [r for r in rows if not (isinstance(r, dict) and r.get("row_type") in exclude_set)]
    table_data["rows"] = filtered
    return table_data


# ---------------------------------------------------------------------------
# classify_section_mapping (A.5.10)
# ---------------------------------------------------------------------------


def classify_section_mapping(
    section_id: str,
    diff_data: dict[str, Any],
    source_type: str = "soe",
) -> tuple[str, dict[str, Any] | None]:
    """Classify how a section maps between SOE and Listed.

    Args:
        section_id: The section_id to classify
        diff_data: The diff data dict (from load_diff_data)
        source_type: "soe" or "listed" — which template the section_id belongs to

    Returns:
        Tuple of (classification, metadata):
        - ("common", {"target_section_id": "...", ...}) — direct copy
        - ("source_only", None) — exists only in source, archive in target
        - ("target_only", None) — exists only in target, create empty
        - ("format_diff", {"soe_format": ..., "listed_format": ..., "field_mapping": ...})
    """
    if not isinstance(diff_data, dict):
        return ("unknown", None)

    id_field = "soe_section_id" if source_type == "soe" else "listed_section_id"
    target_id_field = "listed_section_id" if source_type == "soe" else "soe_section_id"

    # Check format_diff_sections first (more specific)
    for entry in diff_data.get("format_diff_sections", []):
        if entry.get(id_field) == section_id:
            return ("format_diff", {
                "target_section_id": entry.get(target_id_field, ""),
                "section_title": entry.get("section_title", ""),
                "soe_format": entry.get("soe_format"),
                "listed_format": entry.get("listed_format"),
                "field_mapping": entry.get("field_mapping"),
            })

    # Check common_sections
    for entry in diff_data.get("common_sections", []):
        if entry.get(id_field) == section_id:
            return ("common", {
                "target_section_id": entry.get(target_id_field, ""),
                "section_title": entry.get("section_title", ""),
            })

    # Check source-only sections
    source_only_key = "soe_only_sections" if source_type == "soe" else "listed_only_sections"
    for entry in diff_data.get(source_only_key, []):
        if entry.get("section_id") == section_id:
            return ("source_only", {"title": entry.get("title", "")})

    # Check target-only sections (section exists in target but not source)
    target_only_key = "listed_only_sections" if source_type == "soe" else "soe_only_sections"
    for entry in diff_data.get(target_only_key, []):
        if entry.get("section_id") == section_id:
            return ("target_only", {"title": entry.get("title", "")})

    return ("unknown", None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_title_index(sections: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build section_title -> first section dict."""
    index: dict[str, dict[str, Any]] = {}
    for s in sections:
        if not isinstance(s, dict):
            continue
        title = s.get("section_title", "")
        if title and title not in index:
            index[title] = s
    return index


def _compute_from_template_files() -> dict[str, Any]:
    """Load both template files and compute diff."""
    try:
        soe_data = json.loads(_SOE_TEMPLATE_PATH.read_text(encoding="utf-8"))
        listed_data = json.loads(_LISTED_TEMPLATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Cannot load template files for diff computation: %s", e)
        return {
            "version": "0.0.0",
            "is_mock": False,
            "common_sections": [],
            "soe_only_sections": [],
            "listed_only_sections": [],
            "format_diff_sections": [],
        }

    return compute_diff_from_templates(
        soe_data.get("sections", []),
        listed_data.get("sections", []),
    )
