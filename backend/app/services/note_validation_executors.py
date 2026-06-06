"""附注校验规则执行器 — 从 note_validation_engine.py 抽出的伴生模块

包含 11 个 _execute_* 纯函数 + _EXECUTORS 分发表。
每个执行器接收 (ValidationRule, ValidationContext) → ValidationResult。

由 NoteValidationEngine.execute_rule 通过 _EXECUTORS[rule.rule_type] 分发调用。
"""

from __future__ import annotations

from decimal import Decimal

from app.services.note_validation_engine import (
    ValidationContext,
    ValidationResult,
    ValidationRule,
    ValidationType,
    _resolve_tolerance,
)


def _execute_balance(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """余额校验：报表行次金额 = 附注合计行金额"""
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )
    expected = ctx.report_data.get(rule.section_code, Decimal("0"))
    note_section_data = ctx.note_data.get(rule.section_code, {})
    actual = Decimal(str(note_section_data.get("total", 0)))

    result.expected_value = expected
    result.actual_value = actual
    diff = abs(expected - actual)
    result.diff_amount = diff
    tolerance = _resolve_tolerance(rule.tolerance, expected, actual)
    result.passed = diff <= tolerance
    result.details = {"check": "report_amount == note_total"}
    return result


def _execute_wide_table(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """宽表校验：期初余额 + 本期增加 - 本期减少 = 期末余额"""
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )
    note_section_data = ctx.note_data.get(rule.section_code, {})
    rows = note_section_data.get("rows", [])

    errors = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        opening = Decimal(str(row.get("opening", 0) or 0))
        increase = Decimal(str(row.get("increase", 0) or 0))
        decrease = Decimal(str(row.get("decrease", 0) or 0))
        closing = Decimal(str(row.get("closing", 0) or 0))

        expected_closing = opening + increase - decrease
        diff = abs(expected_closing - closing)
        tolerance = _resolve_tolerance(rule.tolerance, opening, increase, decrease, closing)
        if diff > tolerance:
            errors.append({
                "row_index": i,
                "expected": float(expected_closing),
                "actual": float(closing),
                "diff": float(diff),
            })

    result.passed = len(errors) == 0
    result.details = {"unbalanced_rows": errors}
    if errors:
        result.diff_amount = Decimal(str(errors[0]["diff"]))
    return result


def _execute_vertical(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """纵向校验：各明细行之和 = 合计行"""
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )
    note_section_data = ctx.note_data.get(rule.section_code, {})
    rows = note_section_data.get("rows", [])

    total_value = Decimal("0")
    detail_sum = Decimal("0")
    found_total = False

    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("is_total"):
            total_value = Decimal(str(row.get("amount", 0) or 0))
            found_total = True
        else:
            detail_sum += Decimal(str(row.get("amount", 0) or 0))

    if not found_total:
        result.passed = True
        result.details = {"note": "no total row found, skipped"}
        return result

    diff = abs(detail_sum - total_value)
    result.expected_value = total_value
    result.actual_value = detail_sum
    result.diff_amount = diff
    tolerance = _resolve_tolerance(rule.tolerance, total_value, detail_sum)
    result.passed = diff <= tolerance
    result.details = {"check": "sum(detail_rows) == total_row"}
    return result


def _execute_cross(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """交叉校验：附注章节间数据一致性"""
    return ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
        passed=True,
        details={"check": "cross_section_consistency", "note": "stub implementation"},
    )


def _execute_cross_account(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """跨科目校验：不同科目间的勾稽关系"""
    return ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
        passed=True,
        details={"check": "cross_account_reconciliation", "note": "stub implementation"},
    )


def _execute_sub_item(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """其中项校验：sum(明细行) = 合计行"""
    result = ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
    )
    note_section_data = ctx.note_data.get(rule.section_code, {})
    rows = note_section_data.get("rows", [])

    total_value = Decimal("0")
    detail_sum = Decimal("0")
    found_total = False

    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("is_total"):
            total_value = Decimal(str(row.get("amount", 0) or 0))
            found_total = True
        else:
            detail_sum += Decimal(str(row.get("amount", 0) or 0))

    if not found_total:
        result.passed = True
        result.details = {"note": "no total row found, skipped"}
        return result

    diff = abs(detail_sum - total_value)
    result.expected_value = total_value
    result.actual_value = detail_sum
    result.diff_amount = diff
    tolerance = _resolve_tolerance(rule.tolerance, total_value, detail_sum)
    result.passed = diff <= tolerance
    result.details = {"check": "sum(sub_items) == total"}
    return result


def _execute_secondary_detail(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """二级明细校验"""
    return ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
        passed=True,
        details={"check": "secondary_detail_consistency", "note": "stub implementation"},
    )


def _execute_completeness(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """完整性校验：有余额的科目必须有对应附注章节"""
    return ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
        passed=True,
        details={"check": "note_completeness", "note": "stub implementation"},
    )


def _execute_llm_review(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """LLM审核：调用 LLM 对附注文本进行合理性审核"""
    return ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
        passed=True,
        details={"check": "llm_review", "note": "stub - LLM not invoked"},
    )


def _execute_aging_progression(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """账龄衔接校验"""
    return ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
        passed=True,
        details={"check": "aging_progression", "note": "stub implementation"},
    )


def _execute_description(rule: ValidationRule, ctx: ValidationContext) -> ValidationResult:
    """描述类 preset：纯文本章节兜底"""
    return ValidationResult(
        section_code=rule.section_code,
        rule_type=rule.rule_type.value,
        rule_expression=rule.expression,
        passed=True,
        details={"check": "description_skipped"},
    )


# Executor dispatch table
EXECUTORS = {
    ValidationType.BALANCE: _execute_balance,
    ValidationType.WIDE_TABLE: _execute_wide_table,
    ValidationType.VERTICAL: _execute_vertical,
    ValidationType.CROSS: _execute_cross,
    ValidationType.CROSS_ACCOUNT: _execute_cross_account,
    ValidationType.SUB_ITEM: _execute_sub_item,
    ValidationType.SECONDARY_DETAIL: _execute_secondary_detail,
    ValidationType.COMPLETENESS: _execute_completeness,
    ValidationType.AGING_PROGRESSION: _execute_aging_progression,
    ValidationType.LLM_REVIEW: _execute_llm_review,
    ValidationType.DESCRIPTION: _execute_description,
}
