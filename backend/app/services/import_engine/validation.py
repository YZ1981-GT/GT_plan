"""数据导入校验引擎 — 责任链模式校验规则

Validates: Requirements 4.7-4.20
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.models.audit_platform_schemas import ImportValidationResult, RuleResult


# ---------------------------------------------------------------------------
# Validation context
# ---------------------------------------------------------------------------


@dataclass
class ValidationContext:
    """校验上下文 — 携带项目级信息供规则使用。"""

    project_year: int
    account_codes: set[str] = field(default_factory=set)
    # For cross-table validation
    balance_data: list[dict] | None = None
    ledger_data: list[dict] | None = None
    aux_balance_data: list[dict] | None = None


# ---------------------------------------------------------------------------
# Base validation rule
# ---------------------------------------------------------------------------


class ValidationRule(ABC):
    """校验规则基类。"""

    name: str = "base_rule"
    severity: str = "warning"  # "reject" or "warning"

    @abstractmethod
    def applies_to(self, data_type: str) -> bool:
        """Whether this rule applies to the given data type."""
        ...

    @abstractmethod
    def execute(self, data: list[dict], context: ValidationContext) -> RuleResult:
        """Execute the validation rule."""
        ...


# ---------------------------------------------------------------------------
# YearConsistencyRule (reject)
# ---------------------------------------------------------------------------


class YearConsistencyRule(ValidationRule):
    """年度一致性校验 — 导入数据年度必须匹配项目年度。

    Validates: Requirements 4.13, 4.14
    """

    name = "year_consistency"
    severity = "reject"

    def applies_to(self, data_type: str) -> bool:
        return data_type in ("tb_ledger", "tb_aux_ledger")

    def execute(self, data: list[dict], context: ValidationContext) -> RuleResult:
        mismatched = []
        for row in data:
            voucher_date = row.get("voucher_date")
            if voucher_date and hasattr(voucher_date, "year"):
                if voucher_date.year != context.project_year:
                    mismatched.append({
                        "voucher_date": str(voucher_date),
                        "voucher_no": row.get("voucher_no", ""),
                        "data_year": voucher_date.year,
                        "project_year": context.project_year,
                    })

        if mismatched:
            return RuleResult(
                rule_name=self.name,
                severity=self.severity,
                passed=False,
                message=f"导入数据年度与项目年度({context.project_year})不匹配，"
                        f"发现{len(mismatched)}条不匹配记录",
                details=mismatched[:10],
            )

        return RuleResult(
            rule_name=self.name,
            severity=self.severity,
            passed=True,
            message="年度一致性校验通过",
        )


# ---------------------------------------------------------------------------
# DebitCreditBalanceRule (reject)
# ---------------------------------------------------------------------------


class DebitCreditBalanceRule(ValidationRule):
    """凭证借贷平衡校验 — 每张凭证的借方合计必须等于贷方合计。

    Validates: Requirements 4.7, 4.8
    """

    name = "debit_credit_balance"
    severity = "reject"

    def applies_to(self, data_type: str) -> bool:
        return data_type in ("tb_ledger", "tb_aux_ledger")

    def execute(self, data: list[dict], context: ValidationContext) -> RuleResult:
        # Group by voucher_no + voucher_date
        vouchers: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {"debit": Decimal("0"), "credit": Decimal("0")}
        )

        for row in data:
            voucher_no = row.get("voucher_no", "")
            voucher_date = str(row.get("voucher_date", ""))
            key = f"{voucher_date}|{voucher_no}"

            debit = row.get("debit_amount") or Decimal("0")
            credit = row.get("credit_amount") or Decimal("0")
            vouchers[key]["debit"] += debit
            vouchers[key]["credit"] += credit

        unbalanced = []
        for key, totals in vouchers.items():
            if totals["debit"] != totals["credit"]:
                parts = key.split("|", 1)
                unbalanced.append({
                    "voucher_date": parts[0],
                    "voucher_no": parts[1] if len(parts) > 1 else "",
                    "debit_total": str(totals["debit"]),
                    "credit_total": str(totals["credit"]),
                    "difference": str(totals["debit"] - totals["credit"]),
                })

        if unbalanced:
            return RuleResult(
                rule_name=self.name,
                severity=self.severity,
                passed=False,
                message=f"发现{len(unbalanced)}张凭证借贷不平衡",
                details=unbalanced[:10],
            )

        return RuleResult(
            rule_name=self.name,
            severity=self.severity,
            passed=True,
            message="凭证借贷平衡校验通过",
        )


# ---------------------------------------------------------------------------
# DuplicateDetectionRule (warning)
# ---------------------------------------------------------------------------


class DuplicateDetectionRule(ValidationRule):
    """重复记录检测 — 检测重复的凭证号+凭证日期。

    Validates: Requirements 4.15
    """

    name = "duplicate_detection"
    severity = "warning"

    def applies_to(self, data_type: str) -> bool:
        return data_type in ("tb_ledger", "tb_aux_ledger")

    def execute(self, data: list[dict], context: ValidationContext) -> RuleResult:
        seen: dict[str, int] = defaultdict(int)
        for row in data:
            voucher_no = row.get("voucher_no", "")
            voucher_date = str(row.get("voucher_date", ""))
            key = f"{voucher_date}|{voucher_no}"
            seen[key] += 1

        duplicates = [
            {"voucher_date": k.split("|")[0], "voucher_no": k.split("|")[1], "count": v}
            for k, v in seen.items()
            if v > 1
        ]

        if duplicates:
            return RuleResult(
                rule_name=self.name,
                severity=self.severity,
                passed=False,
                message=f"发现{len(duplicates)}组重复凭证",
                details=duplicates[:10],
            )

        return RuleResult(
            rule_name=self.name,
            severity=self.severity,
            passed=True,
            message="无重复记录",
        )


# ---------------------------------------------------------------------------
# OpeningClosingRule (warning)
# ---------------------------------------------------------------------------


class OpeningClosingRule(ValidationRule):
    """期初期末勾稽校验 — 借方科目: 期初+借方-贷方=期末; 贷方科目反之。

    Validates: Requirements 4.9, 4.10
    """

    name = "opening_closing"
    severity = "warning"

    def applies_to(self, data_type: str) -> bool:
        return data_type == "tb_balance"

    def execute(self, data: list[dict], context: ValidationContext) -> RuleResult:
        discrepancies = []
        for row in data:
            opening = row.get("opening_balance") or Decimal("0")
            debit = row.get("debit_amount") or Decimal("0")
            credit = row.get("credit_amount") or Decimal("0")
            closing = row.get("closing_balance") or Decimal("0")

            # Default formula: opening + debit - credit = closing (debit accounts)
            # For credit accounts: opening - debit + credit = closing
            # We check both and pass if either matches
            expected_debit = opening + debit - credit
            expected_credit = opening - debit + credit

            if closing != expected_debit and closing != expected_credit:
                discrepancies.append({
                    "account_code": row.get("account_code", ""),
                    "account_name": row.get("account_name", ""),
                    "opening_balance": str(opening),
                    "debit_amount": str(debit),
                    "credit_amount": str(credit),
                    "closing_balance": str(closing),
                    "expected_debit_formula": str(expected_debit),
                    "expected_credit_formula": str(expected_credit),
                })

        if discrepancies:
            return RuleResult(
                rule_name=self.name,
                severity=self.severity,
                passed=False,
                message=f"发现{len(discrepancies)}个科目期初期末不勾稽",
                details=discrepancies[:10],
            )

        return RuleResult(
            rule_name=self.name,
            severity=self.severity,
            passed=True,
            message="期初期末勾稽校验通过",
        )


# ---------------------------------------------------------------------------
# AccountCompletenessRule (warning)
# ---------------------------------------------------------------------------


class AccountCompletenessRule(ValidationRule):
    """科目完整性校验 — 导入数据中的科目编码必须存在于科目表中。

    Validates: Requirements 4.11, 4.12
    """

    name = "account_completeness"
    severity = "warning"

    def applies_to(self, data_type: str) -> bool:
        return data_type in ("tb_balance", "tb_aux_balance")

    def execute(self, data: list[dict], context: ValidationContext) -> RuleResult:
        if not context.account_codes:
            # No account chart loaded, skip
            return RuleResult(
                rule_name=self.name,
                severity=self.severity,
                passed=True,
                message="未加载科目表，跳过科目完整性校验",
            )

        missing = set()
        for row in data:
            code = row.get("account_code", "")
            if code and code not in context.account_codes:
                missing.add(code)

        if missing:
            return RuleResult(
                rule_name=self.name,
                severity=self.severity,
                passed=False,
                message=f"发现{len(missing)}个科目编码不存在于科目表中",
                details=[{"account_code": c} for c in sorted(missing)[:20]],
            )

        return RuleResult(
            rule_name=self.name,
            severity=self.severity,
            passed=True,
            message="科目完整性校验通过",
        )


# ---------------------------------------------------------------------------
# Cross-table validation rules (Task 9.4)
# ---------------------------------------------------------------------------


class LedgerBalanceReconcileRule(ValidationRule):
    """序时账-余额表勾稽 — 序时账按科目汇总的借贷发生额应等于余额表的借贷发生额。

    Validates: Requirements 4.17, 4.18
    """

    name = "ledger_balance_reconcile"
    severity = "warning"

    def applies_to(self, data_type: str) -> bool:
        # Applied when ledger data is being validated and balance data exists
        return data_type == "tb_ledger"

    def execute(self, data: list[dict], context: ValidationContext) -> RuleResult:
        if not context.balance_data:
            return RuleResult(
                rule_name=self.name,
                severity=self.severity,
                passed=True,
                message="无余额表数据，跳过账表勾稽校验",
            )

        # Sum ledger by account_code
        ledger_sums: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {"debit": Decimal("0"), "credit": Decimal("0")}
        )
        for row in data:
            code = row.get("account_code", "")
            if code:
                ledger_sums[code]["debit"] += row.get("debit_amount") or Decimal("0")
                ledger_sums[code]["credit"] += row.get("credit_amount") or Decimal("0")

        # Build balance lookup
        balance_map: dict[str, dict[str, Decimal]] = {}
        for row in context.balance_data:
            code = row.get("account_code", "")
            if code:
                balance_map[code] = {
                    "debit": row.get("debit_amount") or Decimal("0"),
                    "credit": row.get("credit_amount") or Decimal("0"),
                }

        discrepancies = []
        for code, ledger_totals in ledger_sums.items():
            if code in balance_map:
                bal = balance_map[code]
                if (ledger_totals["debit"] != bal["debit"]
                        or ledger_totals["credit"] != bal["credit"]):
                    discrepancies.append({
                        "account_code": code,
                        "ledger_debit": str(ledger_totals["debit"]),
                        "ledger_credit": str(ledger_totals["credit"]),
                        "balance_debit": str(bal["debit"]),
                        "balance_credit": str(bal["credit"]),
                    })

        if discrepancies:
            return RuleResult(
                rule_name=self.name,
                severity=self.severity,
                passed=False,
                message=f"发现{len(discrepancies)}个科目序时账与余额表不勾稽",
                details=discrepancies[:10],
            )

        return RuleResult(
            rule_name=self.name,
            severity=self.severity,
            passed=True,
            message="序时账-余额表勾稽校验通过",
        )


class AuxMainReconcileRule(ValidationRule):
    """辅助-主表勾稽 — 辅助余额表按科目汇总应等于主余额表。

    Validates: Requirements 4.19, 4.20
    """

    name = "aux_main_reconcile"
    severity = "warning"

    def applies_to(self, data_type: str) -> bool:
        return data_type == "tb_aux_balance"

    def execute(self, data: list[dict], context: ValidationContext) -> RuleResult:
        if not context.balance_data:
            return RuleResult(
                rule_name=self.name,
                severity=self.severity,
                passed=True,
                message="无主余额表数据，跳过辅助-主表勾稽校验",
            )

        # Sum aux balance by account_code
        aux_sums: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {
                "opening": Decimal("0"),
                "debit": Decimal("0"),
                "credit": Decimal("0"),
                "closing": Decimal("0"),
            }
        )
        for row in data:
            code = row.get("account_code", "")
            if code:
                aux_sums[code]["opening"] += row.get("opening_balance") or Decimal("0")
                aux_sums[code]["debit"] += row.get("debit_amount") or Decimal("0")
                aux_sums[code]["credit"] += row.get("credit_amount") or Decimal("0")
                aux_sums[code]["closing"] += row.get("closing_balance") or Decimal("0")

        # Build balance lookup
        balance_map: dict[str, dict[str, Decimal]] = {}
        for row in context.balance_data:
            code = row.get("account_code", "")
            if code:
                balance_map[code] = {
                    "opening": row.get("opening_balance") or Decimal("0"),
                    "debit": row.get("debit_amount") or Decimal("0"),
                    "credit": row.get("credit_amount") or Decimal("0"),
                    "closing": row.get("closing_balance") or Decimal("0"),
                }

        discrepancies = []
        for code, aux_totals in aux_sums.items():
            if code in balance_map:
                bal = balance_map[code]
                if aux_totals["closing"] != bal["closing"]:
                    discrepancies.append({
                        "account_code": code,
                        "aux_closing": str(aux_totals["closing"]),
                        "balance_closing": str(bal["closing"]),
                    })

        if discrepancies:
            return RuleResult(
                rule_name=self.name,
                severity=self.severity,
                passed=False,
                message=f"发现{len(discrepancies)}个科目辅助余额与主余额不勾稽",
                details=discrepancies[:10],
            )

        return RuleResult(
            rule_name=self.name,
            severity=self.severity,
            passed=True,
            message="辅助-主表勾稽校验通过",
        )


# ---------------------------------------------------------------------------
# ValidationEngine
# ---------------------------------------------------------------------------


class ValidationEngine:
    """校验引擎 — 责任链模式执行校验规则。

    Validates: Requirements 4.7-4.20
    """

    def __init__(self) -> None:
        self.rules: list[ValidationRule] = [
            YearConsistencyRule(),
            DebitCreditBalanceRule(),
            DuplicateDetectionRule(),
            OpeningClosingRule(),
            AccountCompletenessRule(),
            LedgerBalanceReconcileRule(),
            AuxMainReconcileRule(),
        ]

    def validate(
        self, data: list[dict], data_type: str, context: ValidationContext
    ) -> ImportValidationResult:
        """Execute all applicable validation rules.

        Reject-level failures stop further processing.
        Warning-level failures are recorded but allow import to proceed.
        """
        results: list[RuleResult] = []
        has_reject = False
        has_warning = False

        for rule in self.rules:
            if not rule.applies_to(data_type):
                continue

            result = rule.execute(data, context)
            results.append(result)

            if not result.passed:
                if rule.severity == "reject":
                    has_reject = True
                    break  # Stop on reject
                else:
                    has_warning = True

        return ImportValidationResult(
            passed=not has_reject,
            rules=results,
            has_reject=has_reject,
            has_warning=has_warning,
        )
