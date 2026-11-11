"""导入校验服务 — 三层校验模型

企业级导入校验分三层：
1. Schema Validation: 文件格式/编码/表头/必需列（已在 smart_import_engine 中实现）
2. Business Validation: 业务规则校验（借贷平衡/重复凭证/年度一致性等）
3. Activation Gate: 激活门禁（哪些问题阻止激活）

severity 分级：
- fatal: 禁止激活，数据不可用
- error: 默认禁止激活，可强制覆盖
- warning: 允许激活但需明确提示
- info: 仅提示

校验报告结构：
{
    "file": str,
    "sheet": str | None,
    "rule_code": str,
    "severity": "fatal" | "error" | "warning" | "info",
    "message": str,
    "details": dict,
    "sample_rows": list,
    "blocking": bool
}
"""

from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 校验规则基类
# ---------------------------------------------------------------------------

class ValidationFinding:
    """单条校验发现"""

    def __init__(
        self,
        rule_code: str,
        severity: str,
        message: str,
        file: str | None = None,
        sheet: str | None = None,
        details: dict | None = None,
        sample_rows: list | None = None,
    ):
        self.rule_code = rule_code
        self.severity = severity
        self.message = message
        self.file = file
        self.sheet = sheet
        self.details = details or {}
        self.sample_rows = sample_rows or []

    @property
    def blocking(self) -> bool:
        return self.severity in ("fatal", "error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "sheet": self.sheet,
            "rule_code": self.rule_code,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
            "sample_rows": self.sample_rows,
            "blocking": self.blocking,
        }


# ---------------------------------------------------------------------------
# 第二层：Business Validation 规则
# ---------------------------------------------------------------------------

def check_debit_credit_balance(parsed_data: dict[str, Any]) -> list[ValidationFinding]:
    """BV-01: 序时账借贷平衡检查

    每张凭证的借方合计应等于贷方合计。
    """
    findings: list[ValidationFinding] = []
    ledger_rows = parsed_data.get("ledger_rows") or []
    if not ledger_rows:
        return findings

    # 按凭证号分组
    voucher_groups: dict[str, dict] = defaultdict(lambda: {"debit": Decimal("0"), "credit": Decimal("0"), "rows": []})
    for row in ledger_rows:
        vno = row.get("voucher_no") or "unknown"
        debit = Decimal(str(row.get("debit_amount") or 0))
        credit = Decimal(str(row.get("credit_amount") or 0))
        voucher_groups[vno]["debit"] += debit
        voucher_groups[vno]["credit"] += credit
        voucher_groups[vno]["rows"].append(row)

    unbalanced = []
    for vno, group in voucher_groups.items():
        diff = abs(group["debit"] - group["credit"])
        if diff > Decimal("0.01"):  # 允许 1 分钱舍入误差
            unbalanced.append({"voucher_no": vno, "debit": str(group["debit"]), "credit": str(group["credit"]), "diff": str(diff)})

    if unbalanced:
        findings.append(ValidationFinding(
            rule_code="BV-01",
            severity="error",
            message=f"发现 {len(unbalanced)} 张凭证借贷不平衡",
            details={"unbalanced_count": len(unbalanced)},
            sample_rows=unbalanced[:5],
        ))

    return findings


def check_duplicate_vouchers(parsed_data: dict[str, Any]) -> list[ValidationFinding]:
    """BV-02: 重复凭证检查

    同一凭证号+日期+科目+金额完全相同视为重复。
    """
    findings: list[ValidationFinding] = []
    ledger_rows = parsed_data.get("ledger_rows") or []
    if not ledger_rows:
        return findings

    seen: dict[str, int] = defaultdict(int)
    for row in ledger_rows:
        key = f"{row.get('voucher_no')}|{row.get('voucher_date')}|{row.get('account_code')}|{row.get('debit_amount')}|{row.get('credit_amount')}"
        seen[key] += 1

    duplicates = [(k, v) for k, v in seen.items() if v > 1]
    if duplicates:
        findings.append(ValidationFinding(
            rule_code="BV-02",
            severity="warning",
            message=f"发现 {len(duplicates)} 组疑似重复凭证行",
            details={"duplicate_groups": len(duplicates)},
            sample_rows=[{"key": k, "count": v} for k, v in duplicates[:5]],
        ))

    return findings


def check_year_consistency(parsed_data: dict[str, Any], expected_year: int | None) -> list[ValidationFinding]:
    """BV-03: 年度一致性检查

    所有凭证日期应在同一会计年度内。
    """
    findings: list[ValidationFinding] = []
    if not expected_year:
        return findings

    ledger_rows = parsed_data.get("ledger_rows") or []
    wrong_year_count = 0
    sample_wrong: list[dict] = []

    for row in ledger_rows:
        date_str = str(row.get("voucher_date") or "")
        if date_str and len(date_str) >= 4:
            try:
                row_year = int(date_str[:4])
                if row_year != expected_year:
                    wrong_year_count += 1
                    if len(sample_wrong) < 5:
                        sample_wrong.append({"voucher_no": row.get("voucher_no"), "date": date_str, "year": row_year})
            except (ValueError, TypeError):
                pass

    if wrong_year_count > 0:
        ratio = wrong_year_count / max(len(ledger_rows), 1)
        severity = "error" if ratio > 0.1 else "warning"
        findings.append(ValidationFinding(
            rule_code="BV-03",
            severity=severity,
            message=f"{wrong_year_count} 条凭证日期不在 {expected_year} 年度内（占比 {ratio:.1%}）",
            details={"wrong_year_count": wrong_year_count, "expected_year": expected_year, "ratio": round(ratio, 4)},
            sample_rows=sample_wrong,
        ))

    return findings


def check_balance_opening_closing(parsed_data: dict[str, Any]) -> list[ValidationFinding]:
    """BV-04: 余额表期初+发生=期末勾稽

    期初余额 + 借方发生额 - 贷方发生额 = 期末余额（借方科目）
    期初余额 - 借方发生额 + 贷方发生额 = 期末余额（贷方科目）
    简化：|期初 + 借方 - 贷方 - 期末| 或 |期初 - 借方 + 贷方 - 期末| 应 ≤ 0.01
    """
    findings: list[ValidationFinding] = []
    balance_rows = parsed_data.get("balance_rows") or []
    if not balance_rows:
        return findings

    unbalanced = []
    for row in balance_rows:
        opening = Decimal(str(row.get("opening_balance") or 0))
        debit = Decimal(str(row.get("debit_amount") or 0))
        credit = Decimal(str(row.get("credit_amount") or 0))
        closing = Decimal(str(row.get("closing_balance") or 0))

        # 尝试两种方向
        diff1 = abs(opening + debit - credit - closing)
        diff2 = abs(opening - debit + credit - closing)
        min_diff = min(diff1, diff2)

        if min_diff > Decimal("0.01"):
            unbalanced.append({
                "account_code": row.get("account_code"),
                "opening": str(opening), "debit": str(debit),
                "credit": str(credit), "closing": str(closing),
                "diff": str(min_diff),
            })

    if unbalanced:
        findings.append(ValidationFinding(
            rule_code="BV-04",
            severity="warning",
            message=f"{len(unbalanced)} 个科目期初+发生≠期末",
            details={"unbalanced_count": len(unbalanced)},
            sample_rows=unbalanced[:5],
        ))

    return findings


# ---------------------------------------------------------------------------
# 第三层：Activation Gate
# ---------------------------------------------------------------------------

class ActivationGate:
    """激活门禁 — 决定数据集是否可以激活

    规则：
    - 有 fatal finding → 禁止激活
    - 有 error finding → 默认禁止，可通过 force=True 覆盖
    - 只有 warning/info → 允许激活
    """

    @staticmethod
    def evaluate(findings: list[ValidationFinding], force: bool = False) -> dict[str, Any]:
        """评估是否允许激活

        Returns:
            {
                "allowed": bool,
                "blocking_findings": [...],
                "summary": {"fatal": N, "error": N, "warning": N, "info": N},
                "force_applied": bool,
            }
        """
        summary = {"fatal": 0, "error": 0, "warning": 0, "info": 0}
        blocking: list[dict] = []

        for f in findings:
            sev = f.severity if f.severity in summary else "info"
            summary[sev] += 1
            if f.blocking:
                blocking.append(f.to_dict())

        has_fatal = summary["fatal"] > 0
        has_error = summary["error"] > 0

        if has_fatal:
            allowed = False
            force_applied = False
        elif has_error:
            allowed = force  # 有 error 时只有 force=True 才允许
            force_applied = force
        else:
            allowed = True
            force_applied = False

        return {
            "allowed": allowed,
            "blocking_findings": blocking,
            "summary": summary,
            "force_applied": force_applied,
        }


# ---------------------------------------------------------------------------
# 统一校验入口
# ---------------------------------------------------------------------------

class ImportValidationService:
    """统一校验服务 — 编排三层校验"""

    @staticmethod
    def run_business_validation(
        parsed_data: dict[str, Any],
        expected_year: int | None = None,
    ) -> list[ValidationFinding]:
        """执行第二层 Business Validation"""
        findings: list[ValidationFinding] = []

        findings.extend(check_debit_credit_balance(parsed_data))
        findings.extend(check_duplicate_vouchers(parsed_data))
        findings.extend(check_year_consistency(parsed_data, expected_year))
        findings.extend(check_balance_opening_closing(parsed_data))

        return findings

    @staticmethod
    async def run_dataset_business_validation(
        db: AsyncSession,
        *,
        project_id: UUID,
        year: int,
        dataset_id: UUID,
    ) -> list[ValidationFinding]:
        """Execute business validation against staged rows already written to DB."""
        from app.models.audit_platform_models import TbBalance, TbLedger

        findings: list[ValidationFinding] = []

        ledger_tbl = TbLedger.__table__
        voucher_stmt = (
            sa.select(
                ledger_tbl.c.voucher_no,
                sa.func.coalesce(sa.func.sum(ledger_tbl.c.debit_amount), 0).label("debit"),
                sa.func.coalesce(sa.func.sum(ledger_tbl.c.credit_amount), 0).label("credit"),
            )
            .where(
                ledger_tbl.c.project_id == project_id,
                ledger_tbl.c.year == year,
                ledger_tbl.c.dataset_id == dataset_id,
                ledger_tbl.c.is_deleted == sa.true(),
            )
            .group_by(ledger_tbl.c.voucher_no)
            .having(sa.func.abs(
                sa.func.coalesce(sa.func.sum(ledger_tbl.c.debit_amount), 0)
                - sa.func.coalesce(sa.func.sum(ledger_tbl.c.credit_amount), 0)
            ) > 0.01)
            .limit(20)
        )
        unbalanced = [
            {"voucher_no": row.voucher_no, "debit": str(row.debit), "credit": str(row.credit)}
            for row in (await db.execute(voucher_stmt)).fetchall()
        ]
        if unbalanced:
            findings.append(ValidationFinding(
                rule_code="BV-01",
                severity="error",
                message=f"发现 {len(unbalanced)} 张凭证借贷不平衡",
                details={"sample_count": len(unbalanced)},
                sample_rows=unbalanced[:5],
            ))

        balance_tbl = TbBalance.__table__
        balance_stmt = (
            sa.select(
                balance_tbl.c.account_code,
                balance_tbl.c.opening_balance,
                balance_tbl.c.debit_amount,
                balance_tbl.c.credit_amount,
                balance_tbl.c.closing_balance,
            )
            .where(
                balance_tbl.c.project_id == project_id,
                balance_tbl.c.year == year,
                balance_tbl.c.dataset_id == dataset_id,
                balance_tbl.c.is_deleted == sa.true(),
                sa.func.abs(
                    sa.func.coalesce(balance_tbl.c.opening_balance, 0)
                    + sa.func.coalesce(balance_tbl.c.debit_amount, 0)
                    - sa.func.coalesce(balance_tbl.c.credit_amount, 0)
                    - sa.func.coalesce(balance_tbl.c.closing_balance, 0)
                ) > 0.01,
            )
            .limit(20)
        )
        balance_errors = [
            {
                "account_code": row.account_code,
                "opening": str(row.opening_balance),
                "debit": str(row.debit_amount),
                "credit": str(row.credit_amount),
                "closing": str(row.closing_balance),
            }
            for row in (await db.execute(balance_stmt)).fetchall()
        ]
        if balance_errors:
            findings.append(ValidationFinding(
                rule_code="BV-04",
                severity="warning",
                message=f"发现 {len(balance_errors)} 个科目期初+发生不等于期末",
                details={"sample_count": len(balance_errors)},
                sample_rows=balance_errors[:5],
            ))

        return findings

    @staticmethod
    def build_full_report(
        schema_findings: list[dict[str, Any]],
        business_findings: list[ValidationFinding],
    ) -> list[dict[str, Any]]:
        """合并 Schema + Business 校验结果为统一报告"""
        report: list[dict[str, Any]] = []

        # Schema findings（来自 LedgerImportApplicationService._build_validation_report）
        for item in schema_findings:
            report.append(item)

        # Business findings
        for f in business_findings:
            report.append(f.to_dict())

        return report

    @staticmethod
    def evaluate_activation(
        report: list[dict[str, Any]],
        force: bool = False,
    ) -> dict[str, Any]:
        """评估激活门禁"""
        findings = [
            ValidationFinding(
                rule_code=item.get("rule_code", "unknown"),
                severity=item.get("severity", "info"),
                message=item.get("message", ""),
                file=item.get("file"),
                sheet=item.get("sheet"),
                details=item.get("details"),
                sample_rows=item.get("sample_rows"),
            )
            for item in report
        ]
        return ActivationGate.evaluate(findings, force=force)
