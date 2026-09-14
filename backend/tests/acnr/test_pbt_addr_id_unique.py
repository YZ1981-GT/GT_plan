"""Property-based test for addr_id global uniqueness.

# Feature: acnr, Property 1: addr_id 全局唯一且每物理格唯一

**Validates: Requirements 8.5, 18.4, 24.4**

验证 global_catalog.json 中：
1. 所有 addr_id（sheets + cells）全局唯一，无重复
2. 任一 CellCatalogEntry 的物理格三元组（parent_wp_code, sheet_code, cell_address）
   最多对应一个 canonical addr_id
3. SheetCatalogEntry 的 addr_id 与 CellCatalogEntry 的 addr_id 无碰撞
4. 应用 overrides 后唯一性仍然成立
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

# ---------------------------------------------------------------------------
# Fixtures: 加载 catalog 数据
# ---------------------------------------------------------------------------

_CATALOG_PATH = _BACKEND_ROOT / "data" / "acnr" / "global_catalog.json"
_OVERRIDES_PATH = _BACKEND_ROOT / "data" / "acnr" / "global_catalog.overrides.json"


@pytest.fixture(scope="module")
def catalog_data() -> dict:
    """加载 global_catalog.json 并返回解析后的 dict。"""
    assert _CATALOG_PATH.exists(), f"global_catalog.json not found at {_CATALOG_PATH}"
    with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def all_sheets(catalog_data: dict) -> list[dict]:
    """提取 sheets 数组。"""
    sheets = catalog_data.get("sheets", [])
    assert len(sheets) > 0, "catalog sheets 为空"
    return sheets


@pytest.fixture(scope="module")
def all_cells(catalog_data: dict) -> list[dict]:
    """提取 cells 数组。"""
    cells = catalog_data.get("cells", [])
    assert len(cells) > 0, "catalog cells 为空"
    return cells


@pytest.fixture(scope="module")
def all_addr_ids(all_sheets: list[dict], all_cells: list[dict]) -> list[str]:
    """收集全部 addr_id（sheets + cells）。"""
    sheet_ids = [s["addr_id"] for s in all_sheets]
    cell_ids = [c["addr_id"] for c in all_cells]
    return sheet_ids + cell_ids


@pytest.fixture(scope="module")
def overrides_data() -> dict:
    """加载 global_catalog.overrides.json。"""
    if not _OVERRIDES_PATH.exists():
        return {"overrides": []}
    with open(_OVERRIDES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Strategies: 从实际 catalog 随机抽样验证
# ---------------------------------------------------------------------------


def sheet_index_strategy(all_sheets):
    """从 sheets 数组中随机选取索引。"""
    return st.integers(min_value=0, max_value=len(all_sheets) - 1)


def cell_index_strategy(all_cells):
    """从 cells 数组中随机选取索引。"""
    return st.integers(min_value=0, max_value=len(all_cells) - 1)


# ---------------------------------------------------------------------------
# Property Test: addr_id 全局唯一且每物理格唯一
# ---------------------------------------------------------------------------


class TestAddrIdGlobalUniqueness:
    """Property 1: addr_id 全局唯一且每物理格唯一。

    Validates: Requirements 8.5, 18.4, 24.4
    """

    def test_all_addr_ids_globally_unique(self, all_addr_ids: list[str]):
        """全部 addr_id 互不重复（R18.4, R24.4）。

        Property: ∀ i,j ∈ catalog.addr_ids, i ≠ j → addr_id[i] ≠ addr_id[j]
        """
        seen: dict[str, int] = {}
        duplicates: list[str] = []
        for addr_id in all_addr_ids:
            if addr_id in seen:
                duplicates.append(addr_id)
            else:
                seen[addr_id] = 1

        assert len(duplicates) == 0, (
            f"发现 {len(duplicates)} 个重复 addr_id: {duplicates[:10]}"
        )

    def test_no_cell_addr_id_collides_with_sheet(
        self, all_sheets: list[dict], all_cells: list[dict]
    ):
        """SheetCatalogEntry addr_id 与 CellCatalogEntry addr_id 无碰撞（R8.5）。

        Property: sheet_addr_ids ∩ cell_addr_ids = ∅
        """
        sheet_ids = {s["addr_id"] for s in all_sheets}
        cell_ids = {c["addr_id"] for c in all_cells}
        collisions = sheet_ids & cell_ids

        assert len(collisions) == 0, (
            f"Sheet 与 Cell addr_id 碰撞: {collisions}"
        )

    def test_physical_cell_has_unique_canonical_addr_id(
        self, all_cells: list[dict]
    ):
        """每物理格（parent_wp_code + sheet_code 推导 + cell_address）最多一个
        canonical addr_id（R8.5）。

        Property: ∀ cell entries with cell_address →
          (parent_addr_id, cell_address) 三元组唯一对应一个 addr_id
        """
        # 物理格以 (parent_addr_id, cell_address) 标识
        physical_map: dict[tuple[str, str], str] = {}
        violations: list[str] = []

        for cell in all_cells:
            cell_address = cell.get("cell_address")
            if cell_address is None:
                # semantic_only 条目无 cell_address，跳过物理格校验
                continue

            parent_addr_id = cell["parent_addr_id"]
            key = (parent_addr_id, cell_address)

            if key in physical_map:
                existing = physical_map[key]
                violations.append(
                    f"物理格 {key} 有两个 addr_id: "
                    f"'{existing}' 与 '{cell['addr_id']}'"
                )
            else:
                physical_map[key] = cell["addr_id"]

        assert len(violations) == 0, (
            f"发现 {len(violations)} 个物理格双主键违反:\n"
            + "\n".join(violations[:10])
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=st.data())
    def test_random_sheet_addr_id_unique_in_set(
        self, data, all_sheets: list[dict], all_addr_ids: list[str]
    ):
        """随机抽取 sheet 条目，其 addr_id 在全局 addr_id 集合中恰好出现一次。

        Property: ∀ sheet ∈ catalog.sheets →
          count(addr_id == sheet.addr_id) == 1 in all_addr_ids
        """
        idx = data.draw(st.integers(min_value=0, max_value=len(all_sheets) - 1))
        sheet = all_sheets[idx]
        addr_id = sheet["addr_id"]

        count = sum(1 for a in all_addr_ids if a == addr_id)
        assert count == 1, (
            f"Sheet addr_id '{addr_id}' 在全局列表中出现 {count} 次，期望恰好 1 次"
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=st.data())
    def test_random_cell_addr_id_unique_in_set(
        self, data, all_cells: list[dict], all_addr_ids: list[str]
    ):
        """随机抽取 cell 条目，其 addr_id 在全局 addr_id 集合中恰好出现一次。

        Property: ∀ cell ∈ catalog.cells →
          count(addr_id == cell.addr_id) == 1 in all_addr_ids
        """
        idx = data.draw(st.integers(min_value=0, max_value=len(all_cells) - 1))
        cell = all_cells[idx]
        addr_id = cell["addr_id"]

        count = sum(1 for a in all_addr_ids if a == addr_id)
        assert count == 1, (
            f"Cell addr_id '{addr_id}' 在全局列表中出现 {count} 次，期望恰好 1 次"
        )

    def test_uniqueness_holds_after_overrides(
        self, all_addr_ids: list[str], overrides_data: dict
    ):
        """应用 overrides 后唯一性仍然成立。

        Property: catalog_addr_ids ∪ override_addr_ids 仍全局唯一
        """
        overrides = overrides_data.get("overrides", [])

        # 收集 overrides 中新增的 addr_id（如果有）
        override_addr_ids: list[str] = []
        for ovr in overrides:
            if "addr_id" in ovr:
                override_addr_ids.append(ovr["addr_id"])

        # 合并后检查唯一性
        combined = all_addr_ids + override_addr_ids
        seen: set[str] = set()
        duplicates: list[str] = []
        for addr_id in combined:
            if addr_id in seen:
                duplicates.append(addr_id)
            seen.add(addr_id)

        assert len(duplicates) == 0, (
            f"应用 overrides 后发现重复 addr_id: {duplicates[:10]}"
        )
