"""零回归安全网 — 4 个已实现 executor 的 characterization 测试 + 契约锁定.

Spec:   .kiro/specs/disclosure-note-validation-completion/ Wave 0 Task 1
Reqs:   9.5  Property: 12

目的：在补齐 ValidationContext 数据装配 + 落地 6 个 stub executor 之前，
锁定 4 个已实现 executor（balance / wide_table / vertical / sub_item）的现状行为，
以及 EXECUTORS 分发表 / ValidationType 枚举的契约，防止后续改动引入回归。

关键基线（记录现状，非缺陷）：
- `_execute_balance` 读 `ctx.report_data.get(rule.section_code)`：
  · report_data 有值 → 用真实报表行金额比对（Property 12 目标状态）
  · report_data 为空 → expected=0（接入前基线，形同虚设）
"""

from __future__ import annotations

from decimal import Decimal

from app.services.note_validation_engine import (
    ValidationContext,
    ValidationRule,
    ValidationType,
)
from app.services.note_validation_executors import (
    EXECUTORS,
    _execute_balance,
    _execute_sub_item,
    _execute_vertical,
    _execute_wide_table,
)


def _rule(rtype: ValidationType, section: str = "五、1") -> ValidationRule:
    return ValidationRule(
        section_code=section,
        rule_type=rtype,
        expression=f"test:{rtype.value}",
    )


# ---------------------------------------------------------------------------
# 契约：EXECUTORS 覆盖全部 11 类型 + 枚举不变
# ---------------------------------------------------------------------------


class TestExecutorContract:
    def test_executors_cover_all_11_types(self):
        assert set(EXECUTORS.keys()) == set(ValidationType)
        assert len(EXECUTORS) == 11

    def test_validation_type_values_unchanged(self):
        assert ValidationType.BALANCE.value == "余额"
        assert ValidationType.WIDE_TABLE.value == "宽表"
        assert ValidationType.VERTICAL.value == "纵向"
        assert ValidationType.SUB_ITEM.value == "其中项"


# ---------------------------------------------------------------------------
# balance — Property 12 基线
# ---------------------------------------------------------------------------


class TestExecuteBalanceBaseline:
    def test_empty_report_data_expected_zero(self):
        """基线：report_data 为空时 expected=0（接入前形同虚设）。"""
        ctx = ValidationContext(note_data={"五、1": {"total": 0}})
        res = _execute_balance(_rule(ValidationType.BALANCE), ctx)
        assert res.expected_value == Decimal("0")
        assert res.actual_value == Decimal("0")
        assert res.passed is True

    def test_report_data_present_uses_real_value(self):
        """Property 12：report_data 有值时用真实报表行金额比对。"""
        ctx = ValidationContext(
            note_data={"五、1": {"total": 100}},
            report_data={"五、1": Decimal("100")},
        )
        res = _execute_balance(_rule(ValidationType.BALANCE), ctx)
        assert res.expected_value == Decimal("100")
        assert res.actual_value == Decimal("100")
        assert res.passed is True

    def test_report_data_mismatch_fails(self):
        ctx = ValidationContext(
            note_data={"五、1": {"total": 80}},
            report_data={"五、1": Decimal("100")},
        )
        res = _execute_balance(_rule(ValidationType.BALANCE), ctx)
        assert res.expected_value == Decimal("100")
        assert res.actual_value == Decimal("80")
        assert res.passed is False
        assert res.diff_amount == Decimal("20")


# ---------------------------------------------------------------------------
# wide_table — 期初+增-减=期末
# ---------------------------------------------------------------------------


class TestExecuteWideTableBaseline:
    def test_balanced_rows_pass(self):
        ctx = ValidationContext(note_data={"五、1": {"rows": [
            {"opening": 100, "increase": 50, "decrease": 30, "closing": 120},
        ]}})
        res = _execute_wide_table(_rule(ValidationType.WIDE_TABLE), ctx)
        assert res.passed is True
        assert res.details["unbalanced_rows"] == []

    def test_unbalanced_row_fails(self):
        ctx = ValidationContext(note_data={"五、1": {"rows": [
            {"opening": 100, "increase": 50, "decrease": 30, "closing": 999},
        ]}})
        res = _execute_wide_table(_rule(ValidationType.WIDE_TABLE), ctx)
        assert res.passed is False
        assert len(res.details["unbalanced_rows"]) == 1


# ---------------------------------------------------------------------------
# vertical / sub_item — Σ明细 = 合计
# ---------------------------------------------------------------------------


class TestExecuteVerticalBaseline:
    def test_sum_equals_total_pass(self):
        ctx = ValidationContext(note_data={"五、1": {"rows": [
            {"amount": 30},
            {"amount": 70},
            {"amount": 100, "is_total": True},
        ]}})
        res = _execute_vertical(_rule(ValidationType.VERTICAL), ctx)
        assert res.passed is True
        assert res.expected_value == Decimal("100")
        assert res.actual_value == Decimal("100")

    def test_no_total_row_skips(self):
        ctx = ValidationContext(note_data={"五、1": {"rows": [{"amount": 30}]}})
        res = _execute_vertical(_rule(ValidationType.VERTICAL), ctx)
        assert res.passed is True
        assert "no total row" in res.details.get("note", "")

    def test_mismatch_fails(self):
        ctx = ValidationContext(note_data={"五、1": {"rows": [
            {"amount": 30},
            {"amount": 50, "is_total": True},
        ]}})
        res = _execute_vertical(_rule(ValidationType.VERTICAL), ctx)
        assert res.passed is False


class TestExecuteSubItemBaseline:
    def test_sub_items_sum_pass(self):
        ctx = ValidationContext(note_data={"五、1": {"rows": [
            {"amount": 40},
            {"amount": 60},
            {"amount": 100, "is_total": True},
        ]}})
        res = _execute_sub_item(_rule(ValidationType.SUB_ITEM), ctx)
        assert res.passed is True

    def test_no_total_skips(self):
        ctx = ValidationContext(note_data={"五、1": {"rows": [{"amount": 40}]}})
        res = _execute_sub_item(_rule(ValidationType.SUB_ITEM), ctx)
        assert res.passed is True
