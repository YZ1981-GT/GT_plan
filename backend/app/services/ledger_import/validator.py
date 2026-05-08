"""3 级校验 — L1 解析期 / L2 全量后 / L3 跨表。

职责（见 design.md §19 / Sprint 2 Task 35-38）：

- L1 (按列分层) :
  - 关键列     → 金额非数 / 日期非法 / 值为空 触发 `blocking`。
  - 次关键列   → 同类问题触发 `warning` 并把该值置 NULL。
  - 非关键列   → 不校验，原样进 `raw_extra`。
- L2           : 借贷平衡、年度范围、科目存在性。
- L3           : 余额期末 = 序时累计（容差 1 元）、辅助与主表科目一致性。
- `force_activate` : 跳过 L2/L3 的 blocking（需审批链）。

返回 `ValidationFinding` 列表 + `ActivationGate` 判定。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

from .detection_types import (
    KEY_COLUMNS,
    RECOMMENDED_COLUMNS,
    TableType,
)

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


class ValidationFinding(BaseModel):
    """单条校验发现。"""

    level: Literal["L1", "L2", "L3"]
    severity: Literal["fatal", "blocking", "warning"]
    code: str
    message: str
    location: dict  # { file, sheet, row, column }
    blocking: bool  # True when this finding blocks activation (unless force)


class ActivationGate(BaseModel):
    """激活门判定结果。"""

    allowed: bool
    blocking_findings: list[ValidationFinding]
    warning_findings: list[ValidationFinding]


# ---------------------------------------------------------------------------
# 内部常量
# ---------------------------------------------------------------------------

# 金额类字段名集合（用于判断是否需要做数值校验）
_AMOUNT_FIELDS: set[str] = {
    "debit_amount",
    "credit_amount",
    "opening_balance",
    "closing_balance",
    "opening_debit",
    "opening_credit",
    "closing_debit",
    "closing_credit",
}

# 日期类字段名集合
_DATE_FIELDS: set[str] = {
    "voucher_date",
}

# L2_LEDGER_YEAR_OUT_OF_RANGE 不可被 force 跳过
_NON_FORCEABLE_CODES: frozenset[str] = frozenset({
    "L2_LEDGER_YEAR_OUT_OF_RANGE",
})

# 日期解析格式列表
_DATE_FORMATS: list[str] = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y%m%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _try_parse_numeric(value: object) -> Optional[float]:
    """尝试将值解析为数值，失败返回 None。"""
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s == "":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _try_parse_date(value: object) -> Optional[datetime]:
    """尝试将值解析为日期，支持多种格式和 Excel 序列号。"""
    if value is None:
        return None
    # 如果已经是 datetime 对象
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if s == "":
        return None
    # 尝试标准格式
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # 尝试 Excel 序列号（纯数字，范围 1-100000 大致覆盖 1900-2173）
    try:
        serial = float(s)
        if 1 <= serial <= 100000:
            # Excel 序列号：1 = 1900-01-01（Excel 有 1900 闰年 bug，这里简化处理）
            from datetime import timedelta

            base = datetime(1899, 12, 30)
            return base + timedelta(days=int(serial))
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def _is_empty(value: object) -> bool:
    """判断值是否为空。"""
    if value is None:
        return True
    s = str(value).strip()
    return s == ""


# ---------------------------------------------------------------------------
# Level 1 — Parse-time validation
# ---------------------------------------------------------------------------


def validate_l1(
    rows: list[dict],
    table_type: TableType,
    column_mapping: dict[str, str],  # {original_header: standard_field}
    *,
    file_name: str = "",
    sheet_name: str = "",
) -> tuple[list[ValidationFinding], list[dict]]:
    """L1 validation: per-row, per-column checks.

    Returns (findings, cleaned_rows) where cleaned_rows has:
    - Key column violations → finding is blocking, row NOT cleaned (caller must handle)
    - Recommended column violations → value set to None in cleaned row, finding is warning
    - Extra columns → not validated at all

    Checks:
    - AMOUNT fields (debit_amount, credit_amount, opening_balance, closing_balance, etc.):
      Must be numeric. Key column → blocking; recommended → warning + NULL.
    - DATE fields (voucher_date):
      Must be parseable as date. Key column → blocking; recommended → warning + NULL.
    - EMPTY check:
      Key columns must not be empty/None. → blocking.
      Recommended columns: no check (empty is acceptable).
    """
    key_cols = KEY_COLUMNS.get(table_type, set())
    rec_cols = RECOMMENDED_COLUMNS.get(table_type, set())

    # Build reverse mapping: standard_field → original_header (for reference)
    # But rows are already keyed by standard_field names
    # The column_mapping tells us which original headers map to which standard fields
    # Rows dict keys are standard_field names

    findings: list[ValidationFinding] = []
    cleaned_rows: list[dict] = []

    for row_idx, row in enumerate(rows):
        cleaned_row = dict(row)  # shallow copy

        for field_name, value in row.items():
            # Determine tier
            if field_name in key_cols:
                tier = "key"
            elif field_name in rec_cols:
                tier = "recommended"
            else:
                # Extra column — no validation
                continue

            location = {
                "file": file_name,
                "sheet": sheet_name,
                "row": row_idx,
                "column": field_name,
            }

            # --- EMPTY check (key columns only) ---
            if tier == "key" and _is_empty(value):
                findings.append(
                    ValidationFinding(
                        level="L1",
                        severity="blocking",
                        code="EMPTY_VALUE_KEY",
                        message=f"关键列 '{field_name}' 值为空（第 {row_idx} 行）",
                        location=location,
                        blocking=True,
                    )
                )
                continue  # skip further checks for this field

            # --- AMOUNT check ---
            if field_name in _AMOUNT_FIELDS:
                if not _is_empty(value) and _try_parse_numeric(value) is None:
                    if tier == "key":
                        findings.append(
                            ValidationFinding(
                                level="L1",
                                severity="blocking",
                                code="AMOUNT_NOT_NUMERIC_KEY",
                                message=(
                                    f"关键列 '{field_name}' 值 '{value}' "
                                    f"非数值（第 {row_idx} 行）"
                                ),
                                location=location,
                                blocking=True,
                            )
                        )
                    else:
                        # recommended → warning + NULL
                        findings.append(
                            ValidationFinding(
                                level="L1",
                                severity="warning",
                                code="AMOUNT_NOT_NUMERIC_RECOMMENDED",
                                message=(
                                    f"次关键列 '{field_name}' 值 '{value}' "
                                    f"非数值，已置 NULL（第 {row_idx} 行）"
                                ),
                                location=location,
                                blocking=False,
                            )
                        )
                        cleaned_row[field_name] = None

            # --- DATE check ---
            elif field_name in _DATE_FIELDS:
                if not _is_empty(value) and _try_parse_date(value) is None:
                    if tier == "key":
                        findings.append(
                            ValidationFinding(
                                level="L1",
                                severity="blocking",
                                code="DATE_INVALID_KEY",
                                message=(
                                    f"关键列 '{field_name}' 值 '{value}' "
                                    f"无法解析为日期（第 {row_idx} 行）"
                                ),
                                location=location,
                                blocking=True,
                            )
                        )
                    else:
                        # recommended → warning + NULL
                        findings.append(
                            ValidationFinding(
                                level="L1",
                                severity="warning",
                                code="DATE_INVALID_RECOMMENDED",
                                message=(
                                    f"次关键列 '{field_name}' 值 '{value}' "
                                    f"无法解析为日期，已置 NULL（第 {row_idx} 行）"
                                ),
                                location=location,
                                blocking=False,
                            )
                        )
                        cleaned_row[field_name] = None

        cleaned_rows.append(cleaned_row)

    return findings, cleaned_rows


# ---------------------------------------------------------------------------
# Level 2 — Post-write validation
# ---------------------------------------------------------------------------


async def validate_l2(
    db,
    *,
    dataset_id: UUID,
    year: int,
    project_id: UUID,
) -> list[ValidationFinding]:
    """L2 validation: aggregate checks after all data is written.

    Checks:
    1. BALANCE_UNBALANCED: sum(debit_amount) != sum(credit_amount) in tb_ledger
    2. L2_LEDGER_YEAR_OUT_OF_RANGE: any voucher_date outside [year-01-01, year-12-31]
    3. ACCOUNT_NOT_IN_CHART: account_code in tb_ledger not found in account_chart
       (only if account_chart was imported)

    All findings are blocking=True by default (can be force-skipped).
    """
    from sqlalchemy import text

    findings: list[ValidationFinding] = []

    # --- Check 1: Debit/Credit balance in tb_ledger ---
    result = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(debit_amount), 0) AS total_debit,
                COALESCE(SUM(credit_amount), 0) AS total_credit
            FROM tb_ledger
            WHERE dataset_id = :dataset_id
        """),
        {"dataset_id": str(dataset_id)},
    )
    row = result.fetchone()
    if row is not None:
        total_debit = float(row.total_debit)
        total_credit = float(row.total_credit)
        if abs(total_debit - total_credit) > 0.01:
            findings.append(
                ValidationFinding(
                    level="L2",
                    severity="blocking",
                    code="BALANCE_UNBALANCED",
                    message=(
                        f"序时账借贷不平衡：借方合计 {total_debit:.2f}，"
                        f"贷方合计 {total_credit:.2f}，"
                        f"差额 {abs(total_debit - total_credit):.2f}"
                    ),
                    location={"file": "", "sheet": "", "row": -1, "column": ""},
                    blocking=True,
                )
            )

    # --- Check 2: Voucher date out of year range ---
    result = await db.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM tb_ledger
            WHERE dataset_id = :dataset_id
              AND (
                  voucher_date < :year_start
                  OR voucher_date > :year_end
              )
        """),
        {
            "dataset_id": str(dataset_id),
            "year_start": f"{year}-01-01",
            "year_end": f"{year}-12-31",
        },
    )
    row = result.fetchone()
    if row is not None and row.cnt > 0:
        findings.append(
            ValidationFinding(
                level="L2",
                severity="blocking",
                code="L2_LEDGER_YEAR_OUT_OF_RANGE",
                message=(
                    f"序时账中有 {row.cnt} 条记录的凭证日期"
                    f"不在 {year} 年度范围内（{year}-01-01 ~ {year}-12-31）"
                ),
                location={"file": "", "sheet": "", "row": -1, "column": "voucher_date"},
                blocking=True,
            )
        )

    # --- Check 3: Account code not in chart (only if chart exists) ---
    result = await db.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM tb_account_chart
            WHERE dataset_id = :dataset_id
        """),
        {"dataset_id": str(dataset_id)},
    )
    chart_row = result.fetchone()
    has_chart = chart_row is not None and chart_row.cnt > 0

    if has_chart:
        result = await db.execute(
            text("""
                SELECT DISTINCT l.account_code
                FROM tb_ledger l
                LEFT JOIN tb_account_chart c
                    ON c.dataset_id = l.dataset_id
                    AND c.account_code = l.account_code
                WHERE l.dataset_id = :dataset_id
                  AND c.account_code IS NULL
            """),
            {"dataset_id": str(dataset_id)},
        )
        missing_codes = [r.account_code for r in result.fetchall()]
        if missing_codes:
            sample = missing_codes[:10]
            findings.append(
                ValidationFinding(
                    level="L2",
                    severity="blocking",
                    code="ACCOUNT_NOT_IN_CHART",
                    message=(
                        f"序时账中有 {len(missing_codes)} 个科目代码"
                        f"不在科目表中：{', '.join(sample)}"
                        + ("..." if len(missing_codes) > 10 else "")
                    ),
                    location={
                        "file": "",
                        "sheet": "",
                        "row": -1,
                        "column": "account_code",
                    },
                    blocking=True,
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Level 3 — Cross-table validation
# ---------------------------------------------------------------------------


async def validate_l3(
    db,
    *,
    dataset_id: UUID,
    project_id: UUID,
) -> list[ValidationFinding]:
    """L3 validation: cross-table consistency checks.

    Checks:
    1. BALANCE_LEDGER_MISMATCH: For each account_code,
       tb_balance.closing_balance != tb_balance.opening_balance
           + sum(tb_ledger.debit) - sum(tb_ledger.credit)
       Tolerance: abs(diff) > 1.0 → blocking
    2. AUX_ACCOUNT_MISMATCH: account_codes in tb_aux_balance/tb_aux_ledger
       that don't exist in tb_balance/tb_ledger → warning (not blocking)
    """
    from sqlalchemy import text

    findings: list[ValidationFinding] = []

    # --- Check 1: Balance vs Ledger mismatch ---
    result = await db.execute(
        text("""
            SELECT
                b.account_code,
                b.opening_balance,
                b.closing_balance,
                COALESCE(l.sum_debit, 0) AS sum_debit,
                COALESCE(l.sum_credit, 0) AS sum_credit
            FROM tb_balance b
            LEFT JOIN (
                SELECT
                    account_code,
                    SUM(debit_amount) AS sum_debit,
                    SUM(credit_amount) AS sum_credit
                FROM tb_ledger
                WHERE dataset_id = :dataset_id
                GROUP BY account_code
            ) l ON l.account_code = b.account_code
            WHERE b.dataset_id = :dataset_id
        """),
        {"dataset_id": str(dataset_id)},
    )
    rows = result.fetchall()
    mismatch_accounts: list[str] = []
    for row in rows:
        opening = float(row.opening_balance) if row.opening_balance is not None else 0.0
        closing = float(row.closing_balance) if row.closing_balance is not None else 0.0
        sum_debit = float(row.sum_debit)
        sum_credit = float(row.sum_credit)
        expected_closing = opening + sum_debit - sum_credit
        diff = abs(closing - expected_closing)
        if diff > 1.0:
            mismatch_accounts.append(row.account_code)

    if mismatch_accounts:
        sample = mismatch_accounts[:10]
        findings.append(
            ValidationFinding(
                level="L3",
                severity="blocking",
                code="BALANCE_LEDGER_MISMATCH",
                message=(
                    f"余额表期末余额与序时账累计不一致（容差 1 元），"
                    f"涉及 {len(mismatch_accounts)} 个科目：{', '.join(sample)}"
                    + ("..." if len(mismatch_accounts) > 10 else "")
                ),
                location={
                    "file": "",
                    "sheet": "",
                    "row": -1,
                    "column": "closing_balance",
                },
                blocking=True,
            )
        )

    # --- Check 2: Aux account codes not in main tables ---
    # Check aux_balance codes not in balance
    result = await db.execute(
        text("""
            SELECT DISTINCT ab.account_code
            FROM tb_aux_balance ab
            LEFT JOIN tb_balance b
                ON b.dataset_id = ab.dataset_id
                AND b.account_code = ab.account_code
            WHERE ab.dataset_id = :dataset_id
              AND b.account_code IS NULL
        """),
        {"dataset_id": str(dataset_id)},
    )
    aux_balance_missing = [r.account_code for r in result.fetchall()]

    # Check aux_ledger codes not in ledger
    result = await db.execute(
        text("""
            SELECT DISTINCT al.account_code
            FROM tb_aux_ledger al
            LEFT JOIN tb_ledger l
                ON l.dataset_id = al.dataset_id
                AND l.account_code = al.account_code
            WHERE al.dataset_id = :dataset_id
              AND l.account_code IS NULL
        """),
        {"dataset_id": str(dataset_id)},
    )
    aux_ledger_missing = [r.account_code for r in result.fetchall()]

    all_aux_missing = set(aux_balance_missing + aux_ledger_missing)
    if all_aux_missing:
        sample = sorted(all_aux_missing)[:10]
        findings.append(
            ValidationFinding(
                level="L3",
                severity="warning",
                code="AUX_ACCOUNT_MISMATCH",
                message=(
                    f"辅助表中有 {len(all_aux_missing)} 个科目代码"
                    f"不在主表中：{', '.join(sample)}"
                    + ("..." if len(all_aux_missing) > 10 else "")
                ),
                location={
                    "file": "",
                    "sheet": "",
                    "row": -1,
                    "column": "account_code",
                },
                blocking=False,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Activation Gate
# ---------------------------------------------------------------------------


def evaluate_activation(
    findings: list[ValidationFinding],
    *,
    force: bool = False,
) -> ActivationGate:
    """Evaluate whether activation is allowed.

    Rules:
    - L1 blocking findings → ALWAYS block (cannot force-skip)
    - L2/L3 blocking findings → block UNLESS force=True
    - Exception: L2_LEDGER_YEAR_OUT_OF_RANGE cannot be force-skipped
    - Warnings never block
    """
    blocking_findings: list[ValidationFinding] = []
    warning_findings: list[ValidationFinding] = []

    for f in findings:
        if f.blocking:
            blocking_findings.append(f)
        else:
            warning_findings.append(f)

    if not blocking_findings:
        return ActivationGate(
            allowed=True,
            blocking_findings=[],
            warning_findings=warning_findings,
        )

    # Determine if activation is allowed despite blocking findings
    if not force:
        # Without force, any blocking finding blocks
        return ActivationGate(
            allowed=False,
            blocking_findings=blocking_findings,
            warning_findings=warning_findings,
        )

    # With force=True, check which findings can be skipped
    non_skippable: list[ValidationFinding] = []
    for f in blocking_findings:
        # L1 blocking findings can NEVER be force-skipped
        if f.level == "L1":
            non_skippable.append(f)
        # Specific codes that cannot be force-skipped
        elif f.code in _NON_FORCEABLE_CODES:
            non_skippable.append(f)
        # L2/L3 blocking findings CAN be force-skipped (not added to non_skippable)

    if non_skippable:
        return ActivationGate(
            allowed=False,
            blocking_findings=non_skippable,
            warning_findings=warning_findings,
        )

    # All blocking findings are force-skippable
    return ActivationGate(
        allowed=True,
        blocking_findings=blocking_findings,
        warning_findings=warning_findings,
    )


__all__ = [
    "ValidationFinding",
    "ActivationGate",
    "validate_l1",
    "validate_l2",
    "validate_l3",
    "evaluate_activation",
]
