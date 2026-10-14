"""Phase 2 Task 13 测试：确定性变量替换计划与执行。"""

from __future__ import annotations

import pytest

from app.services.note_variable_replacer import (
    ReplacementPlan,
    apply_replacement_plan,
    build_replacement_plan,
)


class TestBuildReplacementPlan:
    def test_token_replacement_with_target(self):
        html = "<p>{公司名称}按照企业会计准则编制{年度}年度财务报表。</p>"
        plan = build_replacement_plan(
            html,
            target_vars={"company_name": "目标公司", "year": "2025"},
        )
        assert len(plan.items) == 2
        names = {item.variable for item in plan.items}
        assert "company_name" in names
        assert "year" in names
        assert not plan.warnings

    def test_missing_target_value_produces_warning(self):
        html = "<p>{币种}计价</p>"
        plan = build_replacement_plan(html, target_vars={})
        assert len(plan.items) == 0
        assert any("币种" in w for w in plan.warnings)

    def test_source_entity_name_replacement(self):
        html = "<p>首汽租车股份有限公司是一家交通运输企业。</p>"
        plan = build_replacement_plan(
            html,
            target_vars={"company_name": "目标运输公司"},
            source_entity_name="首汽租车股份有限公司",
        )
        entity_items = [i for i in plan.items if i.variable == "source_entity_name"]
        assert len(entity_items) == 1
        assert entity_items[0].old_value == "首汽租车股份有限公司"
        assert entity_items[0].new_value == "目标运输公司"

    def test_source_entity_without_target_warns(self):
        html = "<p>首汽租车在此</p>"
        plan = build_replacement_plan(
            html,
            target_vars={},
            source_entity_name="首汽租车",
        )
        assert len(plan.items) == 0
        assert any("首汽租车" in w for w in plan.warnings)

    def test_empty_html(self):
        plan = build_replacement_plan("", target_vars={"year": "2025"})
        assert plan.items == []
        assert plan.warnings == []

    def test_no_tokens_no_entity(self):
        html = "<p>本公司遵循会计准则。</p>"
        plan = build_replacement_plan(html, target_vars={"company_name": "A"})
        assert plan.items == []


class TestApplyReplacementPlan:
    def test_apply_all(self):
        html = "<p>{公司名称}的{年度}报表</p>"
        plan = build_replacement_plan(
            html, target_vars={"company_name": "新公司", "year": "2025"}
        )
        result = apply_replacement_plan(html, plan)
        assert "新公司" in result
        assert "2025" in result
        assert "{公司名称}" not in result
        assert "{年度}" not in result

    def test_revoke_skips_item(self):
        html = "<p>{公司名称}和{年度}</p>"
        plan = build_replacement_plan(
            html, target_vars={"company_name": "A", "year": "2025"}
        )
        # 撤销公司名替换
        company_item = next(i for i in plan.items if i.variable == "company_name")
        result = apply_replacement_plan(
            html, plan, revoked_ids={company_item.replacement_id}
        )
        assert "{公司名称}" in result  # 保留
        assert "2025" in result  # 替换

    def test_empty_plan(self):
        html = "<p>原文</p>"
        result = apply_replacement_plan(html, ReplacementPlan())
        assert result == html

    def test_each_item_has_unique_id(self):
        html = "<p>{公司名称}{年度}{币种}</p>"
        plan = build_replacement_plan(
            html,
            target_vars={"company_name": "X", "year": "2025", "currency": "人民币"},
        )
        ids = [item.replacement_id for item in plan.items]
        assert len(ids) == len(set(ids))


class TestReplacementEscapingReview:
    """复盘 R-11：替换值必须 HTML 转义；来源名按转义形态匹配；结果不得引入标签。"""

    def test_target_value_is_escaped(self):
        html = "<p>{公司名称}成立</p>"
        plan = build_replacement_plan(html, target_vars={"company_name": "A&B<公司>"})
        result = apply_replacement_plan(html, plan)
        assert result == "<p>A&amp;B&lt;公司&gt;成立</p>"

    def test_source_entity_with_ampersand_is_detected(self):
        # 消毒器输出中 & 已被转义为 &amp;，按原文匹配会漏检
        html = "<p>A&amp;B公司成立于2020年</p>"
        plan = build_replacement_plan(
            html, target_vars={"company_name": "目标公司"}, source_entity_name="A&B公司",
        )
        assert [i.variable for i in plan.items] == ["source_entity_name"]
        assert apply_replacement_plan(html, plan) == "<p>目标公司成立于2020年</p>"

    def test_script_like_target_value_cannot_inject_tags(self):
        html = "<p>{公司名称}</p>"
        plan = build_replacement_plan(html, target_vars={"company_name": "<script>x</script>"})
        result = apply_replacement_plan(html, plan)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
