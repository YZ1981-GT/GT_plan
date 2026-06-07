"""Tests for backend/app/services/note_row_type_inferrer.py

验证：
1. 推断逻辑对所有 row_type 值正确工作
2. row_type 在模拟重生成（merge + rebuild）后不丢失
3. row_type 在模拟公式执行后不丢失
4. row_type 在模拟用户编辑后不丢失

Validates: Requirements 3.2, 3.4, 3.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_row_type_inferrer import (
    VALID_ROW_TYPES,
    enrich_table_data_with_row_types,
    infer_row_type,
)
from app.services.note_cell_merge import (
    merge_row_preserving_cell_modes,
    merge_table_data_preserving_cell_modes,
)


# ===========================================================================
# 3.1 推断函数单元测试
# ===========================================================================


class TestInferRowType:
    """infer_row_type 推断逻辑测试"""

    def test_existing_row_type_data(self) -> None:
        """已有 row_type=data → 保持 data"""
        row = {"row_type": "data", "label": "现金"}
        assert infer_row_type(row) == "data"

    def test_existing_row_type_total(self) -> None:
        """已有 row_type=total → 保持 total"""
        row = {"row_type": "total", "label": "合计"}
        assert infer_row_type(row) == "total"

    def test_existing_row_type_header_label_maps_to_group_header(self) -> None:
        """已有 row_type=header_label → 映射为 group_header"""
        row = {"row_type": "header_label", "label": "一、流动资产"}
        assert infer_row_type(row) == "group_header"

    def test_existing_row_type_subtotal(self) -> None:
        """已有 row_type=subtotal → 保持 subtotal"""
        row = {"row_type": "subtotal", "label": "小计"}
        assert infer_row_type(row) == "subtotal"

    def test_is_total_true_returns_total(self) -> None:
        """is_total=True 且 label 无"小计" → total"""
        row = {"is_total": True, "label": "应收账款合计"}
        assert infer_row_type(row) == "total"

    def test_is_total_true_with_subtotal_label(self) -> None:
        """is_total=True 且 label 含"小计" → subtotal"""
        row = {"is_total": True, "label": "应收账款小计"}
        assert infer_row_type(row) == "subtotal"

    def test_empty_label_returns_blank(self) -> None:
        """label 为空字符串 → blank"""
        row = {"label": ""}
        assert infer_row_type(row) == "blank"

    def test_none_label_returns_blank(self) -> None:
        """label 缺失（无 key） → blank"""
        row = {}
        assert infer_row_type(row) == "blank"

    def test_whitespace_label_returns_blank(self) -> None:
        """label 为纯空格 → blank"""
        row = {"label": "   "}
        assert infer_row_type(row) == "blank"

    def test_label_with_heji_returns_total(self) -> None:
        """label 含"合计" → total"""
        row = {"label": "应收账款合计"}
        assert infer_row_type(row) == "total"

    def test_label_with_xiaoji_returns_subtotal(self) -> None:
        """label 含"小计" → subtotal"""
        row = {"label": "1年以内小计"}
        assert infer_row_type(row) == "subtotal"

    def test_label_with_tishi_returns_note_tip(self) -> None:
        """label 含"提示" → note_tip"""
        row = {"label": "提示：本表为参考格式"}
        assert infer_row_type(row) == "note_tip"

    def test_label_starting_with_zhu_returns_note_tip(self) -> None:
        """label 以"注："开头 → note_tip"""
        row = {"label": "注：以上数据来源于审计底稿"}
        assert infer_row_type(row) == "note_tip"

    def test_label_starting_with_bracket_returns_note_tip(self) -> None:
        """label 以"【"开头 → note_tip"""
        row = {"label": "【注意事项】请核实余额"}
        assert infer_row_type(row) == "note_tip"

    def test_normal_data_label_returns_data(self) -> None:
        """普通数据 label → data"""
        row = {"label": "1年以内"}
        assert infer_row_type(row) == "data"

    def test_normal_account_label_returns_data(self) -> None:
        """账户名称 label → data"""
        row = {"label": "银行存款——工商银行"}
        assert infer_row_type(row) == "data"

    def test_all_valid_row_types_recognized(self) -> None:
        """所有标准 row_type 枚举值都能被已有 row_type 直接识别"""
        for rt in VALID_ROW_TYPES:
            row = {"row_type": rt, "label": "any"}
            assert infer_row_type(row) == rt


# ===========================================================================
# 3.2 enrich_table_data_with_row_types 测试
# ===========================================================================


class TestEnrichTableData:
    """enrich_table_data_with_row_types 测试"""

    def test_enriches_tables_rows(self) -> None:
        """_tables 中的行被添加 row_type"""
        table_data = {
            "_tables": [
                {
                    "table_id": "aging",
                    "rows": [
                        {"label": "1年以内", "values": [100]},
                        {"label": "合计", "values": [500], "is_total": True},
                    ],
                }
            ]
        }
        result = enrich_table_data_with_row_types(table_data)
        rows = result["_tables"][0]["rows"]
        assert rows[0]["row_type"] == "data"
        assert rows[1]["row_type"] == "total"

    def test_does_not_change_values(self) -> None:
        """enrichment 不改变 values"""
        table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "rows": [
                        {"label": "行1", "values": [1, 2, 3]},
                    ],
                }
            ]
        }
        result = enrich_table_data_with_row_types(table_data)
        assert result["_tables"][0]["rows"][0]["values"] == [1, 2, 3]

    def test_preserves_existing_row_type(self) -> None:
        """已有 row_type 的行保持不变"""
        table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "rows": [
                        {"label": "标题", "values": [], "row_type": "table_title"},
                    ],
                }
            ]
        }
        result = enrich_table_data_with_row_types(table_data)
        assert result["_tables"][0]["rows"][0]["row_type"] == "table_title"

    def test_handles_none_input(self) -> None:
        """None 输入返回空 dict"""
        assert enrich_table_data_with_row_types(None) == {}

    def test_handles_empty_dict(self) -> None:
        """空 dict 输入返回空 dict"""
        result = enrich_table_data_with_row_types({})
        assert result == {}

    def test_enriches_top_level_rows(self) -> None:
        """顶层 rows（单表兼容模式）也被添加 row_type"""
        table_data = {
            "rows": [
                {"label": "银行存款", "values": [100]},
                {"label": "", "values": []},
            ]
        }
        result = enrich_table_data_with_row_types(table_data)
        assert result["rows"][0]["row_type"] == "data"
        assert result["rows"][1]["row_type"] == "blank"

    def test_does_not_mutate_original(self) -> None:
        """不修改原始入参"""
        original_row = {"label": "测试", "values": [1]}
        table_data = {"_tables": [{"table_id": "t", "rows": [original_row]}]}
        enrich_table_data_with_row_types(table_data)
        assert "row_type" not in original_row


# ===========================================================================
# 3.3 note_cell_merge 保留 row_type 测试
# ===========================================================================


class TestMergePreservesRowType:
    """验证 merge 操作保留 row_type"""

    def test_merge_row_preserves_old_row_type_when_new_missing(self) -> None:
        """new_row 无 row_type → 合并后取 old_row 的 row_type"""
        old_row = {
            "label": "合计",
            "values": [100],
            "row_type": "total",
            "_cell_modes": {"0": "auto"},
            "_cell_meta": {},
        }
        new_row = {
            "label": "合计",
            "values": [200],
        }
        merged = merge_row_preserving_cell_modes(old_row, new_row)
        assert merged["row_type"] == "total"

    def test_merge_row_uses_new_row_type_when_both_present(self) -> None:
        """new_row 有 row_type → 合并后用 new 的（模板权威）"""
        old_row = {
            "label": "合计",
            "values": [100],
            "row_type": "data",
            "_cell_modes": {},
            "_cell_meta": {},
        }
        new_row = {
            "label": "合计",
            "values": [200],
            "row_type": "total",
        }
        merged = merge_row_preserving_cell_modes(old_row, new_row)
        assert merged["row_type"] == "total"

    def test_merge_table_data_preserves_row_types_in_tables(self) -> None:
        """多表合并后 _tables 中行的 row_type 保留"""
        old_table_data = {
            "_tables": [
                {
                    "rows": [
                        {
                            "label": "1年以内",
                            "values": [100],
                            "row_type": "data",
                            "_cell_modes": {"0": "manual"},
                            "_cell_meta": {"0": {"manual_value": 100}},
                        },
                        {
                            "label": "合计",
                            "values": [500],
                            "row_type": "total",
                            "_cell_modes": {"0": "auto"},
                            "_cell_meta": {},
                        },
                    ]
                }
            ]
        }
        new_table_data = {
            "_tables": [
                {
                    "rows": [
                        {"label": "1年以内", "values": [150]},
                        {"label": "合计", "values": [600]},
                    ]
                }
            ]
        }
        merged = merge_table_data_preserving_cell_modes(old_table_data, new_table_data)
        rows = merged["_tables"][0]["rows"]
        assert rows[0]["row_type"] == "data"
        assert rows[1]["row_type"] == "total"


# ===========================================================================
# 3.4 row_type 在重生成/公式执行/用户编辑后不丢失
# ===========================================================================


class TestRowTypeSurvival:
    """模拟重生成、公式执行、用户编辑后 row_type 是否保留"""

    def _make_table_data_with_row_types(self) -> dict:
        """构造带 row_type 的 table_data"""
        return {
            "_tables": [
                {
                    "table_id": "aging",
                    "rows": [
                        {
                            "label": "1年以内",
                            "values": [100, 50],
                            "row_type": "data",
                            "_cell_modes": {"0": "auto", "1": "auto"},
                            "_cell_meta": {},
                        },
                        {
                            "label": "1-2年",
                            "values": [80, 40],
                            "row_type": "data",
                            "_cell_modes": {"0": "auto", "1": "auto"},
                            "_cell_meta": {},
                        },
                        {
                            "label": "合计",
                            "values": [180, 90],
                            "row_type": "total",
                            "is_total": True,
                            "_cell_modes": {"0": "auto", "1": "auto"},
                            "_cell_meta": {},
                        },
                    ],
                }
            ]
        }

    def test_row_type_survives_regeneration(self) -> None:
        """模拟重生成：引擎产出新 values 但不带 row_type → merge 后 row_type 保留"""
        old = self._make_table_data_with_row_types()
        # 模拟引擎重新生成（新值、无 row_type）
        new = {
            "_tables": [
                {
                    "table_id": "aging",
                    "rows": [
                        {"label": "1年以内", "values": [110, 55]},
                        {"label": "1-2年", "values": [85, 42]},
                        {"label": "合计", "values": [195, 97]},
                    ],
                }
            ]
        }
        merged = merge_table_data_preserving_cell_modes(old, new)
        rows = merged["_tables"][0]["rows"]
        assert rows[0]["row_type"] == "data"
        assert rows[1]["row_type"] == "data"
        assert rows[2]["row_type"] == "total"

    def test_row_type_survives_formula_execution(self) -> None:
        """模拟公式执行：仅更新 auto 单元格值 → row_type 不丢"""
        old = self._make_table_data_with_row_types()
        # 模拟公式执行后产出的 table_data（只改了合计行的值）
        new = {
            "_tables": [
                {
                    "table_id": "aging",
                    "rows": [
                        {"label": "1年以内", "values": [100, 50]},
                        {"label": "1-2年", "values": [80, 40]},
                        {"label": "合计", "values": [180, 90]},  # 公式重算
                    ],
                }
            ]
        }
        merged = merge_table_data_preserving_cell_modes(old, new)
        rows = merged["_tables"][0]["rows"]
        assert rows[2]["row_type"] == "total"
        assert rows[2]["is_total"] is True

    def test_row_type_survives_user_edit(self) -> None:
        """模拟用户编辑：用户改了 manual 单元格，后续 merge → row_type 保留"""
        old = self._make_table_data_with_row_types()
        # 用户手工修改了第一行第一列
        old["_tables"][0]["rows"][0]["_cell_modes"]["0"] = "manual"
        old["_tables"][0]["rows"][0]["values"][0] = 999

        # 引擎重生成
        new = {
            "_tables": [
                {
                    "table_id": "aging",
                    "rows": [
                        {"label": "1年以内", "values": [110, 55]},
                        {"label": "1-2年", "values": [85, 42]},
                        {"label": "合计", "values": [195, 97]},
                    ],
                }
            ]
        }
        merged = merge_table_data_preserving_cell_modes(old, new)
        rows = merged["_tables"][0]["rows"]
        # manual 列保持用户值
        assert rows[0]["values"][0] == 999
        # row_type 保留
        assert rows[0]["row_type"] == "data"
        assert rows[1]["row_type"] == "data"
        assert rows[2]["row_type"] == "total"

    def test_row_type_survives_enrich_then_merge(self) -> None:
        """模拟完整流程：先 enrich 添加 row_type → 后续 merge 保留"""
        # 原始数据无 row_type
        raw_table_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "rows": [
                        {"label": "现金", "values": [100]},
                        {"label": "合计", "values": [100], "is_total": True},
                    ],
                }
            ]
        }
        # 步骤1: enrich 添加 row_type
        enriched = enrich_table_data_with_row_types(raw_table_data)
        assert enriched["_tables"][0]["rows"][0]["row_type"] == "data"
        assert enriched["_tables"][0]["rows"][1]["row_type"] == "total"

        # 给 enriched 加上必要的 _cell_modes（模拟已保存状态）
        for row in enriched["_tables"][0]["rows"]:
            row["_cell_modes"] = {"0": "auto"}
            row["_cell_meta"] = {}

        # 步骤2: 模拟引擎重生成 merge
        new_data = {
            "_tables": [
                {
                    "table_id": "t1",
                    "rows": [
                        {"label": "现金", "values": [200]},
                        {"label": "合计", "values": [200]},
                    ],
                }
            ]
        }
        merged = merge_table_data_preserving_cell_modes(enriched, new_data)
        rows = merged["_tables"][0]["rows"]
        assert rows[0]["row_type"] == "data"
        assert rows[1]["row_type"] == "total"


# ===========================================================================
# PBT: row_type 推断返回值总在合法枚举范围内
# ===========================================================================


# 构造行数据策略
row_strategy = st.fixed_dictionaries(
    {},
    optional={
        "row_type": st.sampled_from(list(VALID_ROW_TYPES) + ["header_label", ""]),
        "is_total": st.booleans(),
        "label": st.one_of(
            st.just(""),
            st.just(" "),
            st.text(
                alphabet=st.sampled_from(
                    list("合计小计提示注：【测试数据银行存款现金") + list("abcdef123")
                ),
                min_size=0,
                max_size=10,
            ),
        ),
        "values": st.lists(st.one_of(st.none(), st.floats(allow_nan=False)), max_size=5),
    },
)


class TestInferRowTypePBT:
    """Property-based tests for infer_row_type

    **Validates: Requirements 3.2**
    """

    @settings(max_examples=5)
    @given(row=row_strategy)
    def test_infer_always_returns_valid_type(self, row: dict) -> None:
        """P1: infer_row_type 对任意输入总返回合法的 row_type 枚举值"""
        result = infer_row_type(row)
        assert result in VALID_ROW_TYPES, f"Got invalid row_type: {result}"
