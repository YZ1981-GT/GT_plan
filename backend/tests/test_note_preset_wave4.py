"""Wave 4（附注校验 preset 加载/解析修复）测试.

Spec: .kiro/specs/disclosure-note-formula-and-report-sync/ Wave 4 (Task 5.1-5.5)

覆盖：
- 5.1 load_preset_rules 路径修复（基础数据/ 前缀）+ 缺失/损坏 fail-open（Property 10）
- 5.2 _parse_preset_md markdown 表格解析（表头/分隔/无表头裸行/内嵌|/未知类型）
      + bullet 与表格两格式等价且去重（Property 9）
- 5.3 inline _validation_rules 装配：collect_inline_rules_for_note 消费 +
      disclosure_engine _inject_validation_rules / _resolve_check_roles
- 5.4 build_account_section_map（复用披露模板）+ 完整性 executor 科目粒度接入（附加式）
- 5.5 Skip_On_Missing 优于误报（Property 11）
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.services.note_validation_engine import (
    NoteValidationEngine,
    ValidationContext,
    ValidationRule,
    ValidationType,
    _normalize_expr_for_dedup,
    _parse_preset_md,
    build_account_section_map,
    load_preset_rules,
)
from app.services.note_validation_executors import (
    _execute_completeness,
    _execute_cross,
)


# ---------------------------------------------------------------------------
# 5.1 + Property 10：load_preset_rules 路径修复 + fail-open
# ---------------------------------------------------------------------------

class TestLoadPresetRules:
    def test_real_soe_preset_loads_nonempty(self):
        """基础数据/ 前缀修复后：真实国企版 preset.md 能被找到并解析出规则（此前恒 []）。"""
        rules = load_preset_rules("soe")
        assert len(rules) > 0
        # 全部规则类型均为合法 ValidationType
        assert all(isinstance(r.rule_type, ValidationType) for r in rules)

    def test_real_listed_preset_loads_nonempty(self):
        rules = load_preset_rules("listed")
        assert len(rules) > 0

    def test_property10_missing_file_fail_open(self):
        """Property 10：preset 文件缺失 → 返回空规则集，不抛。"""
        rules = load_preset_rules("soe", base_dir=Path("/tmp/gt-does-not-exist-xyz-9999"))
        assert rules == []

    def test_property10_corrupt_content_fail_open(self, tmp_path):
        """Property 10：文件存在但内容非表格/无规则 → 空规则集，不抛。"""
        d = tmp_path / "基础数据" / "附注模版"
        d.mkdir(parents=True)
        (d / "国企版校验公式预设.md").write_text(
            "随便一段散文，没有任何规则表格或 bullet。\n> 引用行\n普通文字。",
            encoding="utf-8",
        )
        rules = load_preset_rules("soe", base_dir=tmp_path)
        assert isinstance(rules, list)
        assert rules == []

    def test_unknown_template_type_falls_back_soe(self):
        """未知 template_type 回退 soe（既有行为不回归）。"""
        rules = load_preset_rules("unknown_type")
        assert len(rules) > 0  # 回退到 soe 的真实规则


# ---------------------------------------------------------------------------
# 5.2：_parse_preset_md markdown 表格解析
# ---------------------------------------------------------------------------

class TestParsePresetMdTable:
    def test_table_skips_header_and_separator(self):
        md = (
            "### 4. 应收票据\n"
            "| 编号 | 公式类型 | 校验公式 |\n"
            "|------|----------|----------|\n"
            "| F4-1 | 余额 | `报表.应收票据 = 合计行` |\n"
        )
        rules = _parse_preset_md(md)
        assert len(rules) == 1
        assert rules[0].rule_type == ValidationType.BALANCE
        assert rules[0].metadata.get("rule_id") == "F4-1"
        assert rules[0].metadata.get("trigger_source") == "preset_md_table"
        assert rules[0].section_code == "4. 应收票据"

    def test_headerless_table_rows_parsed(self):
        """源模板中 **⑨ 核销** 下直接列数据行（无表头）也能解析。"""
        md = (
            "| F4-24 | 其中项 | `⑨表 sum = 合计行` |\n"
            "| F4-29 | 完整性 | `若核销金额非0则名称列非空` |\n"
        )
        rules = _parse_preset_md(md)
        assert len(rules) == 2
        assert {r.rule_type for r in rules} == {
            ValidationType.SUB_ITEM,
            ValidationType.COMPLETENESS,
        }

    def test_pipe_in_expression_rejoined(self):
        """公式列含 | 被误切时，第 3 列及之后拼回（不丢行）。"""
        md = "| F1-1 | 余额 | `a = b | c` |\n"
        rules = _parse_preset_md(md)
        assert len(rules) == 1
        assert "b" in rules[0].expression and "c" in rules[0].expression

    def test_unknown_type_skipped(self):
        md = "| X-1 | 未知类型 | `foo` |\n"
        assert _parse_preset_md(md) == []

    def test_all_validation_types_present_in_real_preset(self):
        """真实 soe preset 应覆盖多种校验类型（不止一种）。"""
        rules = load_preset_rules("soe")
        types = {r.rule_type for r in rules}
        assert ValidationType.BALANCE in types
        assert ValidationType.SUB_ITEM in types
        assert ValidationType.CROSS in types
        assert len(types) >= 5


# ---------------------------------------------------------------------------
# Property 9：bullet 与 markdown 表格两格式解析等价且去重
# ---------------------------------------------------------------------------

_EXPR_ALPHABET = "报表货币资金期末合计行①②.=abc123 "
_TYPES = [
    "余额", "宽表", "纵向", "交叉", "跨科目",
    "其中项", "二级明细", "完整性", "账龄衔接", "LLM审核",
]


class TestProperty9BulletTableEquivalence:
    @given(
        section=st.text(min_size=1, max_size=6, alphabet="一二三四五1234、"),
        type_str=st.sampled_from(_TYPES),
        expr=st.text(min_size=1, max_size=24, alphabet=_EXPR_ALPHABET),
    )
    @settings(max_examples=5)
    def test_bullet_and_table_dedup_to_one(self, section, type_str, expr):
        expr = expr.strip()
        assume(expr)
        md = (
            f"## {section}\n"
            f"- [{type_str}] {expr}\n\n"
            "| 编号 | 公式类型 | 校验公式 |\n"
            "|---|---|---|\n"
            f"| X-1 | {type_str} | `{expr}` |\n"
        )
        rules = _parse_preset_md(md)
        matching = [r for r in rules if r.rule_type.value == type_str]
        # 同 (section, type, 归一表达式) 去重为 1 条（Req5.4）
        assert len(matching) == 1

    @given(
        section=st.text(min_size=1, max_size=6, alphabet="一二三四五1234、"),
        type_str=st.sampled_from(_TYPES),
        expr=st.text(min_size=1, max_size=24, alphabet=_EXPR_ALPHABET),
    )
    @settings(max_examples=5)
    def test_bullet_equiv_table_independently(self, section, type_str, expr):
        expr = expr.strip()
        assume(expr)
        only_bullet = _parse_preset_md(f"## {section}\n- [{type_str}] {expr}\n")
        only_table = _parse_preset_md(
            f"## {section}\n"
            "| 编号 | 公式类型 | 校验公式 |\n|---|---|---|\n"
            f"| X-1 | {type_str} | `{expr}` |\n"
        )
        assert len(only_bullet) == 1
        assert len(only_table) == 1
        assert only_bullet[0].rule_type == only_table[0].rule_type
        # 归一表达式等价（表格带反引号，bullet 不带 → 去重键相同）
        assert _normalize_expr_for_dedup(only_bullet[0].expression) == \
            _normalize_expr_for_dedup(only_table[0].expression)


# ---------------------------------------------------------------------------
# 5.3：inline _validation_rules 装配 + 消费
# ---------------------------------------------------------------------------

class TestInlineRuleWiring:
    def test_collect_inline_rules_consumes_validation_rules(self):
        engine = NoteValidationEngine()
        td = {
            "_validation_rules": ["余额", "其中项"],
            "headers": ["项目", "期末余额"],
            "rows": [],
        }
        rules = engine.collect_inline_rules_for_note("五、1", td)
        assert {r.rule_type for r in rules} == {
            ValidationType.BALANCE,
            ValidationType.SUB_ITEM,
        }

    def test_collect_inline_rules_multi_table(self):
        engine = NoteValidationEngine()
        td = {"_tables": [
            {"_validation_rules": ["余额"]},
            {"_validation_rules": ["宽表"]},
        ]}
        rules = engine.collect_inline_rules_for_note("五、4", td)
        assert {r.rule_type for r in rules} == {
            ValidationType.BALANCE,
            ValidationType.WIDE_TABLE,
        }

    def test_collect_inline_rules_legacy_check_presets(self):
        engine = NoteValidationEngine()
        rules = engine.collect_inline_rules_for_note("五、1", {"_check_presets": ["余额"]})
        assert [r.rule_type for r in rules] == [ValidationType.BALANCE]

    def test_collect_inline_rules_skips_description(self):
        engine = NoteValidationEngine()
        rules = engine.collect_inline_rules_for_note("五、1", {"_validation_rules": ["描述"]})
        assert rules == []

    def test_inject_validation_rules_from_check_roles(self):
        from app.services.disclosure_engine import _inject_validation_rules

        td = {"headers": [], "rows": []}
        _inject_validation_rules(td, {"check_roles": ["余额", "其中项"]})
        assert td["_validation_rules"] == ["余额", "其中项"]
        # 不改既有键
        assert td["headers"] == [] and td["rows"] == []

    def test_resolve_check_roles_english_mapping(self):
        from app.services.disclosure_engine import _resolve_check_roles

        # balance/sub_item 映射；book_value 是单元格公式非校验类型 → 跳过
        got = _resolve_check_roles({"check_presets": ["balance", "sub_item", "book_value"]})
        assert got == ["余额", "其中项"]

    def test_inject_idempotent_no_overwrite(self):
        from app.services.disclosure_engine import _inject_validation_rules

        td = {"_validation_rules": ["余额"]}
        _inject_validation_rules(td, {"check_roles": ["其中项"]})
        assert td["_validation_rules"] == ["余额"]  # 已有不覆盖

    def test_inject_noop_when_no_check_roles(self):
        from app.services.disclosure_engine import _inject_validation_rules

        td = {"headers": [], "rows": []}
        _inject_validation_rules(td, {})
        assert "_validation_rules" not in td

    def test_seed_check_roles_flow_end_to_end(self):
        """seed 的 check_roles → 注入 → collect 消费 全链路。"""
        from app.services.disclosure_engine import _inject_validation_rules

        td = {"headers": ["项目", "期末余额"], "rows": []}
        _inject_validation_rules(td, {"check_roles": ["余额", "其中项"]})
        engine = NoteValidationEngine()
        rules = engine.collect_inline_rules_for_note("五、1", td)
        assert {r.rule_type for r in rules} == {
            ValidationType.BALANCE,
            ValidationType.SUB_ITEM,
        }


# ---------------------------------------------------------------------------
# 5.4：build_account_section_map + 完整性科目粒度
# ---------------------------------------------------------------------------

class TestAccountSectionMap:
    def test_build_map_from_seed(self):
        m = build_account_section_map()
        assert isinstance(m, dict)
        assert len(m) > 0
        # 货币资金科目 → 对应披露章节
        assert m.get("1001") == "五、1"

    def test_build_map_missing_seed_fail_open(self, tmp_path):
        # base_dir 无 seed 文件 → fail-open 返 {}
        m = build_account_section_map(base_dir=tmp_path)
        assert m == {}

    def test_completeness_account_granularity_global_finds_undisclosed(self):
        """全局模式 + account_section_map：有 TB 余额但对应章节无披露 → finding（科目粒度）。"""
        rule = ValidationRule(
            section_code="", rule_type=ValidationType.COMPLETENESS, expression="全局完整性",
        )
        ctx = ValidationContext(
            tb_data={"1001": Decimal("500")},
            note_data={},  # 无任何附注 → 五、1 缺失
            account_section_map={"1001": "五、1"},
        )
        res = _execute_completeness(rule, ctx)
        assert res.passed is False
        assert res.details.get("account_granularity") is True
        assert any(
            a["account_code"] == "1001" for a in res.details["undisclosed_accounts"]
        )

    def test_completeness_account_granularity_disclosed_ok(self):
        """全局模式：科目有余额且对应章节已披露非空 → 该科目不产 finding。"""
        rule = ValidationRule(
            section_code="", rule_type=ValidationType.COMPLETENESS, expression="全局完整性",
        )
        # note_data 覆盖全部 DEFAULT_WP_MAPPING 章节且非空，避免 section-scope 干扰
        from app.services.note_wp_mapping_service import DEFAULT_WP_MAPPING

        note_data = {sec: {"total": 100} for sec in DEFAULT_WP_MAPPING}
        note_data["五、1"] = {"total": 500}
        ctx = ValidationContext(
            tb_data={"1001": Decimal("500")},
            note_data=note_data,
            account_section_map={"1001": "五、1"},
        )
        res = _execute_completeness(rule, ctx)
        assert res.details["undisclosed_accounts"] == []

    def test_completeness_no_map_no_undisclosed_byte_identical(self):
        """account_section_map 空（默认）→ 不产 undisclosed_accounts，回退 section-scope（Req7.3）。"""
        from app.services.note_wp_mapping_service import DEFAULT_WP_MAPPING

        note_data = {sec: {"total": 100} for sec in DEFAULT_WP_MAPPING}
        rule = ValidationRule(
            section_code="五、1", rule_type=ValidationType.COMPLETENESS, expression="完整性",
        )
        ctx = ValidationContext(
            tb_data={"1001": Decimal("500")},
            note_data=note_data,
        )  # account_section_map 默认 {}
        res = _execute_completeness(rule, ctx)
        assert res.details["undisclosed_accounts"] == []
        assert res.details["account_granularity"] is False
        assert res.passed is True  # section-scope 通过


# ---------------------------------------------------------------------------
# Property 11：Skip_On_Missing 优于误报
# ---------------------------------------------------------------------------

class TestProperty11SkipOnMissing:
    def test_completeness_skip_when_no_tb(self):
        rule = ValidationRule(
            section_code="五、1", rule_type=ValidationType.COMPLETENESS, expression="完整性",
        )
        ctx = ValidationContext(tb_data={}, note_data={})
        res = _execute_completeness(rule, ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_completeness_skip_when_section_not_in_mapping(self):
        rule = ValidationRule(
            section_code="不存在的章节", rule_type=ValidationType.COMPLETENESS, expression="完整性",
        )
        ctx = ValidationContext(tb_data={"1001": Decimal("500")}, note_data={})
        res = _execute_completeness(rule, ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_cross_skip_when_section_empty(self):
        rule = ValidationRule(
            section_code="五、1", rule_type=ValidationType.CROSS, expression="cross",
        )
        ctx = ValidationContext(note_data={}, report_data={})
        res = _execute_cross(rule, ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_account_granularity_missing_map_no_false_fail(self):
        """科目粒度：account_section_map 缺该科目映射 → 不臆造 finding（漏报优于误报）。"""
        rule = ValidationRule(
            section_code="", rule_type=ValidationType.COMPLETENESS, expression="全局",
        )
        ctx = ValidationContext(
            tb_data={"9999": Decimal("500")},  # 9999 不在映射内
            note_data={},
            account_section_map={"1001": "五、1"},
        )
        res = _execute_completeness(rule, ctx)
        # 9999 无映射 → 不进 undisclosed_accounts
        assert all(
            a["account_code"] != "9999" for a in res.details["undisclosed_accounts"]
        )
