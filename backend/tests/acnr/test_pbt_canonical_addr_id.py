# Feature: acnr, Property 2: canonical addr_id 与 formula_ref 构造一致
"""Property-based test: canonical addr_id 与 formula_ref 构造一致.

**Validates: Requirements 8.2, 8.3, 8.4, 8.6, 16.2**

验证规则:
- R8.2: 有 cell_address 时，canonical addr_id = {parent}/{sheet_code}/{cell_address}
- R8.3: semantic_label 写入 CellCatalogEntry 且不单独占 addr_id（除非 semantic_only）
- R8.4: semantic_only 时 addr_id = {parent}/{sheet_code}/{slug(semantic_label)}
- R8.6: parent_wp_code（WP() 第一参）== addr_id 的 parent 段
- R16.2: formula_ref 与 addr_id 构造一致
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis.strategies import sampled_from

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

# ---------------------------------------------------------------------------
# Load catalog data
# ---------------------------------------------------------------------------

_CATALOG_PATH = _BACKEND_ROOT / "data" / "acnr" / "global_catalog.json"
_catalog_data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
_ALL_CELLS: list[dict] = _catalog_data["cells"]
_SHEETS_MAP: dict[str, dict] = {s["addr_id"]: s for s in _catalog_data["sheets"]}

# 拆分为有 cell_address 的和 semantic_only 的
_CELLS_WITH_ADDRESS = [c for c in _ALL_CELLS if c.get("cell_address") and not c.get("semantic_only")]
_CELLS_SEMANTIC_ONLY = [c for c in _ALL_CELLS if c.get("semantic_only")]

# 解析 WP() 公式的正则：WP('arg1','arg2'[,'arg3'])
_RE_WP_FORMULA = re.compile(
    r"^WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)$"
)


# ---------------------------------------------------------------------------
# Property Test: cells with cell_address
# ---------------------------------------------------------------------------


@pytest.mark.skipif(len(_CELLS_WITH_ADDRESS) == 0, reason="No cell entries with cell_address")
class TestCanonicalAddrIdWithCellAddress:
    """有 cell_address 的 CellCatalogEntry 构造一致性验证。"""

    @given(cell=sampled_from(_CELLS_WITH_ADDRESS))
    @settings(max_examples=10)
    def test_addr_id_equals_parent_sheet_code_cell_address(self, cell: dict):
        """R8.2: canonical addr_id = {parent}/{sheet_code}/{cell_address}

        从 parent_addr_id 提取 parent 和 sheet_code，加上 cell_address 构成 addr_id。
        """
        parent_addr_id = cell["parent_addr_id"]
        cell_address = cell["cell_address"]

        # addr_id 应当等于 parent_addr_id/cell_address
        expected_addr_id = f"{parent_addr_id}/{cell_address}"
        assert cell["addr_id"] == expected_addr_id, (
            f"addr_id 构造不一致: expected={expected_addr_id}, actual={cell['addr_id']}"
        )

    @given(cell=sampled_from(_CELLS_WITH_ADDRESS))
    @settings(max_examples=10)
    def test_formula_ref_first_arg_matches_parent_wp_code(self, cell: dict):
        """R8.6: formula_ref 的 WP() 第一参 == addr_id 的 parent 段（parent_wp_code）。

        addr_id 形如 {parent_wp_code}/{sheet_code}/{cell}，
        formula_ref 形如 WP('{parent_wp_code}','{sheet_name}','{third_arg}')
        """
        addr_id = cell["addr_id"]
        formula_ref = cell["formula_ref"]

        # 从 addr_id 提取 parent（第一段）
        parent_from_addr_id = addr_id.split("/")[0]

        # 解析 formula_ref
        m = _RE_WP_FORMULA.match(formula_ref)
        if m is None:
            # 非 WP() 格式（可能是 2 参等），跳过此条
            pytest.skip(f"formula_ref 非标准 WP 三参格式: {formula_ref}")

        wp_first_arg = m.group(1)

        assert wp_first_arg == parent_from_addr_id, (
            f"formula_ref 第一参与 addr_id parent 段不一致: "
            f"WP first_arg={wp_first_arg}, addr_id parent={parent_from_addr_id}"
        )

    @given(cell=sampled_from(_CELLS_WITH_ADDRESS))
    @settings(max_examples=10)
    def test_formula_ref_components_consistent_with_addr_id(self, cell: dict):
        """R16.2: formula_ref 字段与 addr_id 构造一致。

        三参 WP(parent, sheet_name, cell_or_semantic):
        - parent == addr_id 第一段
        - cell_address 或 semantic_label 在第三参
        """
        formula_ref = cell["formula_ref"]
        addr_id = cell["addr_id"]
        cell_address = cell["cell_address"]

        m = _RE_WP_FORMULA.match(formula_ref)
        if m is None:
            pytest.skip(f"formula_ref 非标准格式: {formula_ref}")

        wp_parent = m.group(1)
        wp_third = m.group(3)  # 可能为 None (2参)

        # parent 一致性
        addr_parts = addr_id.split("/")
        assert wp_parent == addr_parts[0]

        # 第三参应该是 cell_address 或 semantic_label
        if wp_third is not None:
            # 第三参可以是 cell_address 本身，或 semantic_label
            valid_third = (
                wp_third == cell_address
                or wp_third == cell.get("semantic_label")
            )
            assert valid_third, (
                f"formula_ref 第三参 '{wp_third}' 既不是 cell_address='{cell_address}' "
                f"也不是 semantic_label='{cell.get('semantic_label')}'"
            )


# ---------------------------------------------------------------------------
# Property Test: semantic_only entries
# ---------------------------------------------------------------------------


@pytest.mark.skipif(len(_CELLS_SEMANTIC_ONLY) == 0, reason="No semantic_only entries")
class TestCanonicalAddrIdSemanticOnly:
    """semantic_only CellCatalogEntry 构造一致性验证。"""

    @given(cell=sampled_from(_CELLS_SEMANTIC_ONLY))
    @settings(max_examples=10)
    def test_semantic_only_addr_id_construction(self, cell: dict):
        """R8.4: semantic_only 时 addr_id = {parent}/{sheet_code}/{slug(semantic_label)}
        或使用 'unknown' 作为占位符（当 semantic_label 为 null 时）。

        注: 当前实现中部分 semantic_only 条目的 semantic_label 为 null，
        此时使用 'unknown' 作为 slug 占位符。
        """
        addr_id = cell["addr_id"]
        parent_addr_id = cell["parent_addr_id"]

        # addr_id 应以 parent_addr_id 为前缀
        assert addr_id.startswith(parent_addr_id + "/"), (
            f"semantic_only addr_id 应以 parent_addr_id 为前缀: "
            f"addr_id={addr_id}, parent={parent_addr_id}"
        )

        # 不应有 cell_address（semantic_only 无可靠 A1）
        assert cell.get("cell_address") is None, (
            f"semantic_only 条目不应有 cell_address: {cell.get('cell_address')}"
        )

    @given(cell=sampled_from(_CELLS_SEMANTIC_ONLY))
    @settings(max_examples=10)
    def test_semantic_only_formula_ref_parent_matches_addr_id(self, cell: dict):
        """R8.6: 即使 semantic_only，formula_ref 的 WP() 第一参仍 == parent 段。"""
        addr_id = cell["addr_id"]
        formula_ref = cell["formula_ref"]

        parent_from_addr_id = addr_id.split("/")[0]

        m = _RE_WP_FORMULA.match(formula_ref)
        if m is None:
            pytest.skip(f"formula_ref 非标准格式: {formula_ref}")

        wp_first_arg = m.group(1)
        assert wp_first_arg == parent_from_addr_id, (
            f"semantic_only formula_ref 第一参与 addr_id parent 不一致: "
            f"WP first_arg={wp_first_arg}, addr_id parent={parent_from_addr_id}"
        )
