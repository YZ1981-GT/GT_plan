"""Property 10: L1 层次身份纯净性 (PBT)

# Feature: acnr, Property 10: L1 层次身份纯净性

L1 GlobalCatalog（global_catalog.json）的身份纯净性约束验证：
1. 所有条目 domain="wp"（首期仅 wp 域进 L1）
2. 无条目含 runtime_only=true（RuntimeCellEntry only in L2/L3）
3. 无条目含 project_id 或 wp_id 字段（R6.4）
4. 所有 addr_id 匹配预期 pattern：
   - Sheet: ^[A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+$
   - Cell: ^([A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+/[A-Za-z0-9_-]+|note/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+)$

**Validates: Requirements 6.4, 7.1, 17.2, 22.2, 24.2**

Testing framework: hypothesis
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

# ---------------------------------------------------------------------------
# Load actual global_catalog.json
# ---------------------------------------------------------------------------

_CATALOG_PATH = _BACKEND_ROOT / "data" / "acnr" / "global_catalog.json"

with open(_CATALOG_PATH, "r", encoding="utf-8") as _f:
    _CATALOG = json.load(_f)

_ALL_SHEETS: list[dict] = _CATALOG.get("sheets", [])
_ALL_CELLS: list[dict] = _CATALOG.get("cells", [])

# Combine all entries for unified checks
_ALL_ENTRIES: list[dict] = _ALL_SHEETS + _ALL_CELLS

# ---------------------------------------------------------------------------
# addr_id pattern definitions (from global_catalog.schema.json)
# ---------------------------------------------------------------------------

SHEET_ADDR_ID_RE = re.compile(r"^[A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+$")
CELL_ADDR_ID_RE = re.compile(
    r"^([A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+/[A-Za-z0-9_-]+|note/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+)$"
)

# ---------------------------------------------------------------------------
# Strategies: sample from actual catalog entries
# ---------------------------------------------------------------------------


@st.composite
def st_catalog_entry(draw: st.DrawFn) -> dict:
    """Draw a random entry (sheet or cell) from the actual global_catalog.json."""
    assume(len(_ALL_ENTRIES) > 0)
    idx = draw(st.integers(min_value=0, max_value=len(_ALL_ENTRIES) - 1))
    return _ALL_ENTRIES[idx]


@st.composite
def st_sheet_entry(draw: st.DrawFn) -> dict:
    """Draw a random sheet entry from the actual global_catalog.json."""
    assume(len(_ALL_SHEETS) > 0)
    idx = draw(st.integers(min_value=0, max_value=len(_ALL_SHEETS) - 1))
    return _ALL_SHEETS[idx]


@st.composite
def st_cell_entry(draw: st.DrawFn) -> dict:
    """Draw a random cell entry from the actual global_catalog.json."""
    assume(len(_ALL_CELLS) > 0)
    idx = draw(st.integers(min_value=0, max_value=len(_ALL_CELLS) - 1))
    return _ALL_CELLS[idx]


# ---------------------------------------------------------------------------
# Property Test: L1 层次身份纯净性
# ---------------------------------------------------------------------------


class TestL1IdentityPurity:
    """Property 10: L1 层次身份纯净性

    验证 global_catalog.json 的四项身份纯净性约束。
    """

    # Feature: acnr, Property 10: L1 层次身份纯净性

    @given(entry=st_catalog_entry())
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_all_entries_domain_wp(self, entry: dict):
        """所有 L1 条目 domain 均为 'wp'（首期仅 wp 域进 L1）。

        **Validates: Requirements 22.2**
        """
        assert entry.get("domain") == "wp", (
            f"Entry {entry.get('addr_id')} has domain={entry.get('domain')!r}, "
            f"expected 'wp' (L1 首期仅 wp 域)"
        )

    @given(entry=st_catalog_entry())
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_no_runtime_only(self, entry: dict):
        """无 L1 条目含 runtime_only=true（RuntimeCellEntry only in L2/L3）。

        **Validates: Requirements 24.2**
        """
        assert entry.get("runtime_only") is not True, (
            f"Entry {entry.get('addr_id')} has runtime_only=true, "
            f"which is forbidden in L1 (only allowed in L2/L3)"
        )

    @given(entry=st_catalog_entry())
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_no_project_id_or_wp_id(self, entry: dict):
        """无 L1 条目含 project_id 或 wp_id 字段（R6.4）。

        **Validates: Requirements 6.4**
        """
        assert "project_id" not in entry, (
            f"Entry {entry.get('addr_id')} contains 'project_id' field, "
            f"which is forbidden in global L1 catalog (R6.4)"
        )
        assert "wp_id" not in entry, (
            f"Entry {entry.get('addr_id')} contains 'wp_id' field, "
            f"which is forbidden in global L1 catalog (R6.4)"
        )

    @given(entry=st_sheet_entry())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_sheet_addr_id_pattern(self, entry: dict):
        """Sheet 条目 addr_id 匹配 ^[A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+$ 。

        **Validates: Requirements 7.1, 17.2**
        """
        addr_id = entry.get("addr_id", "")
        assert SHEET_ADDR_ID_RE.match(addr_id), (
            f"Sheet entry addr_id={addr_id!r} does not match expected pattern "
            f"'^[A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+$'"
        )

    @given(entry=st_cell_entry())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_cell_addr_id_pattern(self, entry: dict):
        """Cell 条目 addr_id 匹配合法 pattern（standard 或 note 子域）。

        Pattern: ^([A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+/[A-Za-z0-9_-]+|note/...)$

        **Validates: Requirements 7.1, 17.2**
        """
        addr_id = entry.get("addr_id", "")
        assert CELL_ADDR_ID_RE.match(addr_id), (
            f"Cell entry addr_id={addr_id!r} does not match expected pattern "
            f"'^([A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+/[A-Za-z0-9_-]+|note/...)$'"
        )
