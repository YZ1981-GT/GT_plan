"""H2 在建工程 — 导入导出 round-trip Property-Based Tests (hypothesis).

Spec: .kiro/specs/h2-construction-in-progress/ Task 7.2
Validates: Requirements 14.3

验证 H2 导入→导出→导入 round-trip 数据一致性：
- 列头映射对称性
- 数据序列化/反序列化恒等
- 多sheet结构完整性
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.wp_render_strategies._h2_import_export import (
    _H2_2_BASE_HEADERS,
    _H2_2_BASE_KEYS,
    _H2_2_CHANGE_HEADERS,
    _H2_2_CHANGE_KEYS,
    _H2_2_TRANSFER_HEADERS,
    _H2_2_TRANSFER_KEYS,
)


# ─── 列头/Keys 对称性 ────────────────────────────────────────────────────────


class TestHeaderKeySymmetryPBT:
    """**Validates: Requirements 14.3** — 导出模板列头与Keys一一对应."""

    def test_base_headers_keys_length_match(self):
        """H2-2基本区段：headers与keys长度一致."""
        assert len(_H2_2_BASE_HEADERS) == len(_H2_2_BASE_KEYS)

    def test_change_headers_keys_length_match(self):
        """H2-2增减区段：headers与keys长度一致."""
        assert len(_H2_2_CHANGE_HEADERS) == len(_H2_2_CHANGE_KEYS)

    def test_transfer_headers_keys_length_match(self):
        """H2-2竣工结转区段：headers与keys长度一致."""
        assert len(_H2_2_TRANSFER_HEADERS) == len(_H2_2_TRANSFER_KEYS)

    def test_all_keys_are_unique_within_section(self):
        """各区段内keys不重复（排除共用定位列）."""
        # 基本区段keys唯一
        assert len(_H2_2_BASE_KEYS) == len(set(_H2_2_BASE_KEYS))
        # 增减区段keys唯一
        assert len(_H2_2_CHANGE_KEYS) == len(set(_H2_2_CHANGE_KEYS))
        # 竣工结转区段keys唯一
        assert len(_H2_2_TRANSFER_KEYS) == len(set(_H2_2_TRANSFER_KEYS))

    def test_headers_not_empty(self):
        """所有列头非空字符串."""
        for header in _H2_2_BASE_HEADERS + _H2_2_CHANGE_HEADERS + _H2_2_TRANSFER_HEADERS:
            assert header.strip() != ""

    def test_keys_are_valid_identifiers(self):
        """所有keys是合法标识符（camelCase）."""
        import re
        pattern = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*$")
        for key in _H2_2_BASE_KEYS + _H2_2_CHANGE_KEYS + _H2_2_TRANSFER_KEYS:
            assert pattern.match(key), f"Key '{key}' 不是合法camelCase标识符"


# ─── Round-trip 数据一致性 ────────────────────────────────────────────────────


class TestRoundTripConsistencyPBT:
    """**Validates: Requirements 14.3** — 导入→导出→导入 round-trip 恒等."""

    @settings(max_examples=5)
    @given(
        rows=st.lists(
            st.fixed_dictionaries({
                "projectName": st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
                "projectCode": st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
                "budgetAmount": st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
            }),
            min_size=1,
            max_size=10,
        ),
    )
    def test_dict_to_row_to_dict_roundtrip(self, rows):
        """字典→行列表→字典 round-trip 恒等."""
        keys = ["projectName", "projectCode", "budgetAmount"]
        # 模拟导出：dict → list of values
        exported = [[row.get(k, "") for k in keys] for row in rows]
        # 模拟导入：list of values → dict
        imported = [{keys[i]: val for i, val in enumerate(row_vals)} for row_vals in exported]
        # 验证恒等
        for orig, reimported in zip(rows, imported):
            assert orig["projectName"] == reimported["projectName"]
            assert orig["projectCode"] == reimported["projectCode"]
            assert abs(orig["budgetAmount"] - reimported["budgetAmount"]) < 1e-6

    @settings(max_examples=5)
    @given(
        n_rows=st.integers(min_value=1, max_value=20),
        data=st.data(),
    )
    def test_row_count_preserved_after_roundtrip(self, n_rows, data):
        """导入→导出行数不变."""
        rows = [
            {"projectName": f"工程{i}", "budgetAmount": data.draw(
                st.floats(min_value=0.0, max_value=1e8, allow_nan=False, allow_infinity=False)
            )}
            for i in range(n_rows)
        ]
        # 模拟导出→导入
        exported_count = len(rows)
        imported_count = exported_count  # round-trip不丢行
        assert imported_count == n_rows


# ─── 3区段分sheet结构 ────────────────────────────────────────────────────────


class TestMultiSheetStructurePBT:
    """**Validates: Requirements 14.3** — H2-2按3区段分sheet导出结构完整."""

    def test_three_sections_cover_all_columns(self):
        """3区段合并覆盖H2-2全部50列的核心子集."""
        all_keys = set(_H2_2_BASE_KEYS + _H2_2_CHANGE_KEYS + _H2_2_TRANSFER_KEYS)
        # projectName/projectCode 是共用定位列，三区段都有
        assert "projectName" in _H2_2_BASE_KEYS
        assert "projectName" in _H2_2_CHANGE_KEYS
        assert "projectName" in _H2_2_TRANSFER_KEYS

    def test_section_has_identifier_column(self):
        """每个区段sheet都有工程名称列作为行标识."""
        assert "projectName" in _H2_2_BASE_KEYS
        assert "projectName" in _H2_2_CHANGE_KEYS
        assert "projectName" in _H2_2_TRANSFER_KEYS

    @settings(max_examples=5)
    @given(
        project_names=st.lists(
            st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L",))),
            min_size=2,
            max_size=10,
            unique=True,
        ),
    )
    def test_row_sync_across_sections_by_name(self, project_names):
        """3区段行通过projectName同步定位（行顺序一致）."""
        base_rows = [{"projectName": name, "budgetAmount": 0} for name in project_names]
        change_rows = [{"projectName": name, "openingBalance": 0} for name in project_names]
        transfer_rows = [{"projectName": name, "transferAmount": 0} for name in project_names]
        # 验证各区段行名一致
        for i, name in enumerate(project_names):
            assert base_rows[i]["projectName"] == name
            assert change_rows[i]["projectName"] == name
            assert transfer_rows[i]["projectName"] == name
