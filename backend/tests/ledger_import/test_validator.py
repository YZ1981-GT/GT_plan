"""Validator 3 级校验全分支测试 — Task 77。

覆盖：
- L1: 关键列空值→blocking / 金额非数值→blocking / 日期非法→blocking
- L1: 次关键列同类问题→warning + NULL
- L1: 非关键列不校验
- evaluate_activation: blocking 阻止激活 / force 跳过 / 不可 force 的码
"""

from __future__ import annotations

import pytest

from backend.app.services.ledger_import.validator import (
    ValidationFinding,
    evaluate_activation,
    validate_l1,
)


# ---------------------------------------------------------------------------
# L1 — 关键列校验
# ---------------------------------------------------------------------------


class TestL1KeyColumnEmpty:
    """L1: 关键列空值 → 脏数据行跳过 + warning（企业级宽容策略）。"""

    def test_empty_account_code_row_skipped_warning(self):
        """account_code 为空（其他 key 有值）→ ROW_SKIPPED_KEY_EMPTY warning。"""
        rows = [{"account_code": "", "debit_amount": "100", "credit_amount": "50"}]
        findings, cleaned = validate_l1(
            rows, "balance",
            column_mapping={"科目编码": "account_code"},
        )

        # 脏数据行整行跳过，不写入 cleaned_rows
        assert len(cleaned) == 0
        warnings = [f for f in findings if f.code == "ROW_SKIPPED_KEY_EMPTY"]
        assert len(warnings) == 1
        assert not warnings[0].blocking
        assert "account_code" in warnings[0].message

    def test_none_voucher_date_row_skipped_warning(self):
        """voucher_date 为 None → ROW_SKIPPED_KEY_EMPTY warning。"""
        rows = [{"voucher_date": None, "voucher_no": "记-001", "account_code": "1001",
                 "debit_amount": "100", "credit_amount": "0"}]
        findings, cleaned = validate_l1(rows, "ledger", column_mapping={})

        assert len(cleaned) == 0
        warnings = [f for f in findings if f.code == "ROW_SKIPPED_KEY_EMPTY"]
        assert len(warnings) == 1
        assert not warnings[0].blocking

    def test_all_key_empty_row_silently_skipped(self):
        """整行所有 key col 都空 → 静默跳过，不记 finding。"""
        rows = [{"voucher_date": None, "voucher_no": None, "account_code": None,
                 "debit_amount": None, "credit_amount": None}]
        findings, cleaned = validate_l1(rows, "ledger", column_mapping={})

        assert len(cleaned) == 0
        # 整行空白不记 finding
        assert len([f for f in findings if f.code == "ROW_SKIPPED_KEY_EMPTY"]) == 0


class TestL1KeyColumnAmountInvalid:
    """L1: 关键列金额非数值 → blocking。"""

    def test_debit_amount_not_numeric(self):
        """debit_amount = 'abc' → AMOUNT_NOT_NUMERIC_KEY blocking。"""
        rows = [{"account_code": "1001", "debit_amount": "abc", "credit_amount": "100"}]
        findings, cleaned = validate_l1(rows, "balance", column_mapping={})

        blocking = [f for f in findings if f.code == "AMOUNT_NOT_NUMERIC_KEY"]
        assert len(blocking) == 1
        assert "debit_amount" in blocking[0].message

    def test_opening_balance_with_comma(self):
        """opening_balance = '10,000.50' → 正常（逗号被 strip）。"""
        rows = [{"account_code": "1001", "opening_balance": "10,000.50",
                 "debit_amount": "100", "credit_amount": "50", "closing_balance": "10050.50"}]
        findings, cleaned = validate_l1(rows, "balance", column_mapping={})

        # 逗号分隔的数字应该能解析
        amount_errors = [f for f in findings if "AMOUNT" in f.code]
        assert len(amount_errors) == 0


class TestL1KeyColumnDateInvalid:
    """L1: 关键列日期非法 → blocking。"""

    def test_voucher_date_invalid_format(self):
        """voucher_date = 'not-a-date' → DATE_INVALID_KEY blocking。"""
        rows = [{"voucher_date": "not-a-date", "voucher_no": "记-001",
                 "account_code": "1001", "debit_amount": "100", "credit_amount": "0"}]
        findings, cleaned = validate_l1(rows, "ledger", column_mapping={})

        date_errors = [f for f in findings if f.code == "DATE_INVALID_KEY"]
        assert len(date_errors) == 1

    def test_voucher_date_valid_formats(self):
        """多种合法日期格式都应通过。"""
        valid_dates = ["2025-01-15", "2025/01/15", "20250115", "2025-01-15 10:30:00"]
        for d in valid_dates:
            rows = [{"voucher_date": d, "voucher_no": "记-001",
                     "account_code": "1001", "debit_amount": "100", "credit_amount": "0"}]
            findings, _ = validate_l1(rows, "ledger", column_mapping={})
            date_errors = [f for f in findings if "DATE" in f.code]
            assert len(date_errors) == 0, f"Date '{d}' should be valid"

    def test_voucher_date_excel_serial(self):
        """Excel 序列号（如 45678）应被解析为日期。"""
        rows = [{"voucher_date": "45678", "voucher_no": "记-001",
                 "account_code": "1001", "debit_amount": "100", "credit_amount": "0"}]
        findings, _ = validate_l1(rows, "ledger", column_mapping={})
        date_errors = [f for f in findings if "DATE" in f.code]
        assert len(date_errors) == 0


# ---------------------------------------------------------------------------
# L1 — 次关键列校验
# ---------------------------------------------------------------------------


class TestL1RecommendedColumn:
    """L1: 次关键列问题 → warning + 值置 NULL。"""

    def test_recommended_amount_not_numeric_warning(self):
        """次关键列金额非数值 → warning + cleaned row 中值为 None。"""
        # opening_debit 是 recommended for balance
        rows = [{"account_code": "1001", "opening_balance": "10000",
                 "debit_amount": "100", "credit_amount": "50",
                 "closing_balance": "10050",
                 "opening_debit": "not_a_number"}]
        findings, cleaned = validate_l1(rows, "balance", column_mapping={})

        warnings = [f for f in findings if f.severity == "warning"]
        assert any("opening_debit" in w.message for w in warnings)
        # Cleaned row should have None for the invalid field
        assert cleaned[0]["opening_debit"] is None


# ---------------------------------------------------------------------------
# L1 — 非关键列不校验
# ---------------------------------------------------------------------------


class TestL1ExtraColumnNoValidation:
    """L1: 非关键列（extra tier）不做任何校验。"""

    def test_extra_column_with_garbage_passes(self):
        """extra 列即使有垃圾值也不产生 finding。"""
        rows = [{"account_code": "1001", "debit_amount": "100",
                 "credit_amount": "50", "opening_balance": "1000",
                 "closing_balance": "1050",
                 "custom_garbage": "!@#$%^&*()", "another_extra": None}]
        findings, cleaned = validate_l1(rows, "balance", column_mapping={})

        # 不应有关于 custom_garbage 的 finding
        extra_findings = [f for f in findings if "custom" in f.message or "another" in f.message]
        assert len(extra_findings) == 0


# ---------------------------------------------------------------------------
# evaluate_activation
# ---------------------------------------------------------------------------


class TestEvaluateActivation:
    """evaluate_activation 门控逻辑。"""

    def test_no_findings_allows_activation(self):
        """无 finding → allowed=True。"""
        gate = evaluate_activation([], force=False)
        assert gate.allowed is True
        assert len(gate.blocking_findings) == 0

    def test_blocking_finding_denies_activation(self):
        """有 blocking finding → allowed=False。"""
        findings = [
            ValidationFinding(
                level="L1", severity="blocking",
                code="EMPTY_VALUE_KEY", message="test",
                location={"file": "", "sheet": "", "row": 0, "column": "account_code"},
                blocking=True,
            )
        ]
        gate = evaluate_activation(findings, force=False)
        assert gate.allowed is False
        assert len(gate.blocking_findings) == 1

    def test_force_skips_blocking(self):
        """force=True 跳过 blocking → allowed=True。"""
        findings = [
            ValidationFinding(
                level="L2", severity="blocking",
                code="L2_BALANCE_MISMATCH", message="test",
                location={"file": "", "sheet": "", "row": 0, "column": ""},
                blocking=True,
            )
        ]
        gate = evaluate_activation(findings, force=True)
        assert gate.allowed is True

    def test_non_forceable_code_cannot_be_skipped(self):
        """L2_LEDGER_YEAR_OUT_OF_RANGE 不可被 force 跳过。"""
        findings = [
            ValidationFinding(
                level="L2", severity="blocking",
                code="L2_LEDGER_YEAR_OUT_OF_RANGE", message="test",
                location={"file": "", "sheet": "", "row": 0, "column": ""},
                blocking=True,
            )
        ]
        gate = evaluate_activation(findings, force=True)
        assert gate.allowed is False

    def test_warnings_dont_block(self):
        """warning 级别不阻止激活。"""
        findings = [
            ValidationFinding(
                level="L1", severity="warning",
                code="AMOUNT_NOT_NUMERIC_RECOMMENDED", message="test",
                location={"file": "", "sheet": "", "row": 0, "column": ""},
                blocking=False,
            )
        ]
        gate = evaluate_activation(findings, force=False)
        assert gate.allowed is True
        assert len(gate.warning_findings) == 1
