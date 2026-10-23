"""合并附注明细来源扫描、结构指纹与建议算法测试。

spec: consol-note-detail-template-and-mapping Phase 2 Task 14
覆盖：指纹稳定性 / 分组 / 建议五级匹配 / suggest_template 频率排序。
"""
from __future__ import annotations

import pytest

from app.services.consol_note_detail_source_service import (
    compute_source_structure_hash,
    extract_source_rows,
    group_entities_by_structure,
    suggest_template_rows,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 结构指纹
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractSourceRows:
    def test_list_rows(self):
        rows = [["职工薪酬", "100", "80"], ["办公费", "50", "40"], ["合计", "150", "120"]]
        result = extract_source_rows(rows)
        assert len(result) == 3
        assert result[0]["label"] == "职工薪酬"
        assert result[0]["row_type"] == "data"
        assert result[2]["label"] == "合计"
        assert result[2]["row_type"] == "total"

    def test_dict_rows(self):
        rows = [
            {"label": "职工薪酬", "values": {"1": 100}, "row_type": "data"},
            {"label": "合计", "values": {"1": 100}, "row_type": "total"},
        ]
        result = extract_source_rows(rows)
        assert len(result) == 2
        assert result[0]["label"] == "职工薪酬"
        assert result[1]["row_type"] == "total"

    def test_stable_key_used_when_present(self):
        rows = [{"label": "A", "row_id": "UUID-1"}, {"label": "B", "item_id": "ITEM-2"}]
        result = extract_source_rows(rows)
        assert result[0]["key"] == "UUID-1"
        assert result[1]["key"] == "ITEM-2"

    def test_pseudo_key_for_duplicate_labels(self):
        rows = [["其他", "10"], ["其他", "20"]]
        result = extract_source_rows(rows)
        assert result[0]["key"] == "其他#0"
        assert result[1]["key"] == "其他#1"

    def test_empty_rows(self):
        assert extract_source_rows([]) == []


class TestComputeSourceStructureHash:
    def test_same_structure_same_hash(self):
        rows_a = [["职工薪酬", "100"], ["办公费", "50"]]
        rows_b = [["职工薪酬", "999"], ["办公费", "1"]]
        ha = compute_source_structure_hash("五-67-1", rows_a)
        hb = compute_source_structure_hash("五-67-1", rows_b)
        assert ha == hb, "金额变化不应改变指纹"

    def test_different_labels_different_hash(self):
        rows_a = [["职工薪酬", "100"]]
        rows_b = [["员工成本", "100"]]
        ha = compute_source_structure_hash("五-67-1", rows_a)
        hb = compute_source_structure_hash("五-67-1", rows_b)
        assert ha != hb, "行名变化必须改变指纹"

    def test_added_row_changes_hash(self):
        rows_a = [["A", "1"]]
        rows_b = [["A", "1"], ["B", "2"]]
        ha = compute_source_structure_hash("五-1-1", rows_a)
        hb = compute_source_structure_hash("五-1-1", rows_b)
        assert ha != hb, "新增行必须改变指纹"

    def test_deleted_row_changes_hash(self):
        rows_a = [["A", "1"], ["B", "2"]]
        rows_b = [["A", "1"]]
        ha = compute_source_structure_hash("五-1-1", rows_a)
        hb = compute_source_structure_hash("五-1-1", rows_b)
        assert ha != hb, "删除行必须改变指纹"

    def test_different_section_different_hash(self):
        rows = [["A", "1"]]
        ha = compute_source_structure_hash("五-67-1", rows)
        hb = compute_source_structure_hash("五-68-1", rows)
        assert ha != hb, "不同章节必须不同指纹"

    def test_hash_is_64_hex(self):
        h = compute_source_structure_hash("x", [["A"]])
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_order_with_stable_keys_same_hash(self):
        """P1 优化：数据行排序后算 hash，行顺序不同但行名集合相同的子企业
        共用一条映射规则——减少确认次数。"""
        rows_a = [{"label": "A", "row_id": "1"}, {"label": "B", "row_id": "2"}]
        rows_b = [{"label": "B", "row_id": "2"}, {"label": "A", "row_id": "1"}]
        ha = compute_source_structure_hash("x", rows_a)
        hb = compute_source_structure_hash("x", rows_b)
        # 排序后 hash 相同——同样的行不同顺序的子企业共用规则
        assert ha == hb


class TestGroupEntitiesByStructure:
    def test_same_structure_grouped(self):
        h = compute_source_structure_hash("五-67-1", [["A", "1"]])
        entities = [
            {"node_key": "X:sub", "project_id": "p1", "company_name": "甲", "section_id": "五-67-1", "rows": [["A", "1"]], "hash": h},
            {"node_key": "Y:sub", "project_id": "p2", "company_name": "乙", "section_id": "五-67-1", "rows": [["A", "2"]], "hash": h},
        ]
        groups = group_entities_by_structure(entities)
        assert len(groups) == 1
        assert len(groups[0]["entities"]) == 2

    def test_different_structure_separate_groups(self):
        h1 = compute_source_structure_hash("五-67-1", [["A"]])
        h2 = compute_source_structure_hash("五-67-1", [["A"], ["B"]])
        entities = [
            {"node_key": "X", "project_id": "p1", "company_name": "甲", "section_id": "五-67-1", "rows": [["A"]], "hash": h1},
            {"node_key": "Y", "project_id": "p2", "company_name": "乙", "section_id": "五-67-1", "rows": [["A"], ["B"]], "hash": h2},
        ]
        groups = group_entities_by_structure(entities)
        assert len(groups) == 2

    def test_empty_entities(self):
        assert group_entities_by_structure([]) == []


# ═══════════════════════════════════════════════════════════════════════════════
# 建议算法
# ═══════════════════════════════════════════════════════════════════════════════


class TestSuggestTemplateRows:
    TEMPLATE = [
        {"target_row_id": "t1", "canonical_name": "职工薪酬", "aliases": ["工资及奖金", "管理人员薪酬"]},
        {"target_row_id": "t2", "canonical_name": "办公费", "aliases": ["办公费用"]},
        {"target_row_id": "t3", "canonical_name": "中介机构费", "aliases": ["审计咨询费"]},
        {"target_row_id": "t4", "canonical_name": "合计", "aliases": [], "row_type": "total"},
    ]

    def _groups(self, labels: list[str]) -> list[dict]:
        return [{"source_rows": [{"label": l, "row_type": "data", "key": f"{l}#0"} for l in labels], "entities": []}]

    def test_exact_match(self):
        result = suggest_template_rows(
            self._groups(["职工薪酬"]),
            existing_template_rows=self.TEMPLATE,
        )
        assert len(result) == 1
        assert result[0]["match_type"] == "exact"
        assert result[0]["confidence"] == 1.0
        assert result[0]["suggested_target"]["target_row_id"] == "t1"

    def test_alias_match(self):
        result = suggest_template_rows(
            self._groups(["工资及奖金"]),
            existing_template_rows=self.TEMPLATE,
        )
        assert len(result) == 1
        assert result[0]["match_type"] == "alias"
        assert result[0]["suggested_target"]["target_row_id"] == "t1"

    def test_fuzzy_match(self):
        result = suggest_template_rows(
            self._groups(["办公费支出"]),
            existing_template_rows=self.TEMPLATE,
            fuzzy_threshold=0.6,
        )
        assert len(result) == 1
        assert result[0]["match_type"] == "fuzzy"
        assert result[0]["confidence"] > 0

    def test_history_match(self):
        result = suggest_template_rows(
            self._groups(["差旅交通费"]),
            existing_template_rows=self.TEMPLATE,
            history_mappings=[{"source_label": "差旅交通费", "target_row_id": "t2"}],
        )
        assert len(result) == 1
        assert result[0]["match_type"] == "history"
        assert result[0]["suggested_target"]["target_row_id"] == "t2"

    def test_manual_fallback(self):
        result = suggest_template_rows(
            self._groups(["完全未知的费用项"]),
            existing_template_rows=self.TEMPLATE,
        )
        assert len(result) == 1
        assert result[0]["match_type"] == "manual"
        assert result[0]["suggested_target"] is None
        assert result[0]["confidence"] == 0.0

    def test_dedup_labels_across_groups(self):
        """多个组出现相同标签只返回一次。"""
        h1 = "a" * 64
        h2 = "b" * 64
        groups = [
            {"hash": h1, "source_rows": [{"label": "X", "row_type": "data", "key": "X#0"}], "entities": []},
            {"hash": h2, "source_rows": [{"label": "X", "row_type": "data", "key": "X#0"}], "entities": []},
        ]
        result = suggest_template_rows(groups, existing_template_rows=[])
        assert len(result) == 1
        assert result[0]["source_label"] == "X"

    def test_empty_groups(self):
        result = suggest_template_rows([], existing_template_rows=self.TEMPLATE)
        assert result == []

    def test_no_template_all_manual(self):
        result = suggest_template_rows(
            self._groups(["A", "B", "C"]),
            existing_template_rows=[],
        )
        assert len(result) == 3
        assert all(s["match_type"] == "manual" for s in result)

    def test_alias_match_审计咨询费(self):
        """真实业务场景：审计咨询费→中介机构费。"""
        result = suggest_template_rows(
            self._groups(["审计咨询费"]),
            existing_template_rows=self.TEMPLATE,
        )
        assert result[0]["match_type"] == "alias"
        assert result[0]["suggested_target"]["canonical_name"] == "中介机构费"

    def test_multiple_labels_mixed_matches(self):
        """混合场景：精确+别名+人工。"""
        result = suggest_template_rows(
            self._groups(["职工薪酬", "审计咨询费", "非常特殊的费用"]),
            existing_template_rows=self.TEMPLATE,
        )
        assert len(result) == 3
        types = {r["source_label"]: r["match_type"] for r in result}
        assert types["职工薪酬"] == "exact"
        assert types["审计咨询费"] == "alias"
        assert types["非常特殊的费用"] == "manual"
