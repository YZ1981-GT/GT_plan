"""E0 发函记录表四张 sheet 的列定义与版本常量。

单一真源 = backend/data/e0_send_list_source_manifest.json
"""

from __future__ import annotations

import json
from pathlib import Path

SHEET_E03 = "货币资金发函记录表E0-3"
SHEET_E04 = "借款发函记录表E0-4"
SHEET_E05 = "应付银行承兑汇票发函记录表E0-5"
SHEET_E06 = "理财产品发函记录表E0-6"

ALL_SHEETS = [SHEET_E03, SHEET_E04, SHEET_E05, SHEET_E06]

FORMAT_VERSION: dict[str, str] = {
    SHEET_E03: "send-list-e03-v1",
    SHEET_E04: "send-list-e04-v1",
    SHEET_E05: "send-list-e05-v1",
    SHEET_E06: "send-list-e06-v1",
}

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "e0_send_list_source_manifest.json"
)

_manifest_cache: dict | None = None


def _load_manifest() -> dict:
    global _manifest_cache
    if _manifest_cache is None:
        _manifest_cache = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return _manifest_cache


def column_map(sheet: str) -> dict[str, str]:
    """Return mapping of cell letter → field name for the given sheet.

    Reads from e0_send_list_source_manifest.json (single source of truth).
    """
    manifest = _load_manifest()
    cell_columns = manifest["sheets"][sheet]["cell_columns"]
    return {letter: col_def["field"] for letter, col_def in cell_columns.items()}


def fields(sheet: str) -> list[str]:
    """Return ordered list of field names for the given sheet (in template column order)."""
    manifest = _load_manifest()
    cell_columns = manifest["sheets"][sheet]["cell_columns"]
    return [col_def["field"] for col_def in cell_columns.values()]
