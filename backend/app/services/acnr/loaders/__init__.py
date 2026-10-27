"""ACNR Loaders — 从各数据源加载 catalog 输入。

所有 loader 均为纯函数或薄封装，只读不写。
"""

from __future__ import annotations

from .from_classification import load_sheet_skeletons_from_classification
from .from_ie_manifest import load_ie_manifest
from .from_address_seeds import load_cell_entries_from_seeds
from .from_frontend_labels import load_sheet_name_aliases
from .from_render_registry import load_render_registry_edges
from .from_sheet_verdicts import load_sheet_verdicts
from .from_wp_account_mapping import (
    WpNameAliasResult,
    load_wp_account_mapping_aliases,
)

__all__ = [
    "load_sheet_skeletons_from_classification",
    "load_ie_manifest",
    "load_cell_entries_from_seeds",
    "load_sheet_name_aliases",
    "load_render_registry_edges",
    "load_sheet_verdicts",
    "WpNameAliasResult",
    "load_wp_account_mapping_aliases",
]
