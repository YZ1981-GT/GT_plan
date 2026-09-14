"""Tests for 附注语义离线导入兼容 — Task 10.7.

Covers:
- 10.7.1: 旧版离线包继续走现有导入路径（版本检测 legacy）
- 10.7.2: 新版 semantic workbook 增加隐藏 _meta sheet（版本检测 semantic）
- 10.7.3: 用户修改隐藏语义列时标记 structure_conflict
- 10.7.4: 锁定单元格被改时标记 locked_cell_conflict
- 10.7.5: 公式列被改时标记 formula_override_attempt
- 10.7.7: 用例集成测试

Requirements: 12.1, 12.2, 12.3, 12.4
PBT: conflicts always have valid types (max_examples=5)
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_semantic_offline_import import (
    SEMANTIC_META_KEYS,
    VALID_CONFLICT_TYPES,
    ConflictItem,
    ImportConflictResult,
    WorkbookVersion,
    build_semantic_meta,
    detect_import_conflicts,
    detect_workbook_version,
)


# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------


def _make_original_data(
    section_id: str = "section_ar",
    rows: list | None = None,
) -> dict:
    """创建原始导出数据。"""
    if rows is None:
        rows = [
            {"row_id": "row_0", "table_id": "t1", "cells": [100.0, 200.0, "sec_id"]},
            {"row_id": "row_1", "table_id": "t1", "cells": [50.0, 80.0, "sec_id"]},
        ]
    return {"sections": {section_id: {"rows": rows}}}


def _make_imported_data(
    section_id: str = "section_ar",
    rows: list | None = None,
) -> dict:
    """创建导入数据（模拟用户修改后）。"""
    if rows is None:
        rows = [
            {"row_id": "row_0", "table_id": "t1", "cells": [100.0, 200.0, "sec_id"]},
            {"row_id": "row_1", "table_id": "t1", "cells": [50.0, 80.0, "sec_id"]},
        ]
    return {"sections": {section_id: {"rows": rows}}}


def _make_meta(
    cell_modes: dict | None = None,
    formulas: dict | None = None,
    semantic_columns: list | None = None,
) -> dict:
    """创建 meta 数据。"""
    return {
        "cell_modes": cell_modes or {},
        "formulas": formulas or {},
        "semantic_columns": semantic_columns or [],
    }


# ---------------------------------------------------------------------------
# 10.7.1: 旧版离线包兼容 — 版本检测为 legacy
# ---------------------------------------------------------------------------


class TestDetectWorkbookVersionLegacy:
    """旧版离线包版本检测。"""

    def test_empty_workbook_is_legacy(self):
        assert detect_workbook_version({}) == WorkbookVersion.LEGACY

    def test_no_meta_sheet_is_legacy(self):
        data = {"sheets": {"章节清单": {}, "货币资金": {}}}
        assert detect_workbook_version(data) == WorkbookVersion.LEGACY

    def test_empty_meta_is_legacy(self):
        data = {"_meta": {}}
        assert detect_workbook_version(data) == WorkbookVersion.LEGACY

    def test_meta_without_version_keys_is_legacy(self):
        data = {"_meta": {"some_key": "some_value", "export_time": "2025-01-01"}}
        assert detect_workbook_version(data) == WorkbookVersion.LEGACY


# ---------------------------------------------------------------------------
# 10.7.2: 新版 semantic workbook — 版本检测为 semantic
# ---------------------------------------------------------------------------


class TestDetectWorkbookVersionSemantic:
    """新版 semantic workbook 版本检测。"""

    def test_meta_with_workbook_version_is_semantic(self):
        data = {"_meta": {"workbook_version": "2.0"}}
        assert detect_workbook_version(data) == WorkbookVersion.SEMANTIC

    def test_meta_with_template_type_and_semantic_version(self):
        data = {"_meta": {"template_type": "semantic", "semantic_version": "1.0.0"}}
        assert detect_workbook_version(data) == WorkbookVersion.SEMANTIC

    def test_full_semantic_meta(self):
        meta = build_semantic_meta()
        data = {"_meta": meta}
        assert detect_workbook_version(data) == WorkbookVersion.SEMANTIC

    def test_nested_sheets_meta(self):
        """支持 sheets._meta 嵌套格式。"""
        data = {"sheets": {"_meta": {"workbook_version": "2.0", "template_type": "semantic", "semantic_version": "1.0.0"}}}
        assert detect_workbook_version(data) == WorkbookVersion.SEMANTIC

    def test_build_semantic_meta_contains_required_keys(self):
        meta = build_semantic_meta()
        assert "workbook_version" in meta
        assert "template_type" in meta
        assert "semantic_version" in meta


# ---------------------------------------------------------------------------
# 10.7.3: 隐藏语义列被改 — structure_conflict
# ---------------------------------------------------------------------------


class TestStructureConflict:
    """用户修改隐藏语义列时标记 structure_conflict。"""

    def test_semantic_column_modified_triggers_structure_conflict(self):
        original = _make_original_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 200.0, "ar_001"]},
        ])
        imported = _make_imported_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 200.0, "MODIFIED"]},
        ])
        meta = _make_meta(semantic_columns=[2])  # col_idx=2 is semantic

        result = detect_import_conflicts(original, imported, meta)
        assert len(result.structure_conflicts) == 1
        assert result.structure_conflicts[0].conflict_type == "structure_conflict"
        assert result.structure_conflicts[0].old_value == "ar_001"
        assert result.structure_conflicts[0].new_value == "MODIFIED"

    def test_no_conflict_when_semantic_column_unchanged(self):
        original = _make_original_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 200.0, "ar_001"]},
        ])
        imported = _make_imported_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [999.0, 200.0, "ar_001"]},
        ])
        meta = _make_meta(semantic_columns=[2])

        result = detect_import_conflicts(original, imported, meta)
        assert len(result.structure_conflicts) == 0


# ---------------------------------------------------------------------------
# 10.7.4: 锁定单元格被改 — locked_cell_conflict
# ---------------------------------------------------------------------------


class TestLockedCellConflict:
    """锁定单元格被修改时标记 locked_cell_conflict。"""

    def test_locked_cell_modified_triggers_conflict(self):
        original = _make_original_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 200.0]},
        ])
        imported = _make_imported_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 999.0]},
        ])
        # cell "0:1" is locked
        meta = _make_meta(cell_modes={"section_ar": {"0:1": "locked"}})

        result = detect_import_conflicts(original, imported, meta)
        assert len(result.locked_cell_conflicts) == 1
        assert result.locked_cell_conflicts[0].conflict_type == "locked_cell_conflict"
        assert result.locked_cell_conflicts[0].old_value == 200.0
        assert result.locked_cell_conflicts[0].new_value == 999.0

    def test_auto_mode_cell_modified_triggers_locked_conflict(self):
        """auto 模式的单元格也应被视为锁定。"""
        original = _make_original_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [50.0]},
        ])
        imported = _make_imported_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [77.0]},
        ])
        meta = _make_meta(cell_modes={"section_ar": {"0:0": "auto"}})

        result = detect_import_conflicts(original, imported, meta)
        assert len(result.locked_cell_conflicts) == 1

    def test_no_conflict_when_locked_cell_unchanged(self):
        original = _make_original_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0]},
        ])
        imported = _make_imported_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0]},
        ])
        meta = _make_meta(cell_modes={"section_ar": {"0:0": "locked"}})

        result = detect_import_conflicts(original, imported, meta)
        assert len(result.locked_cell_conflicts) == 0


# ---------------------------------------------------------------------------
# 10.7.5: 公式列被改 — formula_override_attempt
# ---------------------------------------------------------------------------


class TestFormulaOverrideAttempt:
    """公式列被修改时标记 formula_override_attempt。"""

    def test_formula_cell_modified_triggers_override(self):
        original = _make_original_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 300.0]},
        ])
        imported = _make_imported_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 500.0]},
        ])
        # cell "0:1" has a formula
        meta = _make_meta(formulas={"section_ar": {"0:1": "=SUM(A1:A10)"}})

        result = detect_import_conflicts(original, imported, meta)
        assert len(result.formula_overrides) == 1
        assert result.formula_overrides[0].conflict_type == "formula_override_attempt"
        assert result.formula_overrides[0].old_value == 300.0
        assert result.formula_overrides[0].new_value == 500.0

    def test_no_conflict_when_formula_cell_unchanged(self):
        original = _make_original_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 300.0]},
        ])
        imported = _make_imported_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 300.0]},
        ])
        meta = _make_meta(formulas={"section_ar": {"0:1": "=SUM(A1:A10)"}})

        result = detect_import_conflicts(original, imported, meta)
        assert len(result.formula_overrides) == 0


# ---------------------------------------------------------------------------
# 10.7.7: 综合用例
# ---------------------------------------------------------------------------


class TestMixedConflicts:
    """综合冲突检测用例。"""

    def test_mixed_conflicts_all_detected(self):
        """一行中同时出现三种冲突类型。"""
        original = _make_original_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 200.0, 300.0, "sid"]},
        ])
        imported = _make_imported_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [999.0, 888.0, 777.0, "CHANGED"]},
        ])
        meta = _make_meta(
            cell_modes={"section_ar": {"0:0": "locked"}},
            formulas={"section_ar": {"0:2": "=A1+B1"}},
            semantic_columns=[3],
        )

        result = detect_import_conflicts(original, imported, meta)
        assert len(result.locked_cell_conflicts) == 1
        assert len(result.formula_overrides) == 1
        assert len(result.structure_conflicts) == 1
        assert result.has_conflicts is True

    def test_content_change_detected_for_normal_cell(self):
        """普通可编辑单元格修改记为 content_change。"""
        original = _make_original_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [100.0, 200.0]},
        ])
        imported = _make_imported_data(rows=[
            {"row_id": "r0", "table_id": "t1", "cells": [999.0, 200.0]},
        ])
        meta = _make_meta()  # no locks, no formulas, no semantic cols

        result = detect_import_conflicts(original, imported, meta)
        assert result.has_conflicts is False
        assert len(result.content_changes) == 1
        assert result.content_changes[0]["type"] == "cell_changed"

    def test_new_section_treated_as_content_change(self):
        """新增 section 不是冲突而是内容变更。"""
        original = _make_original_data()
        imported = {"sections": {
            "section_ar": original["sections"]["section_ar"],
            "section_new": {"rows": [{"cells": [1, 2, 3]}]},
        }}
        meta = _make_meta()

        result = detect_import_conflicts(original, imported, meta)
        assert result.has_conflicts is False
        assert any(c["type"] == "section_added" for c in result.content_changes)

    def test_import_conflict_result_to_dict(self):
        """to_dict 序列化验证。"""
        result = ImportConflictResult(
            content_changes=[{"type": "cell_changed"}],
            structure_conflicts=[ConflictItem(conflict_type="structure_conflict", section_id="s1")],
            locked_cell_conflicts=[],
            formula_overrides=[],
        )
        d = result.to_dict()
        assert "content_changes" in d
        assert "structure_conflicts" in d
        assert "has_conflicts" in d
        assert d["has_conflicts"] is True


# ---------------------------------------------------------------------------
# PBT: conflicts always have valid types (max_examples=5)
# ---------------------------------------------------------------------------


# Strategy: generate random conflict items
_conflict_type_st = st.sampled_from(list(VALID_CONFLICT_TYPES))
_section_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
    min_size=1,
    max_size=20,
)


@st.composite
def conflict_item_st(draw):
    """Generate random ConflictItem."""
    return ConflictItem(
        conflict_type=draw(_conflict_type_st),
        section_id=draw(_section_id_st),
        table_id=draw(st.text(min_size=0, max_size=10)),
        row_id=draw(st.text(min_size=0, max_size=10)),
        col_id=draw(st.text(min_size=0, max_size=10)),
        cell_ref=draw(st.text(min_size=0, max_size=10)),
        old_value=draw(st.one_of(st.none(), st.floats(allow_nan=False), st.text(max_size=10))),
        new_value=draw(st.one_of(st.none(), st.floats(allow_nan=False), st.text(max_size=10))),
    )


class TestConflictTypesPBT:
    """**Validates: Requirements 12.3**

    Property: All conflict items in an ImportConflictResult always have
    a conflict_type from the valid set.
    """

    @given(
        structure=st.lists(conflict_item_st(), min_size=0, max_size=3),
        locked=st.lists(conflict_item_st(), min_size=0, max_size=3),
        formula=st.lists(conflict_item_st(), min_size=0, max_size=3),
    )
    @settings(max_examples=5)
    def test_all_conflicts_have_valid_types(self, structure, locked, formula):
        """All conflicts in result must have valid conflict_type."""
        result = ImportConflictResult(
            content_changes=[],
            structure_conflicts=structure,
            locked_cell_conflicts=locked,
            formula_overrides=formula,
        )
        for conflict in result.all_conflicts:
            assert conflict.conflict_type in VALID_CONFLICT_TYPES, (
                f"Invalid conflict_type: {conflict.conflict_type}"
            )

    @given(item=conflict_item_st())
    @settings(max_examples=5)
    def test_conflict_to_dict_preserves_type(self, item):
        """to_dict must preserve the conflict_type field."""
        d = item.to_dict()
        assert d["conflict_type"] == item.conflict_type
        assert d["conflict_type"] in VALID_CONFLICT_TYPES
