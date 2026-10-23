"""集团级附注披露模板下推服务测试。

spec: consol-note-template-push-to-subsidiaries
"""
from __future__ import annotations

import pytest

from app.services.consol_note_template_push_service import (
    build_skeleton_rows,
    merge_rows,
)
from app.services.consol_note_detail_suggest import suggest_template_rows


# ── 骨架构建 ──


class TestBuildSkeletonRows:

    def test_basic_skeleton(self):
        """固定行 + 可选行 + 动态行区 → 骨架行。"""
        template = [
            {"target_row_id": "r1", "canonical_name": "库存现金", "row_type": "data", "category": "required"},
            {"target_row_id": "r2", "canonical_name": "银行存款", "row_type": "data", "category": "optional"},
            {"target_row_id": "dz", "canonical_name": "", "row_type": "data", "category": "dynamic_zone"},
            {"target_row_id": "r3", "canonical_name": "合计", "row_type": "total", "category": "required"},
        ]
        rows = build_skeleton_rows(template)
        assert len(rows) == 4
        # 固定行
        assert rows[0]["label"] == "库存现金"
        assert rows[0]["_pushed_row_id"] == "r1"
        assert rows[0]["_pushed_category"] == "required"
        assert "_pushed_optional_active" not in rows[0]
        # 可选行
        assert rows[1]["label"] == "银行存款"
        assert rows[1]["_pushed_category"] == "optional"
        assert rows[1]["_pushed_optional_active"] is True
        # 动态行区
        assert rows[2]["row_type"] == "dynamic_zone_marker"
        assert rows[2]["_pushed_row_id"] == "dz"
        # 合计行
        assert rows[3]["label"] == "合计"
        assert rows[3]["row_type"] == "total"

    def test_empty_template(self):
        assert build_skeleton_rows([]) == []

    def test_values_are_empty(self):
        """骨架行的金额为空。"""
        template = [{"target_row_id": "x", "canonical_name": "A", "row_type": "data", "category": "required"}]
        rows = build_skeleton_rows(template)
        assert rows[0]["values"] == []


# ── 增量合并 ──


class TestMergeRows:

    def test_new_push_creates_rows(self):
        """子企业无已有行 → 全部新建。"""
        template = [
            {"target_row_id": "r1", "canonical_name": "库存现金", "row_type": "data", "category": "required"},
            {"target_row_id": "r2", "canonical_name": "合计", "row_type": "total", "category": "required"},
        ]
        merged = merge_rows(template, [])
        assert len(merged) == 2
        assert merged[0]["label"] == "库存现金"
        assert merged[0]["_pushed_row_id"] == "r1"

    def test_existing_values_preserved(self):
        """增量合并保留子企业已填的金额。"""
        template = [
            {"target_row_id": "r1", "canonical_name": "库存现金（新名字）", "row_type": "data", "category": "required"},
        ]
        existing = [
            {"label": "库存现金", "values": [100.5, 200.3], "_pushed_row_id": "r1", "_pushed_category": "required"},
        ]
        merged = merge_rows(template, existing)
        assert len(merged) == 1
        assert merged[0]["label"] == "库存现金（新名字）"  # 行名更新
        assert merged[0]["values"] == [100.5, 200.3]  # 金额保留

    def test_user_added_rows_in_dynamic_zone(self):
        """用户新增行放在动态行区。"""
        template = [
            {"target_row_id": "r1", "canonical_name": "A", "row_type": "data", "category": "required"},
            {"target_row_id": "dz", "canonical_name": "", "row_type": "data", "category": "dynamic_zone"},
            {"target_row_id": "r2", "canonical_name": "合计", "row_type": "total", "category": "required"},
        ]
        existing = [
            {"label": "A", "values": [10], "_pushed_row_id": "r1"},
            {"label": "用户自定义行", "values": [50]},  # 无 _pushed_row_id = 用户新增
            {"label": "合计", "values": [60], "_pushed_row_id": "r2"},
        ]
        merged = merge_rows(template, existing)
        labels = [r["label"] for r in merged]
        # A → 用户自定义行 → 动态行区占位 → 合计
        assert labels == ["A", "用户自定义行", "", "合计"]
        assert merged[2]["row_type"] == "dynamic_zone_marker"
        # 用户行金额保留
        assert merged[1]["values"] == [50]

    def test_new_template_row_added(self):
        """模板新增行（子企业之前没有的）→ 插入空行。"""
        template = [
            {"target_row_id": "r1", "canonical_name": "A", "row_type": "data", "category": "required"},
            {"target_row_id": "r_new", "canonical_name": "B新增", "row_type": "data", "category": "required"},
        ]
        existing = [
            {"label": "A", "values": [10], "_pushed_row_id": "r1"},
        ]
        merged = merge_rows(template, existing)
        assert len(merged) == 2
        assert merged[1]["label"] == "B新增"
        assert merged[1]["values"] == []
        assert merged[1]["_pushed_row_id"] == "r_new"

    def test_optional_flag_preserved(self):
        """可选行的 optional_active 标记保留。"""
        template = [
            {"target_row_id": "r1", "canonical_name": "X", "row_type": "data", "category": "optional"},
        ]
        existing = [
            {"label": "X", "values": [5], "_pushed_row_id": "r1", "_pushed_optional_active": False},
        ]
        merged = merge_rows(template, existing)
        assert merged[0]["_pushed_optional_active"] is False  # 子企业已取消勾选，保留


# ── row_id 精确匹配 ──


class TestSuggestRowIdMatch:

    def test_pushed_row_id_exact_match(self):
        """来源行带 _pushed_row_id → 第 0 级 exact_id 匹配。"""
        groups = [{
            "hash": "x",
            "entities": [],
            "source_rows": [
                {"label": "库存现金", "_pushed_row_id": "rid-001"},
                {"label": "银行存款", "_pushed_row_id": "rid-002"},
                {"label": "用户自定义行"},  # 无 rid → 走七级匹配
            ],
        }]
        template_rows = [
            {"target_row_id": "rid-001", "canonical_name": "库存现金", "aliases": []},
            {"target_row_id": "rid-002", "canonical_name": "银行存款", "aliases": []},
        ]
        result = suggest_template_rows(groups, existing_template_rows=template_rows)
        assert len(result) == 3
        # 前两个按 row_id 匹配
        assert result[0]["match_type"] == "exact_id"
        assert result[0]["confidence"] == 1.0
        assert result[1]["match_type"] == "exact_id"
        # 第三个没有 rid → manual
        assert result[2]["match_type"] == "manual"

    def test_rid_takes_priority_over_name(self):
        """row_id 匹配优先于名字匹配——即使名字改了也能匹配。"""
        groups = [{
            "hash": "x",
            "entities": [],
            "source_rows": [
                {"label": "现金及现金等价物", "_pushed_row_id": "rid-001"},  # 名字不同但 rid 相同
            ],
        }]
        template_rows = [
            {"target_row_id": "rid-001", "canonical_name": "库存现金", "aliases": []},
        ]
        result = suggest_template_rows(groups, existing_template_rows=template_rows)
        assert result[0]["match_type"] == "exact_id"
        assert result[0]["suggested_target"]["canonical_name"] == "库存现金"

    def test_no_rid_falls_through_to_name_match(self):
        """无 _pushed_row_id 的行正常走七级匹配。"""
        groups = [{
            "hash": "x",
            "entities": [],
            "source_rows": [{"label": "库存现金"}],
        }]
        template_rows = [
            {"target_row_id": "rid-001", "canonical_name": "库存现金", "aliases": []},
        ]
        result = suggest_template_rows(groups, existing_template_rows=template_rows)
        assert result[0]["match_type"] == "exact"  # 名字精确匹配，不是 exact_id


# ── category 校验 ──


class TestCategoryValidation:

    def test_default_category_is_required(self):
        """不传 category 默认 required。"""
        from app.services.consol_note_detail_template_service import _validate_template_rows
        rows = [{"canonical_name": "测试行"}]
        validated = _validate_template_rows(rows)
        assert validated[0]["category"] == "required"

    def test_dynamic_zone_allows_empty_name(self):
        """dynamic_zone 行允许空 canonical_name。"""
        from app.services.consol_note_detail_template_service import _validate_template_rows
        rows = [{"category": "dynamic_zone"}]
        validated = _validate_template_rows(rows)
        assert validated[0]["canonical_name"] == "[动态行区]"
        assert validated[0]["category"] == "dynamic_zone"

    def test_invalid_category_defaults_to_required(self):
        from app.services.consol_note_detail_template_service import _validate_template_rows
        rows = [{"canonical_name": "X", "category": "invalid"}]
        validated = _validate_template_rows(rows)
        assert validated[0]["category"] == "required"
