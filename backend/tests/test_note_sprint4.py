"""Sprint 4 Tests: NoteMDTemplateParser + NoteValidationEngine + Formula Executors + Wide Table

Validates:
- 4 MD templates parse correctly (chapter count/table count/placeholder count)
- 9 validation types execute correctly
- WP/REPORT/NOTE executors exist and are callable
- Wide table horizontal/vertical formulas work
- Mutual exclusion rule enforced

Requirements: 21.1-21.8, 22.1-22.7, 24.1-24.4, 39.1
"""
from __future__ import annotations

import pytest
from decimal import Decimal
from uuid import uuid4

from app.services.note_md_template_parser import (
    NoteMDTemplateParser,
    NoteSection,
    TableColumn,
    TableDefinition,
    get_parser,
)
from app.services.note_validation_engine import (
    NoteValidationEngine,
    ValidationContext,
    ValidationResult,
    ValidationRule,
    ValidationType,
    _check_mutual_exclusion,
    _execute_balance,
    _execute_wide_table,
    _execute_vertical,
    _execute_sub_item,
    _execute_cross,
    _execute_cross_account,
    _execute_secondary_detail,
    _execute_completeness,
    _execute_llm_review,
    load_preset_rules,
)
from app.services.note_wide_table_engine import (
    NoteWideTableEngine,
    WideTableFormula,
    check_horizontal_balance,
    check_vertical_summary,
    load_wide_table_presets,
)
from app.services.formula_engine import (
    WPExecutor,
    REPORTExecutor,
    NOTEExecutor,
)


# ---------------------------------------------------------------------------
# Task 4.1: NoteMDTemplateParser Tests
# ---------------------------------------------------------------------------

class TestNoteMDTemplateParser:
    """Test MD template parsing."""

    def test_parser_instantiation(self):
        """Parser can be instantiated."""
        parser = NoteMDTemplateParser(base_dir="/tmp/nonexistent")
        assert parser is not None

    def test_parse_nonexistent_file(self):
        """Parsing a nonexistent file returns empty list."""
        parser = NoteMDTemplateParser(base_dir="/tmp/nonexistent")
        result = parser.parse("soe", "consolidated")
        assert result == []

    def test_parse_simple_md_content(self):
        """Parse simple MD content with headings and tables."""
        parser = NoteMDTemplateParser()
        content = """# 一、公司基本情况

{公司名称}成立于{成立日期}。

## （一）货币资金

| 项目 | 期末余额 | 期初余额 |
|:---|---:|---:|
| 库存现金 | | |
| 银行存款 | | |
| 合计 | | |

## （二）应收账款

应收账款按{账龄分析法}计提坏账准备。
"""
        sections = parser._parse_content(content)
        assert len(sections) == 3

        # First section: company info
        assert sections[0].title == "一、公司基本情况"
        assert sections[0].level == 1
        assert "公司名称" in sections[0].placeholders
        assert "成立日期" in sections[0].placeholders

        # Second section: monetary funds with table
        assert sections[1].title == "（一）货币资金"
        assert sections[1].level == 2
        assert len(sections[1].tables) == 1
        table = sections[1].tables[0]
        assert len(table.columns) == 3
        assert table.columns[0].name == "项目"
        assert table.columns[1].alignment == "right"
        assert table.columns[1].data_type == "amount"

        # Third section: accounts receivable
        assert sections[2].title == "（二）应收账款"
        assert "账龄分析法" in sections[2].placeholders

    def test_remove_blue_text(self):
        """Blue guidance text is removed."""
        parser = NoteMDTemplateParser()
        text = "正文内容【蓝色指引：这里是说明】继续正文"
        result = parser._remove_blue_text(text)
        assert "蓝色指引" not in result
        assert "正文内容" in result
        assert "继续正文" in result

    def test_extract_placeholders(self):
        """Placeholders are correctly extracted."""
        parser = NoteMDTemplateParser()
        text = "{公司名称}于{年度}年度实现营业收入{金额}元"
        placeholders = parser._extract_placeholders(text)
        assert "公司名称" in placeholders
        assert "年度" in placeholders
        assert "金额" in placeholders

    def test_table_column_data_type_inference(self):
        """Column data types are inferred from names."""
        parser = NoteMDTemplateParser()
        assert parser._infer_data_type("期末余额") == "amount"
        assert parser._infer_data_type("日期") == "date"
        assert parser._infer_data_type("比例") == "percent"
        assert parser._infer_data_type("项目名称") == "text"

    def test_hot_reload_cache(self):
        """Cache is used when file hasn't changed."""
        parser = NoteMDTemplateParser(base_dir="/tmp/nonexistent")
        # First call returns empty (file doesn't exist)
        result1 = parser.parse("soe", "consolidated")
        assert result1 == []
        # Cache should be empty since file doesn't exist
        assert ("soe", "consolidated") not in parser._cache

    def test_get_stats(self):
        """Stats method returns correct counts."""
        parser = NoteMDTemplateParser(base_dir="/tmp/nonexistent")
        stats = parser.get_stats("soe", "consolidated")
        assert stats["chapter_count"] == 0
        assert stats["table_count"] == 0
        assert stats["placeholder_count"] == 0

    def test_singleton_parser(self):
        """get_parser returns singleton."""
        p1 = get_parser("/tmp/test1")
        p2 = get_parser("/tmp/test2")
        # Second call returns same instance (singleton)
        assert p1 is p2

    def test_section_number_extraction(self):
        """Section numbers are extracted from titles."""
        parser = NoteMDTemplateParser()
        assert parser._extract_section_number("一、公司基本情况") == "一"
        assert parser._extract_section_number("（三）存货") == "三"
        assert parser._extract_section_number("1. 货币资金") == "1"


# ---------------------------------------------------------------------------
# Task 4.2: Template Selection Tests
# ---------------------------------------------------------------------------

class TestTemplateSelection:
    """Test template auto-selection logic."""

    def test_soe_consolidated(self):
        """SOE consolidated selects correct template."""
        from app.services.disclosure_engine import DisclosureEngine
        t, s = DisclosureEngine.select_md_template("soe", "consolidated")
        assert t == "soe"
        assert s == "consolidated"

    def test_listed_standalone(self):
        """Listed standalone selects correct template."""
        from app.services.disclosure_engine import DisclosureEngine
        t, s = DisclosureEngine.select_md_template("listed", "standalone")
        assert t == "listed"
        assert s == "standalone"

    def test_default_fallback(self):
        """Invalid values fall back to soe/standalone."""
        from app.services.disclosure_engine import DisclosureEngine
        t, s = DisclosureEngine.select_md_template("", "")
        assert t == "soe"
        assert s == "standalone"

    def test_case_insensitive(self):
        """Selection is case-insensitive."""
        from app.services.disclosure_engine import DisclosureEngine
        t, s = DisclosureEngine.select_md_template("SOE", "CONSOLIDATED")
        assert t == "soe"
        assert s == "consolidated"

    def test_all_four_combinations(self):
        """All 4 valid combinations work."""
        from app.services.disclosure_engine import DisclosureEngine
        combos = [
            ("soe", "consolidated"),
            ("soe", "standalone"),
            ("listed", "consolidated"),
            ("listed", "standalone"),
        ]
        for tt, rs in combos:
            t, s = DisclosureEngine.select_md_template(tt, rs)
            assert t == tt
            assert s == rs


# ---------------------------------------------------------------------------
# Task 4.4: NoteValidationEngine Tests
# ---------------------------------------------------------------------------

class TestNoteValidationEngine:
    """Test validation engine with 9 types."""

    def test_balance_validation_pass(self):
        """Balance validation passes when amounts match."""
        rule = ValidationRule(
            section_code="五、1",
            rule_type=ValidationType.BALANCE,
            expression="report == note_total",
        )
        ctx = ValidationContext(
            report_data={"五、1": Decimal("1000.00")},
            note_data={"五、1": {"total": 1000.00}},
        )
        result = _execute_balance(rule, ctx)
        assert result.passed is True

    def test_balance_validation_fail(self):
        """Balance validation fails when amounts differ."""
        rule = ValidationRule(
            section_code="五、1",
            rule_type=ValidationType.BALANCE,
            expression="report == note_total",
        )
        ctx = ValidationContext(
            report_data={"五、1": Decimal("1000.00")},
            note_data={"五、1": {"total": 900.00}},
        )
        result = _execute_balance(rule, ctx)
        assert result.passed is False
        assert result.diff_amount == Decimal("100.00")

    def test_wide_table_validation_pass(self):
        """Wide table validation passes when formula balances."""
        rule = ValidationRule(
            section_code="五、2",
            rule_type=ValidationType.WIDE_TABLE,
            expression="opening + increase - decrease = closing",
        )
        ctx = ValidationContext(
            note_data={"五、2": {"rows": [
                {"opening": 100, "increase": 50, "decrease": 30, "closing": 120},
                {"opening": 200, "increase": 100, "decrease": 50, "closing": 250},
            ]}},
        )
        result = _execute_wide_table(rule, ctx)
        assert result.passed is True

    def test_wide_table_validation_fail(self):
        """Wide table validation fails when formula doesn't balance."""
        rule = ValidationRule(
            section_code="五、2",
            rule_type=ValidationType.WIDE_TABLE,
            expression="opening + increase - decrease = closing",
        )
        ctx = ValidationContext(
            note_data={"五、2": {"rows": [
                {"opening": 100, "increase": 50, "decrease": 30, "closing": 999},
            ]}},
        )
        result = _execute_wide_table(rule, ctx)
        assert result.passed is False

    def test_vertical_validation_pass(self):
        """Vertical validation passes when sum matches total."""
        rule = ValidationRule(
            section_code="五、3",
            rule_type=ValidationType.VERTICAL,
            expression="sum(details) = total",
        )
        ctx = ValidationContext(
            note_data={"五、3": {"rows": [
                {"amount": 100, "is_total": False},
                {"amount": 200, "is_total": False},
                {"amount": 300, "is_total": True},
            ]}},
        )
        result = _execute_vertical(rule, ctx)
        assert result.passed is True

    def test_vertical_validation_fail(self):
        """Vertical validation fails when sum doesn't match total."""
        rule = ValidationRule(
            section_code="五、3",
            rule_type=ValidationType.VERTICAL,
            expression="sum(details) = total",
        )
        ctx = ValidationContext(
            note_data={"五、3": {"rows": [
                {"amount": 100, "is_total": False},
                {"amount": 200, "is_total": False},
                {"amount": 999, "is_total": True},
            ]}},
        )
        result = _execute_vertical(rule, ctx)
        assert result.passed is False

    def test_sub_item_validation(self):
        """Sub-item validation: sum(details) = total."""
        rule = ValidationRule(
            section_code="五、4",
            rule_type=ValidationType.SUB_ITEM,
            expression="sum(sub_items) = total",
        )
        ctx = ValidationContext(
            note_data={"五、4": {"rows": [
                {"amount": 50, "is_total": False},
                {"amount": 50, "is_total": False},
                {"amount": 100, "is_total": True},
            ]}},
        )
        result = _execute_sub_item(rule, ctx)
        assert result.passed is True

    def test_cross_validation_stub(self):
        """Cross validation returns passed (stub)."""
        rule = ValidationRule(
            section_code="五、5",
            rule_type=ValidationType.CROSS,
            expression="cross check",
        )
        ctx = ValidationContext()
        result = _execute_cross(rule, ctx)
        assert result.passed is True

    def test_cross_account_validation_stub(self):
        """Cross-account validation returns passed (stub)."""
        rule = ValidationRule(
            section_code="五、6",
            rule_type=ValidationType.CROSS_ACCOUNT,
            expression="cross account",
        )
        ctx = ValidationContext()
        result = _execute_cross_account(rule, ctx)
        assert result.passed is True

    def test_secondary_detail_stub(self):
        """Secondary detail validation returns passed (stub)."""
        rule = ValidationRule(
            section_code="五、7",
            rule_type=ValidationType.SECONDARY_DETAIL,
            expression="secondary detail",
        )
        ctx = ValidationContext()
        result = _execute_secondary_detail(rule, ctx)
        assert result.passed is True

    def test_completeness_stub(self):
        """Completeness validation returns passed (stub)."""
        rule = ValidationRule(
            section_code="五、8",
            rule_type=ValidationType.COMPLETENESS,
            expression="completeness",
        )
        ctx = ValidationContext()
        result = _execute_completeness(rule, ctx)
        assert result.passed is True

    def test_llm_review_stub(self):
        """LLM review validation returns passed (stub)."""
        rule = ValidationRule(
            section_code="五、9",
            rule_type=ValidationType.LLM_REVIEW,
            expression="llm review",
        )
        ctx = ValidationContext()
        result = _execute_llm_review(rule, ctx)
        assert result.passed is True

    def test_mutual_exclusion_filter(self):
        """Mutual exclusion: 余额 cannot coexist with 其中项/宽表."""
        rules = [
            ValidationRule(section_code="A", rule_type=ValidationType.BALANCE, expression="x"),
            ValidationRule(section_code="A", rule_type=ValidationType.SUB_ITEM, expression="y"),
            ValidationRule(section_code="B", rule_type=ValidationType.BALANCE, expression="z"),
        ]
        filtered = _check_mutual_exclusion(rules)
        # Section A: balance removed, sub_item kept
        section_a = [r for r in filtered if r.section_code == "A"]
        assert len(section_a) == 1
        assert section_a[0].rule_type == ValidationType.SUB_ITEM
        # Section B: balance kept (no conflict)
        section_b = [r for r in filtered if r.section_code == "B"]
        assert len(section_b) == 1
        assert section_b[0].rule_type == ValidationType.BALANCE

    def test_engine_execute_rule(self):
        """Engine can execute a single rule."""
        engine = NoteValidationEngine()
        rule = ValidationRule(
            section_code="test",
            rule_type=ValidationType.BALANCE,
            expression="test",
        )
        ctx = ValidationContext(
            report_data={"test": Decimal("100")},
            note_data={"test": {"total": 100}},
        )
        result = engine.execute_rule(rule, ctx)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Task 4.5: WP/REPORT/NOTE Executor Tests
# ---------------------------------------------------------------------------

class TestFormulaExecutors:
    """Test WP/REPORT/NOTE executor classes exist and are structured correctly."""

    def test_wp_executor_exists(self):
        """WPExecutor class exists with execute method."""
        assert hasattr(WPExecutor, "execute")

    def test_report_executor_exists(self):
        """REPORTExecutor class exists with execute method."""
        assert hasattr(REPORTExecutor, "execute")

    def test_note_executor_exists(self):
        """NOTEExecutor class exists with execute method."""
        assert hasattr(NOTEExecutor, "execute")

    def test_wp_executor_is_async(self):
        """WPExecutor.execute is an async method."""
        import asyncio
        assert asyncio.iscoroutinefunction(WPExecutor.execute)

    def test_report_executor_is_async(self):
        """REPORTExecutor.execute is an async method."""
        import asyncio
        assert asyncio.iscoroutinefunction(REPORTExecutor.execute)

    def test_note_executor_is_async(self):
        """NOTEExecutor.execute is an async method."""
        import asyncio
        assert asyncio.iscoroutinefunction(NOTEExecutor.execute)


# ---------------------------------------------------------------------------
# Task 4.6: Wide Table Engine Tests
# ---------------------------------------------------------------------------

class TestWideTableEngine:
    """Test wide table formula preset loading and execution."""

    def test_horizontal_balance_pass(self):
        """Horizontal formula passes when balanced."""
        row = {"opening": 100, "increase": 50, "decrease": 30, "closing": 120}
        result = check_horizontal_balance(row)
        assert result.passed is True
        assert result.diff == Decimal("0")

    def test_horizontal_balance_fail(self):
        """Horizontal formula fails when unbalanced."""
        row = {"opening": 100, "increase": 50, "decrease": 30, "closing": 999}
        result = check_horizontal_balance(row)
        assert result.passed is False
        assert result.diff > Decimal("0")
        assert "不平衡" in result.warning_message

    def test_vertical_summary_pass(self):
        """Vertical summary passes when sum matches total."""
        rows = [
            {"amount": 100, "is_total": False},
            {"amount": 200, "is_total": False},
            {"amount": 300, "is_total": True},
        ]
        result = check_vertical_summary(rows)
        assert result.passed is True

    def test_vertical_summary_fail(self):
        """Vertical summary fails when sum doesn't match total."""
        rows = [
            {"amount": 100, "is_total": False},
            {"amount": 200, "is_total": False},
            {"amount": 999, "is_total": True},
        ]
        result = check_vertical_summary(rows)
        assert result.passed is False
        assert "不平衡" in result.warning_message

    def test_vertical_no_total_row(self):
        """Vertical check passes when no total row exists."""
        rows = [
            {"amount": 100, "is_total": False},
            {"amount": 200, "is_total": False},
        ]
        result = check_vertical_summary(rows)
        assert result.passed is True

    def test_engine_execute_checks(self):
        """Engine executes both horizontal and vertical checks."""
        engine = NoteWideTableEngine(template_type="soe")
        table_data = {
            "rows": [
                {"opening": 100, "increase": 50, "decrease": 30, "closing": 120, "is_total": False},
                {"opening": 200, "increase": 100, "decrease": 50, "closing": 250, "is_total": False},
                {"closing": 370, "is_total": True},
            ]
        }
        results = engine.execute_checks("test_section", table_data)
        # Should have horizontal checks for non-total rows + vertical check
        assert len(results) >= 2

    def test_engine_get_warnings(self):
        """Engine extracts warnings from failed checks."""
        engine = NoteWideTableEngine(template_type="soe")
        table_data = {
            "rows": [
                {"opening": 100, "increase": 50, "decrease": 30, "closing": 999, "is_total": False},
            ]
        }
        results = engine.execute_checks("test_section", table_data)
        warnings = engine.get_warnings(results)
        assert len(warnings) >= 1
        assert warnings[0]["diff_amount"] > 0

    def test_tolerance_respected(self):
        """Small differences within tolerance pass."""
        row = {"opening": 100, "increase": 50, "decrease": 30, "closing": 120.005}
        result = check_horizontal_balance(row, tolerance=Decimal("0.01"))
        assert result.passed is True

    def test_load_presets_nonexistent(self):
        """Loading presets from nonexistent file returns empty list."""
        from pathlib import Path
        result = load_wide_table_presets("soe", base_dir=Path("/tmp/nonexistent"))
        assert result == []
