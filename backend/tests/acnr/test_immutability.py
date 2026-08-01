"""Tests for ACNR addr_id 不可变政策 + registry_version 处理

Covers:
- R19.1: addr_id 不可变校验
- R19.2: 重命名政策（旧名 → aliases，addr_id 不变）
- R19.3: 弃用政策（deprecated + 保留 ≥1 version）
- R19.4: 归档项目 registry_version 记录

Requirements: 19.1, 19.2, 19.3, 19.4
"""
from __future__ import annotations

import pytest

from app.services.acnr.immutability import (
    AddrIdImmutabilityError,
    check_addr_id_immutable,
    clear_all_project_versions,
    deprecate_entry,
    get_project_registry_version,
    is_safe_to_remove,
    list_archived_projects,
    record_project_registry_version,
    remove_project_registry_version,
    rename_sheet,
    validate_addr_id_immutable,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def base_catalog() -> dict:
    """基础 catalog 结构，包含 2 sheet + 2 cell 条目。"""
    return {
        "version": "1",
        "registry_version": "20260710102744",
        "sheets": [
            {
                "addr_id": "D2/D2-2",
                "domain": "wp",
                "parent_wp_code": "D2",
                "sheet_code": "D2-2",
                "sheet_name": "明细表D2-2",
                "sheet_name_aliases": ["应收账款明细"],
                "cycle": "D",
                "registry_version": "20260710102744",
            },
            {
                "addr_id": "D2/D2-3",
                "domain": "wp",
                "parent_wp_code": "D2",
                "sheet_code": "D2-3",
                "sheet_name": "账龄分析表D2-3",
                "sheet_name_aliases": [],
                "cycle": "D",
                "registry_version": "20260710102744",
            },
        ],
        "cells": [
            {
                "addr_id": "D2/D2-2/E100",
                "parent_addr_id": "D2/D2-2",
                "cell_address": "E100",
                "domain": "wp",
                "semantic_label": "合计行-期末余额",
                "formula_ref": "WP('D2','明细表D2-2','E100')",
                "uri": "wp://D2/明细表D2-2#E100",
                "registry_version": "20260710102744",
            },
            {
                "addr_id": "D2/D2-2/F100",
                "parent_addr_id": "D2/D2-2",
                "cell_address": "F100",
                "domain": "wp",
                "semantic_label": "合计行-期初余额",
                "formula_ref": "WP('D2','明细表D2-2','F100')",
                "uri": "wp://D2/明细表D2-2#F100",
                "registry_version": "20260710102744",
            },
        ],
    }


@pytest.fixture(autouse=True)
def _clean_project_versions():
    """每个测试后清理项目版本记录。"""
    yield
    clear_all_project_versions()


# ─── R19.1: addr_id 不可变校验 ───────────────────────────────────────────────


class TestAddrIdImmutability:
    """R19.1: addr_id 不可变校验。"""

    def test_no_violations_when_identical(self, base_catalog: dict):
        """相同 catalog 无违规。"""
        violations = validate_addr_id_immutable(base_catalog, base_catalog)
        assert violations == []

    def test_sheet_removed_is_violation(self, base_catalog: dict):
        """sheet 条目被移除 → 违规。"""
        new = {
            "version": "1",
            "registry_version": "20260711000000",
            "sheets": [base_catalog["sheets"][0]],  # 只保留第一个
            "cells": base_catalog["cells"],
        }
        violations = validate_addr_id_immutable(base_catalog, new)
        assert len(violations) == 1
        assert violations[0]["type"] == "removed"
        assert violations[0]["addr_id"] == "D2/D2-3"

    def test_cell_removed_is_violation(self, base_catalog: dict):
        """cell 条目被移除 → 违规。"""
        new = {
            "version": "1",
            "registry_version": "20260711000000",
            "sheets": base_catalog["sheets"],
            "cells": [base_catalog["cells"][0]],  # 只保留第一个
        }
        violations = validate_addr_id_immutable(base_catalog, new)
        assert len(violations) == 1
        assert violations[0]["type"] == "removed"
        assert violations[0]["addr_id"] == "D2/D2-2/F100"

    def test_sheet_code_changed_is_violation(self, base_catalog: dict):
        """sheet_code 变更 → 违规。"""
        import copy
        new = copy.deepcopy(base_catalog)
        new["sheets"][0]["sheet_code"] = "D2-2-new"
        violations = validate_addr_id_immutable(base_catalog, new)
        assert len(violations) == 1
        assert violations[0]["type"] == "value_changed"
        assert "sheet_code" in violations[0]["detail"]

    def test_parent_wp_code_changed_is_violation(self, base_catalog: dict):
        """parent_wp_code 变更 → 违规。"""
        import copy
        new = copy.deepcopy(base_catalog)
        new["sheets"][0]["parent_wp_code"] = "D3"
        violations = validate_addr_id_immutable(base_catalog, new)
        assert len(violations) == 1
        assert violations[0]["type"] == "value_changed"
        assert "parent_wp_code" in violations[0]["detail"]

    def test_cell_address_changed_is_violation(self, base_catalog: dict):
        """cell_address 变更 → 违规。"""
        import copy
        new = copy.deepcopy(base_catalog)
        new["cells"][0]["cell_address"] = "E200"
        violations = validate_addr_id_immutable(base_catalog, new)
        assert len(violations) == 1
        assert violations[0]["type"] == "value_changed"
        assert "cell_address" in violations[0]["detail"]

    def test_deprecated_entry_removal_allowed(self, base_catalog: dict):
        """deprecated 条目移除不触发违规。"""
        import copy
        old = copy.deepcopy(base_catalog)
        old["sheets"][1]["deprecated"] = True  # D2/D2-3 标记为 deprecated

        new = {
            "version": "1",
            "registry_version": "20260711000000",
            "sheets": [base_catalog["sheets"][0]],  # 移除 D2/D2-3
            "cells": base_catalog["cells"],
        }
        violations = validate_addr_id_immutable(old, new)
        assert violations == []

    def test_adding_new_entries_allowed(self, base_catalog: dict):
        """新增条目不违规。"""
        import copy
        new = copy.deepcopy(base_catalog)
        new["sheets"].append({
            "addr_id": "D2/D2-4",
            "parent_wp_code": "D2",
            "sheet_code": "D2-4",
            "sheet_name": "新增表",
        })
        violations = validate_addr_id_immutable(base_catalog, new)
        assert violations == []

    def test_sheet_name_change_allowed(self, base_catalog: dict):
        """sheet_name 变更不违规（改名走 aliases）。"""
        import copy
        new = copy.deepcopy(base_catalog)
        new["sheets"][0]["sheet_name"] = "新明细表D2-2"
        violations = validate_addr_id_immutable(base_catalog, new)
        assert violations == []

    def test_check_raises_on_violations(self, base_catalog: dict):
        """check_addr_id_immutable 违规时 raise。"""
        new = {
            "version": "1",
            "registry_version": "20260711000000",
            "sheets": [],
            "cells": [],
        }
        with pytest.raises(AddrIdImmutabilityError) as exc_info:
            check_addr_id_immutable(base_catalog, new)
        assert len(exc_info.value.violations) > 0

    def test_check_passes_when_valid(self, base_catalog: dict):
        """check_addr_id_immutable 无违规时不 raise。"""
        check_addr_id_immutable(base_catalog, base_catalog)  # should not raise

    def test_multiple_violations_collected(self, base_catalog: dict):
        """多个违规同时检出。"""
        new = {
            "version": "1",
            "registry_version": "20260711000000",
            "sheets": [],  # 移除所有 sheet
            "cells": base_catalog["cells"],
        }
        violations = validate_addr_id_immutable(base_catalog, new)
        assert len(violations) == 2  # D2/D2-2 + D2/D2-3


# ─── R19.2: 重命名政策 ──────────────────────────────────────────────────────


class TestRenameSheet:
    """R19.2: sheet 改名走 aliases，addr_id 不变。"""

    def test_rename_updates_sheet_name(self, base_catalog: dict):
        """重命名后 sheet_name 更新。"""
        result = rename_sheet(base_catalog, "D2/D2-2", "应收账款明细表D2-2")
        target = next(s for s in result["sheets"] if s["addr_id"] == "D2/D2-2")
        assert target["sheet_name"] == "应收账款明细表D2-2"

    def test_rename_preserves_addr_id(self, base_catalog: dict):
        """重命名后 addr_id 不变。"""
        result = rename_sheet(base_catalog, "D2/D2-2", "新名称")
        target = next(s for s in result["sheets"] if s["addr_id"] == "D2/D2-2")
        assert target["addr_id"] == "D2/D2-2"

    def test_rename_adds_old_name_to_aliases(self, base_catalog: dict):
        """旧权威名追加到 aliases。"""
        result = rename_sheet(base_catalog, "D2/D2-2", "新名称")
        target = next(s for s in result["sheets"] if s["addr_id"] == "D2/D2-2")
        assert "明细表D2-2" in target["sheet_name_aliases"]

    def test_rename_preserves_existing_aliases(self, base_catalog: dict):
        """重命名保留已有的 aliases。"""
        result = rename_sheet(base_catalog, "D2/D2-2", "新名称")
        target = next(s for s in result["sheets"] if s["addr_id"] == "D2/D2-2")
        assert "应收账款明细" in target["sheet_name_aliases"]

    def test_rename_no_duplicate_aliases(self, base_catalog: dict):
        """旧名已在 aliases 中时不重复追加。"""
        import copy
        cat = copy.deepcopy(base_catalog)
        cat["sheets"][0]["sheet_name_aliases"] = ["明细表D2-2", "应收账款明细"]
        result = rename_sheet(cat, "D2/D2-2", "新名称")
        target = next(s for s in result["sheets"] if s["addr_id"] == "D2/D2-2")
        assert target["sheet_name_aliases"].count("明细表D2-2") == 1

    def test_rename_same_name_noop(self, base_catalog: dict):
        """名称未变时无操作。"""
        result = rename_sheet(base_catalog, "D2/D2-2", "明细表D2-2")
        target = next(s for s in result["sheets"] if s["addr_id"] == "D2/D2-2")
        # aliases 不应新增旧名
        assert target["sheet_name_aliases"] == ["应收账款明细"]

    def test_rename_nonexistent_raises(self, base_catalog: dict):
        """不存在的 addr_id 抛出 ValueError。"""
        with pytest.raises(ValueError, match="not found"):
            rename_sheet(base_catalog, "D2/D2-99", "新名称")

    def test_rename_does_not_mutate_original(self, base_catalog: dict):
        """rename_sheet 不修改原始 catalog。"""
        import copy
        original = copy.deepcopy(base_catalog)
        rename_sheet(base_catalog, "D2/D2-2", "新名称")
        assert base_catalog == original


# ─── R19.3: 弃用政策 ────────────────────────────────────────────────────────


class TestDeprecateEntry:
    """R19.3: deprecated 标记 + 保留判断。"""

    def test_deprecate_sheet(self, base_catalog: dict):
        """标记 sheet 为 deprecated。"""
        result = deprecate_entry(base_catalog, "D2/D2-3", "20260711000000")
        target = next(s for s in result["sheets"] if s["addr_id"] == "D2/D2-3")
        assert target["deprecated"] is True
        assert target["deprecated_at_version"] == "20260711000000"

    def test_deprecate_cell(self, base_catalog: dict):
        """标记 cell 为 deprecated。"""
        result = deprecate_entry(base_catalog, "D2/D2-2/E100", "20260711000000")
        target = next(c for c in result["cells"] if c["addr_id"] == "D2/D2-2/E100")
        assert target["deprecated"] is True
        assert target["deprecated_at_version"] == "20260711000000"

    def test_deprecate_already_deprecated_noop(self, base_catalog: dict):
        """已 deprecated 的条目重复调用无变化。"""
        import copy
        cat = copy.deepcopy(base_catalog)
        cat["sheets"][1]["deprecated"] = True
        cat["sheets"][1]["deprecated_at_version"] = "20260710000000"

        result = deprecate_entry(cat, "D2/D2-3", "20260711000000")
        target = next(s for s in result["sheets"] if s["addr_id"] == "D2/D2-3")
        # 保持原版本号
        assert target["deprecated_at_version"] == "20260710000000"

    def test_deprecate_nonexistent_raises(self, base_catalog: dict):
        """不存在的 addr_id 抛出 ValueError。"""
        with pytest.raises(ValueError, match="not found"):
            deprecate_entry(base_catalog, "D2/D2-99", "20260711000000")

    def test_deprecate_does_not_mutate_original(self, base_catalog: dict):
        """deprecate_entry 不修改原始 catalog。"""
        import copy
        original = copy.deepcopy(base_catalog)
        deprecate_entry(base_catalog, "D2/D2-3", "20260711000000")
        assert base_catalog == original

    def test_is_safe_to_remove_after_one_version(self):
        """deprecated 条目跨版本后可安全移除。"""
        entry = {
            "addr_id": "D2/D2-3",
            "deprecated": True,
            "deprecated_at_version": "20260710000000",
        }
        # 当前版本 > deprecated_at_version
        assert is_safe_to_remove(entry, "20260711000000") is True

    def test_is_safe_to_remove_same_version(self):
        """deprecated 条目同版本不可移除。"""
        entry = {
            "addr_id": "D2/D2-3",
            "deprecated": True,
            "deprecated_at_version": "20260710000000",
        }
        assert is_safe_to_remove(entry, "20260710000000") is False

    def test_is_safe_to_remove_not_deprecated(self):
        """非 deprecated 条目不可移除。"""
        entry = {"addr_id": "D2/D2-3"}
        assert is_safe_to_remove(entry, "20260711000000") is False

    def test_is_safe_to_remove_no_version_recorded(self):
        """deprecated 但无版本记录 → 保守不移除。"""
        entry = {"addr_id": "D2/D2-3", "deprecated": True}
        assert is_safe_to_remove(entry, "20260711000000") is False


# ─── R19.4: 归档项目 registry_version 记录 ─────────────────────────────────


class TestProjectRegistryVersion:
    """R19.4: 归档项目记录 registry_version。"""

    def test_record_and_get(self):
        """记录并获取项目 registry_version。"""
        record_project_registry_version("proj-001", "20260710102744")
        assert get_project_registry_version("proj-001") == "20260710102744"

    def test_get_nonexistent_returns_none(self):
        """未记录的项目返回 None。"""
        assert get_project_registry_version("proj-999") is None

    def test_record_overwrites(self):
        """重复记录覆盖旧值。"""
        record_project_registry_version("proj-001", "20260710000000")
        record_project_registry_version("proj-001", "20260711000000")
        assert get_project_registry_version("proj-001") == "20260711000000"

    def test_remove_version(self):
        """移除项目 registry_version 记录。"""
        record_project_registry_version("proj-001", "20260710102744")
        assert remove_project_registry_version("proj-001") is True
        assert get_project_registry_version("proj-001") is None

    def test_remove_nonexistent(self):
        """移除不存在的项目返回 False。"""
        assert remove_project_registry_version("proj-999") is False

    def test_list_archived_projects(self):
        """列出所有归档项目。"""
        record_project_registry_version("proj-001", "20260710000000")
        record_project_registry_version("proj-002", "20260711000000")
        result = list_archived_projects()
        assert result == {
            "proj-001": "20260710000000",
            "proj-002": "20260711000000",
        }

    def test_clear_all(self):
        """清除全部记录。"""
        record_project_registry_version("proj-001", "20260710000000")
        clear_all_project_versions()
        assert list_archived_projects() == {}
