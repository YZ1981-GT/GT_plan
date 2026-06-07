"""Tests for backend/app/services/note_table_col_id_service.py

验证：
1. 稳定 table_id 生成（基于表名 / 位置回退 / 唯一性）
2. 稳定 col_id 生成（基于列头 / 位置回退 / 唯一性）
3. 列重命名后 col_id 不变（已有 col_id 优先）
4. col_id 解析与回退
5. 幂等性
6. PBT: ensure_table_ids 总产出非空 table_id

Validates: Requirements 3.1, 3.3
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_table_col_id_service import (
    _make_unique,
    _slugify,
    ensure_column_ids,
    ensure_table_ids,
    resolve_col_reference,
)


# ===========================================================================
# 4.1 ensure_table_ids 测试
# ===========================================================================


class TestEnsureTableIds:
    """table_id 生成测试"""

    def test_generates_table_id_from_name(self) -> None:
        """表有 name → slugify 生成 table_id"""
        table_data = {
            "_tables": [
                {"name": "账龄分析", "rows": []},
            ]
        }
        result = ensure_table_ids(table_data)
        tid = result["_tables"][0]["table_id"]
        assert tid
        assert isinstance(tid, str)
        assert "账龄分析" in tid or tid == "账龄分析"

    def test_generates_table_id_from_position_when_no_name(self) -> None:
        """表无 name → 用 table_{idx}"""
        table_data = {
            "_tables": [
                {"rows": []},
                {"name": "", "rows": []},
            ]
        }
        result = ensure_table_ids(table_data)
        assert result["_tables"][0]["table_id"] == "table_0"
        assert result["_tables"][1]["table_id"] == "table_1"

    def test_preserves_existing_table_id(self) -> None:
        """已有 table_id 的表不改变"""
        table_data = {
            "_tables": [
                {"table_id": "aging_analysis", "name": "账龄分析", "rows": []},
            ]
        }
        result = ensure_table_ids(table_data)
        assert result["_tables"][0]["table_id"] == "aging_analysis"

    def test_uniqueness_with_duplicate_names(self) -> None:
        """同名表生成唯一 table_id"""
        table_data = {
            "_tables": [
                {"name": "明细表", "rows": []},
                {"name": "明细表", "rows": []},
                {"name": "明细表", "rows": []},
            ]
        }
        result = ensure_table_ids(table_data)
        ids = [t["table_id"] for t in result["_tables"]]
        assert len(ids) == len(set(ids)), f"table_ids not unique: {ids}"

    def test_does_not_mutate_original(self) -> None:
        """不修改原始入参"""
        original_table = {"name": "测试", "rows": []}
        table_data = {"_tables": [original_table]}
        ensure_table_ids(table_data)
        assert "table_id" not in original_table

    def test_handles_none_input(self) -> None:
        """None → 返回空 dict"""
        assert ensure_table_ids(None) == {}

    def test_handles_empty_tables(self) -> None:
        """空 _tables → 原样返回"""
        table_data = {"_tables": [], "headers": ["A"]}
        result = ensure_table_ids(table_data)
        assert result["_tables"] == []
        assert result["headers"] == ["A"]

    def test_idempotent(self) -> None:
        """幂等：连续调用两次结果相同"""
        table_data = {
            "_tables": [
                {"name": "账龄分析", "rows": []},
            ]
        }
        first = ensure_table_ids(table_data)
        second = ensure_table_ids(first)
        assert first["_tables"][0]["table_id"] == second["_tables"][0]["table_id"]


# ===========================================================================
# 4.2 ensure_column_ids 测试
# ===========================================================================


class TestEnsureColumnIds:
    """col_id 生成测试"""

    def test_generates_col_id_from_columns_label(self) -> None:
        """columns 已有 label → slugify 生成 col_id"""
        table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "columns": [
                        {"label": "期末余额"},
                        {"label": "期初余额"},
                    ],
                    "rows": [],
                }
            ]
        }
        result = ensure_column_ids(table_data)
        cols = result["_tables"][0]["columns"]
        assert cols[0]["col_id"]
        assert cols[1]["col_id"]
        assert cols[0]["col_id"] != cols[1]["col_id"]

    def test_generates_col_id_from_headers(self) -> None:
        """无 columns 但有 headers → 从 headers 构建 columns"""
        table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "headers": ["项目", "期末余额", "期初余额"],
                    "rows": [],
                }
            ]
        }
        result = ensure_column_ids(table_data)
        cols = result["_tables"][0]["columns"]
        assert len(cols) == 3
        assert all(c["col_id"] for c in cols)

    def test_preserves_existing_col_id(self) -> None:
        """已有 col_id 不改变"""
        table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "columns": [
                        {"col_id": "closing_balance", "label": "期末余额"},
                    ],
                    "rows": [],
                }
            ]
        }
        result = ensure_column_ids(table_data)
        assert result["_tables"][0]["columns"][0]["col_id"] == "closing_balance"

    def test_generates_col_id_for_empty_label(self) -> None:
        """label 为空 → col_{idx}"""
        table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "columns": [
                        {"label": ""},
                        {"label": "  "},
                    ],
                    "rows": [],
                }
            ]
        }
        result = ensure_column_ids(table_data)
        cols = result["_tables"][0]["columns"]
        assert cols[0]["col_id"] == "col_0"
        assert cols[1]["col_id"] == "col_1"

    def test_uniqueness_with_duplicate_labels(self) -> None:
        """同名列生成唯一 col_id"""
        table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "columns": [
                        {"label": "金额"},
                        {"label": "金额"},
                        {"label": "金额"},
                    ],
                    "rows": [],
                }
            ]
        }
        result = ensure_column_ids(table_data)
        ids = [c["col_id"] for c in result["_tables"][0]["columns"]]
        assert len(ids) == len(set(ids)), f"col_ids not unique: {ids}"

    def test_does_not_mutate_original(self) -> None:
        """不修改原始入参"""
        original_col = {"label": "期末"}
        table_data = {"_tables": [{"table_id": "t1", "columns": [original_col], "rows": []}]}
        ensure_column_ids(table_data)
        assert "col_id" not in original_col

    def test_handles_none_input(self) -> None:
        """None → 返回空 dict"""
        assert ensure_column_ids(None) == {}

    def test_idempotent(self) -> None:
        """幂等：连续调用两次结果相同"""
        table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "headers": ["期末余额", "期初余额"],
                    "rows": [],
                }
            ]
        }
        first = ensure_column_ids(table_data)
        second = ensure_column_ids(first)
        first_ids = [c["col_id"] for c in first["_tables"][0]["columns"]]
        second_ids = [c["col_id"] for c in second["_tables"][0]["columns"]]
        assert first_ids == second_ids


# ===========================================================================
# 4.3 resolve_col_reference 测试
# ===========================================================================


class TestResolveColReference:
    """col_id 解析测试"""

    def test_int_ref_returns_directly(self) -> None:
        """int 直接返回"""
        table = {"columns": [{"col_id": "a"}, {"col_id": "b"}]}
        assert resolve_col_reference(table, 1) == 1

    def test_string_ref_returns_index(self) -> None:
        """col_id 字符串返回对应下标"""
        table = {
            "columns": [
                {"col_id": "project", "label": "项目"},
                {"col_id": "closing_balance", "label": "期末余额"},
                {"col_id": "opening_balance", "label": "期初余额"},
            ]
        }
        assert resolve_col_reference(table, "closing_balance") == 1
        assert resolve_col_reference(table, "opening_balance") == 2
        assert resolve_col_reference(table, "project") == 0

    def test_missing_col_id_returns_zero(self) -> None:
        """col_id 不存在时回退为 0"""
        table = {"columns": [{"col_id": "a"}]}
        assert resolve_col_reference(table, "nonexistent") == 0

    def test_no_columns_returns_zero(self) -> None:
        """表无 columns 时回退为 0"""
        table = {"rows": []}
        assert resolve_col_reference(table, "any_col") == 0

    def test_invalid_type_returns_zero(self) -> None:
        """非 int/str 类型回退为 0"""
        table = {"columns": []}
        assert resolve_col_reference(table, None) == 0  # type: ignore[arg-type]


# ===========================================================================
# 4.4 列重命名后 col_id 不变
# ===========================================================================


class TestColIdStabilityOnRename:
    """验证列重命名后 col_id 不变（已有 col_id 优先）"""

    def test_rename_header_does_not_change_col_id(self) -> None:
        """已有 col_id 的列，修改 label 后 col_id 保持不变"""
        # 初始状态：已分配 col_id
        table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "columns": [
                        {"col_id": "closing_balance", "label": "期末余额"},
                        {"col_id": "opening_balance", "label": "期初余额"},
                    ],
                    "rows": [],
                }
            ]
        }
        # 模拟用户重命名列头
        table_data["_tables"][0]["columns"][0]["label"] = "本期期末数"
        table_data["_tables"][0]["columns"][1]["label"] = "上期期末数"

        # 再次 ensure → col_id 不变
        result = ensure_column_ids(table_data)
        cols = result["_tables"][0]["columns"]
        assert cols[0]["col_id"] == "closing_balance"
        assert cols[1]["col_id"] == "opening_balance"

    def test_new_column_without_id_gets_generated_id(self) -> None:
        """新增列无 col_id → 生成新 ID，不影响已有列"""
        table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "columns": [
                        {"col_id": "closing_balance", "label": "期末余额"},
                        {"label": "本年增加"},  # 新增列，无 col_id
                    ],
                    "rows": [],
                }
            ]
        }
        result = ensure_column_ids(table_data)
        cols = result["_tables"][0]["columns"]
        assert cols[0]["col_id"] == "closing_balance"
        assert cols[1]["col_id"]  # 非空
        assert cols[1]["col_id"] != "closing_balance"


# ===========================================================================
# PBT: ensure_table_ids 总产出非空 table_id
# ===========================================================================


table_name_strategy = st.one_of(
    st.just(""),
    st.just("  "),
    st.text(
        alphabet=st.sampled_from(
            list("账龄分析固定资产明细表应收账款") + list("abcABC123_")
        ),
        min_size=0,
        max_size=15,
    ),
)

tables_strategy = st.lists(
    st.fixed_dictionaries(
        {"rows": st.just([])},
        optional={"name": table_name_strategy, "table_id": st.just("")},
    ),
    min_size=1,
    max_size=5,
)


class TestEnsureTableIdsPBT:
    """Property-based tests for ensure_table_ids

    **Validates: Requirements 3.1**
    """

    @settings(max_examples=5)
    @given(tables=tables_strategy)
    def test_all_tables_have_non_empty_table_id(self, tables: list[dict]) -> None:
        """P1: ensure_table_ids 对任意 _tables 输入，每张表都有非空 table_id"""
        table_data = {"_tables": tables}
        result = ensure_table_ids(table_data)
        for idx, tbl in enumerate(result["_tables"]):
            assert isinstance(tbl, dict), f"Table {idx} is not dict"
            tid = tbl.get("table_id")
            assert tid and isinstance(tid, str) and tid.strip(), (
                f"Table {idx} has empty table_id: {tid!r}"
            )

    @settings(max_examples=5)
    @given(tables=tables_strategy)
    def test_all_table_ids_unique(self, tables: list[dict]) -> None:
        """P2: ensure_table_ids 产出的 table_id 全部唯一"""
        table_data = {"_tables": tables}
        result = ensure_table_ids(table_data)
        ids = [t["table_id"] for t in result["_tables"]]
        assert len(ids) == len(set(ids)), f"Duplicate table_ids: {ids}"


# ===========================================================================
# Slugify 单元测试（辅助验证）
# ===========================================================================


class TestSlugify:
    """_slugify 工具函数测试"""

    def test_chinese_text(self) -> None:
        slug = _slugify("期末余额")
        assert slug == "期末余额"

    def test_english_text(self) -> None:
        slug = _slugify("Closing Balance")
        assert slug == "closing_balance"

    def test_html_tags_stripped(self) -> None:
        slug = _slugify("期末余额<br/>合计")
        assert "<" not in slug
        assert ">" not in slug

    def test_empty_returns_empty(self) -> None:
        slug = _slugify("")
        assert slug == ""

    def test_mixed_content(self) -> None:
        slug = _slugify("1年以内（含）")
        assert slug  # 非空
        assert "（" not in slug


class TestMakeUnique:
    """_make_unique 工具函数测试"""

    def test_first_use_returns_as_is(self) -> None:
        existing: set[str] = set()
        assert _make_unique("foo", existing) == "foo"
        assert "foo" in existing

    def test_duplicate_gets_suffix(self) -> None:
        existing: set[str] = {"foo"}
        assert _make_unique("foo", existing) == "foo_2"
        assert "foo_2" in existing

    def test_triple_duplicate(self) -> None:
        existing: set[str] = {"foo", "foo_2"}
        assert _make_unique("foo", existing) == "foo_3"
