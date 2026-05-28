"""Sprint B.0.9 — consol_note_aggregation_service 单元测试.

覆盖：
- aggregate_cell 5 种方法
- fuzzy_merge_same_label 模糊合并
- validate_lineage_dag DAG 校验
- get_lineage_chain 链路获取
- _simple_sum / _sum_after_elimination / _top_n_after_elimination
- _weighted_avg / _first_n_concat

Validates: Requirements D12, CI-15, CI-16
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from uuid import UUID, uuid4

from app.services.consol_note_aggregation_service import (
    AGGREGATION_METHODS,
    aggregate_cell,
    fuzzy_merge_same_label,
    validate_lineage_dag,
    get_lineage_chain,
    _simple_sum,
    _sum_after_elimination,
    _top_n_after_elimination,
    _weighted_avg,
    _first_n_concat,
    _label_similarity,
    _collect_all_rows,
    _extract_rows_from_table_data,
)


# ---------------------------------------------------------------------------
# aggregate_cell 测试
# ---------------------------------------------------------------------------


class TestAggregateCell:
    """aggregate_cell 单元测试."""

    def test_simple_sum_basic(self):
        result = aggregate_cell([100, 200, 300], method="simple_sum")
        assert result == Decimal("600.00")

    def test_simple_sum_with_none(self):
        result = aggregate_cell([100, None, 200], method="simple_sum")
        assert result == Decimal("300.00")

    def test_simple_sum_all_none(self):
        result = aggregate_cell([None, None], method="simple_sum")
        assert result is None

    def test_simple_sum_empty(self):
        result = aggregate_cell([], method="simple_sum")
        assert result is None

    def test_sum_after_elimination(self):
        result = aggregate_cell(
            [1000, 2000, 500],
            method="sum_after_elimination",
            elimination_amount=300,
        )
        assert result == Decimal("3200.00")

    def test_sum_after_elimination_no_amount(self):
        result = aggregate_cell(
            [1000, 2000],
            method="sum_after_elimination",
            elimination_amount=None,
        )
        assert result == Decimal("3000.00")

    def test_weighted_avg(self):
        result = aggregate_cell([100, 200, 300], method="weighted_avg")
        assert result == Decimal("200.00")

    def test_top_n_after_elimination(self):
        result = aggregate_cell(
            [100, 200],
            method="top_n_after_elimination",
            elimination_amount=50,
        )
        # top_n at cell-level sums without elimination (elimination is section-level)
        assert result == Decimal("300.00")

    def test_decimal_input(self):
        result = aggregate_cell(
            [Decimal("100.50"), Decimal("200.75")],
            method="simple_sum",
        )
        assert result == Decimal("301.25")

    def test_float_input(self):
        result = aggregate_cell([10.5, 20.3], method="simple_sum")
        assert result == Decimal("30.80")


# ---------------------------------------------------------------------------
# fuzzy_merge_same_label 测试
# ---------------------------------------------------------------------------


class TestFuzzyMergeSameLabel:
    """fuzzy_merge_same_label 模糊合并测试."""

    def test_empty_input(self):
        assert fuzzy_merge_same_label([]) == []

    def test_no_merge_needed(self):
        rows = [
            {"label": "客户A", "values": {"col1": Decimal("100")}},
            {"label": "客户B", "values": {"col1": Decimal("200")}},
        ]
        result = fuzzy_merge_same_label(rows, threshold=0.85)
        assert len(result) == 2

    def test_merge_similar_labels(self):
        rows = [
            {"label": "中国石油天然气股份有限公司", "values": {"col1": Decimal("100")}},
            {"label": "中国石油天然气股份有限公司北京分公司", "values": {"col1": Decimal("50")}},
        ]
        # These are similar enough (> 0.85 for long strings)
        result = fuzzy_merge_same_label(rows, threshold=0.70)
        assert len(result) == 1
        assert result[0]["values"]["col1"] == Decimal("150")

    def test_merge_exact_same_labels(self):
        rows = [
            {"label": "华为技术有限公司", "values": {"col1": Decimal("500")}},
            {"label": "华为技术有限公司", "values": {"col1": Decimal("300")}},
        ]
        result = fuzzy_merge_same_label(rows, threshold=0.85)
        assert len(result) == 1
        assert result[0]["values"]["col1"] == Decimal("800")

    def test_threshold_boundary(self):
        rows = [
            {"label": "ABC公司", "values": {"col1": Decimal("100")}},
            {"label": "XYZ公司", "values": {"col1": Decimal("200")}},
        ]
        # Very different labels should not merge
        result = fuzzy_merge_same_label(rows, threshold=0.85)
        assert len(result) == 2

    def test_multiple_columns_merge(self):
        rows = [
            {"label": "同一客户", "values": {"col1": Decimal("100"), "col2": Decimal("50")}},
            {"label": "同一客户", "values": {"col1": Decimal("200"), "col2": Decimal("30")}},
        ]
        result = fuzzy_merge_same_label(rows, threshold=0.85)
        assert len(result) == 1
        assert result[0]["values"]["col1"] == Decimal("300")
        assert result[0]["values"]["col2"] == Decimal("80")

    def test_preserves_first_label(self):
        rows = [
            {"label": "中国移动通信集团", "values": {"col1": Decimal("100")}},
            {"label": "中国移动通信集团有限公司", "values": {"col1": Decimal("200")}},
        ]
        result = fuzzy_merge_same_label(rows, threshold=0.70)
        assert len(result) == 1
        assert result[0]["label"] == "中国移动通信集团"


# ---------------------------------------------------------------------------
# _label_similarity 测试
# ---------------------------------------------------------------------------


class TestLabelSimilarity:
    """_label_similarity 相似度计算测试."""

    def test_identical(self):
        assert _label_similarity("ABC", "ABC") == 1.0

    def test_empty_both(self):
        assert _label_similarity("", "") == 1.0

    def test_empty_one(self):
        assert _label_similarity("ABC", "") == 0.0
        assert _label_similarity("", "ABC") == 0.0

    def test_similar(self):
        sim = _label_similarity("中国石油", "中国石化")
        assert 0.5 < sim < 1.0

    def test_different(self):
        sim = _label_similarity("ABCDEF", "XYZWVU")
        assert sim < 0.5


# ---------------------------------------------------------------------------
# 聚合方法内部测试
# ---------------------------------------------------------------------------


class TestAggregationMethods:
    """内部聚合方法测试."""

    def _make_child_data(self):
        return [
            {
                "project_id": uuid4(),
                "company_name": "子公司A",
                "rows": [
                    {"label": "客户1", "values": {"col1": Decimal("100")}, "row_type": "data"},
                    {"label": "客户2", "values": {"col1": Decimal("200")}, "row_type": "data"},
                ],
                "ownership_ratio": 0.6,
            },
            {
                "project_id": uuid4(),
                "company_name": "子公司B",
                "rows": [
                    {"label": "客户1", "values": {"col1": Decimal("150")}, "row_type": "data"},
                    {"label": "客户3", "values": {"col1": Decimal("300")}, "row_type": "data"},
                ],
                "ownership_ratio": 0.4,
            },
        ]

    def test_simple_sum(self):
        data = self._make_child_data()
        result = _simple_sum(data, {})
        assert result["elimination_applied"] is False
        assert len(result["rows"]) == 4  # no merge without threshold

    def test_simple_sum_with_merge(self):
        data = self._make_child_data()
        result = _simple_sum(data, {"merge_same_label_threshold": 0.85})
        # "客户1" appears twice → merged
        assert len(result["rows"]) == 3

    def test_sum_after_elimination(self):
        data = self._make_child_data()
        rules = [{"amount": 50}]
        result = _sum_after_elimination(data, {"merge_same_label_threshold": 0.85}, rules)
        assert result["elimination_applied"] is True

    def test_top_n_after_elimination(self):
        data = self._make_child_data()
        result = _top_n_after_elimination(
            data,
            {"top_n": 2, "merge_same_label_threshold": 0.85, "sort_column": "col1"},
            [],
        )
        assert len(result["rows"]) <= 2

    def test_weighted_avg(self):
        data = self._make_child_data()
        result = _weighted_avg(data, {"merge_same_label_threshold": 0.85})
        assert result["elimination_applied"] is False
        assert len(result["rows"]) > 0

    def test_first_n_concat(self):
        data = [
            {"project_id": uuid4(), "company_name": "A", "text_content": "段落A", "rows": []},
            {"project_id": uuid4(), "company_name": "B", "text_content": "段落B", "rows": []},
            {"project_id": uuid4(), "company_name": "C", "text_content": "段落C", "rows": []},
        ]
        result = _first_n_concat(data, {"first_n": 2})
        assert len(result["texts"]) == 2


# ---------------------------------------------------------------------------
# DAG 校验测试
# ---------------------------------------------------------------------------


class TestLineageDAG:
    """validate_lineage_dag / get_lineage_chain 测试."""

    @pytest.mark.asyncio
    async def test_validate_no_db(self):
        """无 DB 时应返回 True（无法检测环）."""
        result = await validate_lineage_dag(uuid4(), db=None)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_lineage_chain_no_db(self):
        """无 DB 时返回仅含自身的链."""
        pid = uuid4()
        chain = await get_lineage_chain(pid, db=None)
        assert chain == [pid]


# ---------------------------------------------------------------------------
# 辅助函数测试
# ---------------------------------------------------------------------------


class TestHelpers:
    """辅助函数测试."""

    def test_collect_all_rows(self):
        data = [
            {"project_id": "p1", "rows": [{"label": "A"}, {"label": "B"}]},
            {"project_id": "p2", "rows": [{"label": "C"}]},
        ]
        rows = _collect_all_rows(data)
        assert len(rows) == 3
        assert rows[0]["source_project"] == "p1"
        assert rows[2]["source_project"] == "p2"

    def test_extract_rows_from_table_data_empty(self):
        assert _extract_rows_from_table_data({}) == []
        assert _extract_rows_from_table_data(None) == []

    def test_extract_rows_from_table_data(self):
        table_data = {
            "rows": [
                {"label": "行1", "cells": {"A": 100}, "row_type": "data"},
                {"label": "合计", "cells": {"A": 100}, "row_type": "total"},
            ]
        }
        rows = _extract_rows_from_table_data(table_data)
        assert len(rows) == 2
        assert rows[0]["label"] == "行1"
        assert rows[1]["is_total"] is True

    def test_aggregation_methods_constant(self):
        assert "simple_sum" in AGGREGATION_METHODS
        assert "sum_after_elimination" in AGGREGATION_METHODS
        assert "top_n_after_elimination" in AGGREGATION_METHODS
        assert "weighted_avg" in AGGREGATION_METHODS
        assert "first_n_concat" in AGGREGATION_METHODS
        assert len(AGGREGATION_METHODS) == 5
