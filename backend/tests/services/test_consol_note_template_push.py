"""集团级附注披露模板下推服务测试（纯函数）。

spec: consol-note-template-push-to-subsidiaries；note-pull-header-formula-closure R6.1 改写入规则：
不写动态行区占位行（编辑器 / Word / 空表判定都不认它）、不改子企业已有行名（行身份靠 ``_pushed_row_id``）、
新行按本表列宽补空；写库行为见 ``test_consol_note_template_push_db.py``。
"""
from __future__ import annotations

import pytest

from app.services.consol_note_template_push_service import (
    build_skeleton_rows,
    merge_rows,
    plan_merge,
)
from app.services.consol_note_detail_suggest import suggest_template_rows


# ── 骨架构建 ──


class TestBuildSkeletonRows:

    def test_basic_skeleton(self):
        """固定行 + 可选行 → 骨架行；动态行区占位不写（没有读取方认它）。"""
        template = [
            {"target_row_id": "r1", "canonical_name": "库存现金", "row_type": "data", "category": "required"},
            {"target_row_id": "r2", "canonical_name": "银行存款", "row_type": "data", "category": "optional"},
            {"target_row_id": "dz", "canonical_name": "", "row_type": "data", "category": "dynamic_zone"},
            {"target_row_id": "r3", "canonical_name": "合计", "row_type": "total", "category": "required"},
        ]
        rows = build_skeleton_rows(template, width=2)
        assert len(rows) == 3
        # 固定行
        assert rows[0]["label"] == "库存现金"
        assert rows[0]["_pushed_row_id"] == "r1"
        assert rows[0]["_pushed_category"] == "required"
        assert "_pushed_optional_active" not in rows[0]
        # 可选行
        assert rows[1]["label"] == "银行存款"
        assert rows[1]["_pushed_category"] == "optional"
        assert rows[1]["_pushed_optional_active"] is True
        # 没有动态行区占位行；合计行
        assert all(r["row_type"] != "dynamic_zone_marker" for r in rows)
        assert rows[2]["label"] == "合计"
        assert rows[2]["row_type"] == "total"
        # 值按列宽补空
        assert all(r["values"] == [None, None] for r in rows)

    def test_placeholder_row_not_written_even_if_marked_required(self):
        """「……」可扩位占位行按行名认：模板把它标成固定行（自动映射修复前建的、用户手建的模板）也不写进子企业附注
        —— 推进去就是删不掉的空行（下推的固定行编辑器不让删；2026-10-26 浏览器实测【测试】甲 五、5 被补了「……」）。"""
        template = [
            {"target_row_id": "a", "canonical_name": "1年以内", "row_type": "data", "category": "required"},
            {"target_row_id": "p", "canonical_name": "……", "row_type": "data", "category": "required"},
            {"target_row_id": "q", "canonical_name": " ... ", "row_type": "data", "category": "required"},
            {"target_row_id": "t", "canonical_name": "合计", "row_type": "total", "category": "required"},
        ]
        assert [r["label"] for r in build_skeleton_rows(template, width=1)] == ["1年以内", "合计"]
        plan = plan_merge(template, [{"label": "合计", "values": [2], "row_type": "total"}], width=1)
        assert [r["label"] for r in plan.rows] == ["1年以内", "合计"] and plan.added == 1

    def test_previously_pushed_placeholder_row_is_released(self):
        """修复前已推进子企业的「……」行：再下推时去掉下推标记（行留在原处、变成子企业自己的行，编辑器可以删）。"""
        template = [
            {"target_row_id": "a", "canonical_name": "1年以内", "row_type": "data", "category": "required"},
            {"target_row_id": "p", "canonical_name": "……", "row_type": "data", "category": "required"},
        ]
        existing = [{"label": "1年以内", "values": [1], "_pushed_row_id": "a", "_pushed_category": "required"},
                    {"label": "……", "values": [None], "_pushed_row_id": "p", "_pushed_category": "required"}]
        plan = plan_merge(template, existing, width=1)
        assert [r["label"] for r in plan.rows] == ["1年以内", "……"]
        assert plan.rows[0]["_pushed_row_id"] == "a" and "_pushed_row_id" not in plan.rows[1]
        assert "_pushed_category" not in plan.rows[1] and (plan.claimed, plan.released) == (1, 1)

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
        """增量合并保留子企业已填的金额；已有行名不改（行身份靠 _pushed_row_id，改名会让子企业公式推送找不到行）。"""
        template = [
            {"target_row_id": "r1", "canonical_name": "库存现金（新名字）", "row_type": "data", "category": "required"},
        ]
        existing = [
            {"label": "库存现金", "values": [100.5, 200.3], "_pushed_row_id": "r1", "_pushed_category": "required"},
        ]
        merged = merge_rows(template, existing)
        assert len(merged) == 1
        assert merged[0]["label"] == "库存现金"  # 行名不改
        assert merged[0]["values"] == [100.5, 200.3]  # 金额保留
        assert merged[0]["_pushed_row_id"] == "r1"

    def test_user_added_rows_stay_in_place(self):
        """子企业自己加的行留在原位，不插动态行区占位行。"""
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
        assert labels == ["A", "用户自定义行", "合计"]
        assert all(r.get("row_type") != "dynamic_zone_marker" for r in merged)
        # 用户行金额保留、不带下推标记
        assert merged[1]["values"] == [50] and "_pushed_row_id" not in merged[1]

    def test_new_template_row_added(self):
        """模板新增行（子企业之前没有的）→ 插入空行。"""
        template = [
            {"target_row_id": "r1", "canonical_name": "A", "row_type": "data", "category": "required"},
            {"target_row_id": "r_new", "canonical_name": "B新增", "row_type": "data", "category": "required"},
        ]
        existing = [
            {"label": "A", "values": [10], "_pushed_row_id": "r1"},
        ]
        merged = merge_rows(template, existing, width=1)
        assert len(merged) == 2
        assert merged[1]["label"] == "B新增"
        assert merged[1]["values"] == [None]
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


# ── 认领规则 ──


class TestPlanMerge:

    TEMPLATE = [
        {"target_row_id": "a", "canonical_name": "库存现金", "aliases": ["现金"], "row_type": "data"},
        {"target_row_id": "x", "canonical_name": "数字货币", "aliases": [], "row_type": "data"},
        {"target_row_id": "b", "canonical_name": "银行存款", "aliases": [], "row_type": "data"},
        {"target_row_id": "s1", "canonical_name": "小计", "aliases": [], "row_type": "subtotal"},
        {"target_row_id": "s2", "canonical_name": "小计", "aliases": [], "row_type": "subtotal"},
        {"target_row_id": "t", "canonical_name": "合计", "aliases": [], "row_type": "total"},
    ]

    def test_claims_by_alias_and_inserts_missing_before_next_claimed_row(self):
        existing = [{"label": "现  金", "values": [1]}, {"label": "其中：备用金", "values": [1]},
                    {"label": "银行存款", "values": [2]}, {"label": "合计", "values": [3], "row_type": "total"}]
        plan = plan_merge(self.TEMPLATE, existing, width=1)
        assert [r["label"] for r in plan.rows] == ["现  金", "其中：备用金", "数字货币", "银行存款", "小计", "小计", "合计"]
        assert [r.get("_pushed_row_id") for r in plan.rows] == ["a", None, "x", "b", "s1", "s2", "t"]
        assert (plan.claimed, plan.added, plan.claimed_detail) == (3, 3, 2)

    def test_declared_row_type_mismatch_still_claims_same_name_row(self):
        """同名即同一行：模板把「账面价值」声明为合计、子企业是普通行 —— 认领，不补出一条重名行。"""
        template = [{"target_row_id": "v", "canonical_name": "账面价值", "aliases": [], "row_type": "total"}]
        plan = plan_merge(template, [{"label": "账面价值", "values": [9]}], width=1)
        assert [(r["label"], r.get("_pushed_row_id"), r["values"]) for r in plan.rows] == [("账面价值", "v", [9])]
        assert (plan.claimed, plan.added) == (1, 0)

    def test_same_name_rows_pair_in_order_and_bare_total_label_is_claimed(self):
        existing = [{"label": "银行存款", "values": [1]}, {"label": "小计", "values": [1], "row_type": "subtotal"},
                    {"label": "库存现金", "values": [2]}, {"label": "小计", "values": [2], "row_type": "subtotal"},
                    {"label": "合计", "values": [3]}]
        plan = plan_merge(self.TEMPLATE, existing)
        rid = {r["label"] + str(r["values"]): r.get("_pushed_row_id") for r in plan.rows}
        assert rid["小计[1]"] == "s1" and rid["小计[2]"] == "s2", "同名小计按顺序对应"
        assert rid["合计[3]"] == "t", "只有行名的「合计」也按合计认"

    def test_does_not_mutate_input_rows(self):
        existing = [{"label": "库存现金", "values": [1]}]
        snapshot = [dict(r) for r in existing]
        plan_merge(self.TEMPLATE, existing)
        assert existing == snapshot


class TestPushedRowsThroughProductionReader:
    """下推后的单体附注经生产读取层 → 结构指纹 → 建议：固定行按行身份 exact_id（原 e2e 用例直接手造来源行，绕过了
    丢掉 ``_pushed_row_id`` 的读取层 ⇒ 生产里 exact_id 从不触发）。"""

    def test_exact_id_survives_reader_and_rename(self):
        from app.services.consol_note_detail_source_service import extract_source_rows
        from app.services.consol_note_formula_service import find_table
        from app.services.consol_note_standalone_reader import read_source_table

        template = [
            {"target_row_id": "r-cash", "canonical_name": "库存现金", "aliases": [], "row_type": "data"},
            {"target_row_id": "r-bank", "canonical_name": "银行存款", "aliases": [], "row_type": "data"},
            {"target_row_id": "r-total", "canonical_name": "合计", "aliases": [], "row_type": "total"},
        ]
        table = {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
                 "rows": [{"label": "库存现金", "values": [1.0, 2.0]}, {"label": "银行存款", "values": [3.0, 4.0]},
                          {"label": "合计", "values": [4.0, 6.0], "row_type": "total"}]}
        rows = merge_rows(template, table["rows"], width=2)
        rows[0]["label"] = "现金及现金等价物"  # 子企业改了行名
        td = {"_tables": [{**table, "rows": rows}]}
        source = read_source_table(td, consol_table=find_table("soe", "五-1-1"), table_name="货币资金", title="货币资金",
                                   section_title="货币资金", std="soe", consol_section_id="五-1-1", standalone_section="八、1")
        assert [r.get("_pushed_row_id") for r in source.rows] == ["r-cash", "r-bank", "r-total"]
        groups = [{"hash": "h", "entities": [], "source_rows": extract_source_rows(source.rows)}]
        result = {s["source_label"]: s for s in suggest_template_rows(groups, existing_template_rows=template)}
        assert result["现金及现金等价物"]["match_type"] == "exact_id"
        assert result["现金及现金等价物"]["suggested_target"]["target_row_id"] == "r-cash"
