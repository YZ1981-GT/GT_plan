# Feature: acnr, Property 14: addr_id 不可变与版本确定性
"""Property-Based Test: addr_id 不可变与版本确定性（重命名不断边、版本锁定确定）。

**Validates: Requirements 14.3, 19.1, 19.2, 19.5**

Property 14 验证:
1. rename_sheet() 变更 sheet_name 但 NEVER 变更 addr_id（R19.1, R19.2）
2. rename_sheet() 总是把旧名加入 sheet_name_aliases（边保护）
3. validate_addr_id_immutable() 检测 addr_id 移除或不可变字段变更
4. deprecate_entry() 保留 addr_id 同时标记 deprecated
5. 版本确定性：同 registry_version 多次操作产出确定一致结果（R19.5）

Testing framework: hypothesis
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

# 确保 backend 在 sys.path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.immutability import (
    deprecate_entry,
    rename_sheet,
    validate_addr_id_immutable,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 有效循环前缀
_CYCLES = list("ABCDEFGHIJKLMNS")

# sheet_code: 如 D2-2, F3-1, K10
_sheet_code_st = st.from_regex(r"[A-S]\d{1,2}(-\d{1,2})?", fullmatch=True)

# parent_wp_code: 如 D2, F3, K10
_parent_wp_code_st = st.from_regex(r"[A-S]\d{1,2}", fullmatch=True)

# sheet_name: 中文名称（2~15 字符）
_sheet_name_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        min_codepoint=0x30,
        max_codepoint=0x9FFF,
    ),
    min_size=2,
    max_size=15,
)

# cell_address: A1 样式地址
_cell_address_st = st.from_regex(r"[A-Z]{1,2}\d{1,3}", fullmatch=True)

# registry_version: 时间戳式版本号
_registry_version_st = st.from_regex(r"20[23]\d{10}", fullmatch=True)

# aliases: 别名列表（0~3 条）
_aliases_st = st.lists(_sheet_name_st, min_size=0, max_size=3)


@st.composite
def sheet_catalog_entry_strategy(draw: st.DrawFn) -> dict:
    """生成一条随机 SheetCatalogEntry。"""
    parent = draw(_parent_wp_code_st)
    sheet_code = draw(_sheet_code_st)
    addr_id = f"{parent}/{sheet_code}"
    sheet_name = draw(_sheet_name_st)
    assume(len(sheet_name.strip()) > 0)

    aliases = draw(_aliases_st)
    # 确保别名中不含当前 sheet_name
    aliases = [a for a in aliases if a != sheet_name and len(a.strip()) > 0]

    return {
        "addr_id": addr_id,
        "domain": "wp",
        "parent_wp_code": parent,
        "sheet_code": sheet_code,
        "sheet_name": sheet_name,
        "sheet_name_aliases": aliases,
        "component_type": f"{parent.lower()}-detail",
        "registry_version": draw(_registry_version_st),
    }


@st.composite
def cell_catalog_entry_strategy(draw: st.DrawFn, parent_addr_id: str | None = None) -> dict:
    """生成一条随机 CellCatalogEntry。"""
    if parent_addr_id is None:
        parent = draw(_parent_wp_code_st)
        sheet_code = draw(_sheet_code_st)
        parent_addr_id = f"{parent}/{sheet_code}"
    cell = draw(_cell_address_st)
    addr_id = f"{parent_addr_id}/{cell}"
    return {
        "addr_id": addr_id,
        "parent_addr_id": parent_addr_id,
        "domain": "wp",
        "cell_address": cell,
        "formula_ref": f"WP('{parent_addr_id.split('/')[0]}','{parent_addr_id}','{cell}')",
        "uri": f"wp://{parent_addr_id}#{cell}",
        "registry_version": draw(_registry_version_st),
    }


@st.composite
def catalog_strategy(draw: st.DrawFn) -> dict:
    """生成包含 1~4 个 sheet 条目及对应 cell 条目的 catalog。"""
    sheets = draw(st.lists(sheet_catalog_entry_strategy(), min_size=1, max_size=4))

    # 确保 addr_id 唯一
    seen_ids: set[str] = set()
    unique_sheets: list[dict] = []
    for s in sheets:
        if s["addr_id"] not in seen_ids:
            seen_ids.add(s["addr_id"])
            unique_sheets.append(s)
    assume(len(unique_sheets) >= 1)

    cells: list[dict] = []
    for s in unique_sheets:
        n_cells = draw(st.integers(min_value=0, max_value=2))
        for _ in range(n_cells):
            cell = draw(cell_catalog_entry_strategy(parent_addr_id=s["addr_id"]))
            if cell["addr_id"] not in seen_ids:
                seen_ids.add(cell["addr_id"])
                cells.append(cell)

    version = draw(_registry_version_st)
    return {
        "version": "1",
        "registry_version": version,
        "sheets": unique_sheets,
        "cells": cells,
    }


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestAddrIdImmutabilityAndVersionDeterminism:
    """Property 14: addr_id 不可变与版本确定性。

    Validates: Requirements 14.3, 19.1, 19.2, 19.5
    """

    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    @given(
        catalog=catalog_strategy(),
        new_name=_sheet_name_st,
    )
    def test_rename_sheet_never_changes_addr_id(
        self,
        catalog: dict,
        new_name: str,
    ):
        """R19.1 + R19.2: rename_sheet() 变更 sheet_name 但 addr_id 不变。

        Property: ∀ catalog, ∀ sheet entry, ∀ new_name:
          rename_sheet(catalog, addr_id, new_name).addr_id == original.addr_id
          ∧ rename_sheet 不变更 parent_wp_code 或 sheet_code

        **Validates: Requirements 19.1, 19.2**
        """
        assume(len(new_name.strip()) > 0)
        assume(len(catalog["sheets"]) > 0)

        target = catalog["sheets"][0]
        original_addr_id = target["addr_id"]
        original_parent = target["parent_wp_code"]
        original_sheet_code = target["sheet_code"]

        result = rename_sheet(catalog, original_addr_id, new_name)

        # 找到更新后的条目
        updated = next(
            s for s in result["sheets"] if s["addr_id"] == original_addr_id
        )

        # addr_id 不变
        assert updated["addr_id"] == original_addr_id, (
            f"addr_id 被修改: {original_addr_id} → {updated['addr_id']}"
        )
        # 不可变字段不变
        assert updated["parent_wp_code"] == original_parent
        assert updated["sheet_code"] == original_sheet_code

    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    @given(
        catalog=catalog_strategy(),
        new_name=_sheet_name_st,
    )
    def test_rename_sheet_old_name_enters_aliases(
        self,
        catalog: dict,
        new_name: str,
    ):
        """R19.2: rename_sheet() 总是把旧名写入 sheet_name_aliases（边保护）。

        Property: ∀ catalog, ∀ sheet entry, ∀ new_name ≠ old_name:
          old_name ∈ rename_sheet(catalog, addr_id, new_name).sheet_name_aliases

        **Validates: Requirements 19.2**
        """
        assume(len(new_name.strip()) > 0)
        assume(len(catalog["sheets"]) > 0)

        target = catalog["sheets"][0]
        original_addr_id = target["addr_id"]
        old_name = target["sheet_name"]

        # 只测试实际发生更名的情况
        assume(old_name != new_name)
        assume(len(old_name.strip()) > 0)

        result = rename_sheet(catalog, original_addr_id, new_name)

        updated = next(
            s for s in result["sheets"] if s["addr_id"] == original_addr_id
        )

        # 旧名在 aliases 中
        assert old_name in updated["sheet_name_aliases"], (
            f"旧名 '{old_name}' 未进入 aliases: {updated['sheet_name_aliases']}"
        )
        # 新名被设置
        assert updated["sheet_name"] == new_name

    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    @given(catalog=catalog_strategy())
    def test_validate_detects_addr_id_removal(
        self,
        catalog: dict,
    ):
        """R19.1: validate_addr_id_immutable() 检测 addr_id 被移除。

        Property: ∀ catalog with ≥1 non-deprecated sheet,
          移除一条 sheet 后 validate 返回 type="removed" 违规

        **Validates: Requirements 19.1**
        """
        assume(len(catalog["sheets"]) > 0)

        # 确保至少有一条非 deprecated 的 sheet
        non_deprecated = [
            s for s in catalog["sheets"] if not s.get("deprecated")
        ]
        assume(len(non_deprecated) > 0)

        # 构造新 catalog：移除第一条非 deprecated sheet
        removed_addr_id = non_deprecated[0]["addr_id"]
        new_catalog = deepcopy(catalog)
        new_catalog["sheets"] = [
            s for s in new_catalog["sheets"]
            if s["addr_id"] != removed_addr_id
        ]

        violations = validate_addr_id_immutable(catalog, new_catalog)

        # 必须检测到移除
        assert len(violations) > 0, (
            f"移除了 addr_id='{removed_addr_id}' 但 validate 未检测到"
        )
        removed_violations = [
            v for v in violations
            if v["type"] == "removed" and v["addr_id"] == removed_addr_id
        ]
        assert len(removed_violations) == 1

    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    @given(
        catalog=catalog_strategy(),
        new_parent=_parent_wp_code_st,
    )
    def test_validate_detects_immutable_field_change(
        self,
        catalog: dict,
        new_parent: str,
    ):
        """R19.1: validate_addr_id_immutable() 检测不可变字段变更。

        Property: ∀ catalog, 修改 parent_wp_code 后 validate 返回
          type="value_changed" 违规

        **Validates: Requirements 19.1**
        """
        assume(len(catalog["sheets"]) > 0)

        target = catalog["sheets"][0]
        original_parent = target["parent_wp_code"]
        # 确保新值不同
        assume(new_parent != original_parent)

        new_catalog = deepcopy(catalog)
        for s in new_catalog["sheets"]:
            if s["addr_id"] == target["addr_id"]:
                s["parent_wp_code"] = new_parent
                break

        violations = validate_addr_id_immutable(catalog, new_catalog)

        assert len(violations) > 0, (
            f"修改了 parent_wp_code ({original_parent}→{new_parent}) "
            f"但 validate 未检测到"
        )
        changed_violations = [
            v for v in violations
            if v["type"] == "value_changed" and v["addr_id"] == target["addr_id"]
        ]
        assert len(changed_violations) >= 1

    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    @given(
        catalog=catalog_strategy(),
        version=_registry_version_st,
    )
    def test_deprecate_preserves_addr_id(
        self,
        catalog: dict,
        version: str,
    ):
        """R19.3: deprecate_entry() 标记 deprecated 但保留 addr_id。

        Property: ∀ catalog entry,
          deprecate_entry(catalog, addr_id, version).addr_id == original.addr_id
          ∧ entry.deprecated == True
          ∧ entry.deprecated_at_version == version

        **Validates: Requirements 14.3, 19.1**
        """
        assume(len(catalog["sheets"]) > 0)

        target = catalog["sheets"][0]
        original_addr_id = target["addr_id"]

        result = deprecate_entry(catalog, original_addr_id, version)

        # 找到更新后的条目
        updated = next(
            s for s in result["sheets"] if s["addr_id"] == original_addr_id
        )

        # addr_id 不变
        assert updated["addr_id"] == original_addr_id
        # 标记 deprecated
        assert updated["deprecated"] is True
        assert updated["deprecated_at_version"] == version
        # 不可变字段仍然完整
        assert updated["parent_wp_code"] == target["parent_wp_code"]
        assert updated["sheet_code"] == target["sheet_code"]

    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    @given(
        catalog=catalog_strategy(),
        new_name=_sheet_name_st,
    )
    def test_version_determinism_rename_idempotent(
        self,
        catalog: dict,
        new_name: str,
    ):
        """R19.5: 同 registry_version 多次操作产出确定一致结果。

        Property: ∀ catalog, ∀ new_name:
          rename_sheet(catalog, addr_id, name) 运行两次结果完全一致

        **Validates: Requirements 19.5**
        """
        assume(len(new_name.strip()) > 0)
        assume(len(catalog["sheets"]) > 0)

        target = catalog["sheets"][0]
        addr_id = target["addr_id"]

        result1 = rename_sheet(catalog, addr_id, new_name)
        result2 = rename_sheet(catalog, addr_id, new_name)

        # 两次执行结果必须完全一致
        assert result1 == result2, (
            "同输入两次 rename_sheet 结果不一致（版本确定性违规）"
        )
